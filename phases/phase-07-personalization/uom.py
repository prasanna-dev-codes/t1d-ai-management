"""Bounded reader for the official T1D-UOM v1.0.4 offline archive."""

import csv
import hashlib
import io
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from zipfile import ZipFile

from t1d_forecasting.datasets import Kind, OfflineEvent, SourceData, number

ARCHIVE_SHA256 = "f9725405a0761e4e6f51be7a0ea0a221e58afe8eda96ecedb213998cf382526c"
_FILES: tuple[tuple[str, str, str, str, Kind, str], ...] = (
    ("Glucose Data", "Glucose", "bg_ts", "value", "glucose", "mg/dL"),
    ("Nutrition Data", "Nutrition", "meal_ts", "carbs_g", "carbohydrate", "g"),
    ("Insulin Data/Bolus Data", "Bolus", "bolus_ts", "bolus_dose", "bolus", "U"),
)


def source_time(raw: str | None) -> datetime:
    if raw is None:
        raise ValueError("Missing T1D-UOM timestamp")
    value = raw.strip()
    try:
        return datetime.strptime(value, "%d/%m/%Y %H:%M")
    except ValueError:
        return datetime.strptime(value, "%d/%m/%Y %H:%M:%S")


def read_official_uom(path: Path) -> tuple[tuple[SourceData, ...], dict[str, int]]:
    if path.stat().st_size > 15_000_000:
        raise ValueError("Unexpected T1D-UOM archive size")
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != ARCHIVE_SHA256:
        raise ValueError("Expected the pinned official T1D-UOM archive")
    return read_uom(io.BytesIO(payload))


def read_uom(path: Path | io.BytesIO) -> tuple[tuple[SourceData, ...], dict[str, int]]:
    groups: dict[str, list[OfflineEvent]] = defaultdict(list)
    rejected: Counter[str] = Counter()
    inventory: Counter[str] = Counter()
    with ZipFile(path) as archive:
        files = archive.infolist()
        if len(files) > 300 or sum(file.file_size for file in files) > 150_000_000:
            raise ValueError("T1D-UOM archive exceeds reader limits")
        for directory, prefix, clock, measurement, kind, unit in _FILES:
            pattern = re.compile(rf"[^/]+/{re.escape(directory)}/UoM{prefix}(\d{{4}})\.csv")
            for file in files:
                match = pattern.fullmatch(file.filename)
                if match is None:
                    continue
                if file.file_size > 15_000_000:
                    raise ValueError("T1D-UOM input file exceeds reader limit")
                participant = match.group(1)
                data = archive.read(file)
                source_hash = hashlib.sha256(data).hexdigest()
                reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig")))
                if not {clock, measurement} <= set(reader.fieldnames or []):
                    raise ValueError("Unexpected T1D-UOM column names")
                previous = None
                for index, row in enumerate(reader, 1):
                    try:
                        stamp = source_time(row[clock])
                        value = number(row[measurement], positive=True)
                    except (ValueError, TypeError):
                        rejected[participant] += 1
                        inventory[f"{kind}_invalid"] += 1
                        continue
                    if value is None:
                        inventory[f"{kind}_missing"] += 1
                        continue
                    if kind == "glucose":
                        if previous is not None and stamp < previous:
                            raise ValueError("Unresolved CGM order in T1D-UOM archive")
                        previous = stamp
                        value /= 0.0555
                    groups[participant].append(
                        OfflineEvent(
                            "uom",
                            participant,
                            "unsplit",
                            kind,
                            stamp,
                            row[clock],
                            value,
                            unit,
                            source_hash,
                            index,
                        )
                    )
                    inventory[f"{kind}_read"] += 1
    if not inventory["glucose_read"]:
        raise ValueError("No usable T1D-UOM CGM observations")
    for participant, events in groups.items():
        simultaneous = Counter(
            (event.kind, event.time) for event in events if event.kind != "glucose"
        )
        admitted = [
            event
            for event in events
            if event.kind == "glucose" or simultaneous[event.kind, event.time] == 1
        ]
        inventory["ambiguous_context_rows_excluded"] += len(events) - len(admitted)
        groups[participant] = admitted
    inventory["participants_with_cgm"] = sum(
        any(event.kind == "glucose" for event in events) for events in groups.values()
    )
    return tuple(
        SourceData(
            tuple(events),
            rejected[participant],
            hashlib.sha256(
                "".join(sorted({event.source_sha256 for event in events})).encode()
            ).hexdigest(),
        )
        for participant, events in sorted(groups.items())
    ), dict(inventory)
