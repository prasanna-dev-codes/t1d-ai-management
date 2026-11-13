"""Offline source adapters. Unknown local clocks never become invented UTC instants."""

import csv
import hashlib
import io
import math
import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

Dataset = Literal["ohio", "physiocgm", "azt1d", "uom"]
Kind = Literal[
    "glucose",
    "carbohydrate",
    "bolus",
    "basal",
    "temporary_basal",
    "exercise",
    "sleep",
    "work",
    "sensor_sleep",
]


@dataclass(frozen=True)
class OfflineEvent:
    dataset: Dataset
    participant: str
    partition: str
    kind: Kind
    time: datetime
    original_time: str
    value: float | None
    unit: str
    source_sha256: str
    source_row: int
    end_time: datetime | None = None
    # Event time does not establish logging/availability time.
    available_at: datetime | None = None
    observation_status: Literal["recorded", "blank", "zero_encoding_unverified"] = "recorded"
    glucose_type: Literal["cgm", "unverified_cgm_or_bgm"] = "cgm"
    device_mode: str | None = None
    intensity: float | None = None
    insulin_type: str | None = None

    @property
    def timezone_known(self) -> bool:
        return self.time.tzinfo is not None

    @property
    def scope(self) -> tuple[str, str]:
        return self.dataset, self.participant


@dataclass(frozen=True)
class SourceData:
    events: tuple[OfflineEvent, ...]
    rejected_rows: int
    source_sha256: str


def parse_source_time(raw: str, dataset: Dataset) -> datetime:
    text = raw.strip()
    if not text:
        raise ValueError("Missing source timestamp")
    if dataset == "ohio":
        return datetime.strptime(text, "%d-%m-%Y %H:%M:%S")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        # Dexcom exports can use an unpadded hour.
        return datetime.strptime(text, "%Y-%m-%d %H:%M:%S")


def number(raw: str | None, *, positive: bool = False) -> float | None:
    if raw is None or not raw.strip():
        return None
    value = float(raw)
    if not math.isfinite(value) or value < 0 or (positive and value == 0):
        raise ValueError("Invalid source measurement")
    return value


def read_ohio(archive_path: Path, *, extended_context: bool = False) -> tuple[SourceData, ...]:
    output = []
    mapping: dict[str, tuple[Kind, str, str]] = {
        "glucose_level": ("glucose", "value", "mg/dL"),
        "meal": ("carbohydrate", "carbs", "g"),
        "bolus": ("bolus", "dose", "U"),
        "basal": ("basal", "value", "U/hour"),
        "temp_basal": ("temporary_basal", "value", "U/hour"),
        "exercise": ("exercise", "duration", "minutes"),
    }
    if extended_context:
        mapping.update(
            {
                "sleep": ("sleep", "quality", "ordinal"),
                "work": ("work", "intensity", "ordinal"),
                "basis_sleep": ("sensor_sleep", "quality", "ordinal"),
            }
        )
    with zipfile.ZipFile(archive_path) as archive:
        members = archive.infolist()
        if len(members) > 100 or sum(m.file_size for m in members) > 150_000_000:
            raise ValueError("Archive exceeds source-adapter limits")
        for member in sorted(members, key=lambda m: m.filename):
            if not member.filename.endswith(".xml"):
                continue
            match = re.fullmatch(r"(\d+)-ws-(training|testing)\.xml", Path(member.filename).name)
            if match is None or member.file_size > 15_000_000:
                raise ValueError("Unexpected Ohio file")
            raw = archive.read(member)
            if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
                raise ValueError("XML declarations are unsupported")
            root = ET.fromstring(raw)
            participant, partition = match.groups()
            if root.tag != "patient" or root.get("id") != participant:
                raise ValueError("Source identity mismatch")
            sha = hashlib.sha256(raw).hexdigest()
            events, rejected = [], 0
            row_number = 0
            for section in root:
                if section.tag not in mapping:
                    continue
                kind, field, unit = mapping[section.tag]
                for row in section:
                    row_number += 1
                    try:
                        original = row.get("ts") or row.get("ts_begin") or row.get("tbegin") or ""
                        when = parse_source_time(original, "ohio")
                        raw_end = row.get("ts_end") or row.get("tend")
                        end = parse_source_time(raw_end, "ohio") if raw_end else None
                        if end is not None and end < when:
                            raise ValueError("Reversed event interval")
                        value = (
                            None
                            if kind == "sensor_sleep"
                            else number(row.get(field), positive=kind == "glucose")
                        )
                        if kind == "glucose" and value is None:
                            raise ValueError("Missing glucose")
                        if kind in {"sleep", "work", "sensor_sleep"} and (
                            end is None or end == when
                        ):
                            raise ValueError("Missing or empty interval")
                        intensity = None
                        if extended_context and kind in {"exercise", "work"}:
                            reported = row.get("intensity")
                            if reported and reported.isdecimal() and 1 <= int(reported) <= 10:
                                intensity = float(reported)
                    except (ValueError, KeyError):
                        rejected += 1
                        continue
                    events.append(
                        OfflineEvent(
                            "ohio",
                            participant,
                            partition,
                            kind,
                            when,
                            original,
                            value,
                            unit,
                            sha,
                            row_number,
                            end,
                            intensity=intensity,
                            insulin_type=root.get("insulin_type")
                            if extended_context and kind == "bolus"
                            else None,
                        )
                    )
            output.append(SourceData(tuple(events), rejected, sha))
    return tuple(output)


def read_physiocgm(path: Path) -> SourceData:
    if path.stat().st_size > 4_000_000:
        raise ValueError("CGM file exceeds source-adapter limit")
    raw = path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    events, rejected = [], 0
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    if not {"Event Type", "Timestamp (YYYY-MM-DDThh:mm:ss)", "Glucose Value (mg/dL)"} <= set(
        reader.fieldnames or []
    ):
        raise ValueError("Unexpected PhysioCGM columns")
    for index, row in enumerate(reader, 1):
        if row.get("Event Type") != "EGV":
            continue
        # Other event types are not glucose measurements; do not convert blanks to zero.
        raw_value = row.get("Glucose Value (mg/dL)", "")
        if not raw_value or not raw_value.strip():
            continue
        try:
            original = row.get("Timestamp (YYYY-MM-DDThh:mm:ss)", "")
            when = parse_source_time(original, "physiocgm")
            value = number(raw_value, positive=True)
        except ValueError:
            rejected += 1
            continue
        events.append(
            OfflineEvent(
                "physiocgm",
                path.stem,
                "unsplit",
                "glucose",
                when,
                original,
                value,
                "mg/dL",
                sha,
                index,
            )
        )
    return SourceData(tuple(events), rejected, sha)


def read_azt1d(archive_path: Path) -> tuple[SourceData, ...]:
    """Read canonical participant CSVs from the inner official ZIP, not analysis exports."""
    output = []
    with zipfile.ZipFile(archive_path) as archive:
        members = [
            m
            for m in archive.infolist()
            if not m.filename.startswith("__MACOSX/")
            and re.fullmatch(r"AZT1D 2025/CGM Records/Subject (\d+)/Subject \1\.csv", m.filename)
        ]
        if not members or len(members) > 100:
            raise ValueError("Unexpected AZT1D participant inventory")
        for member in sorted(members, key=lambda m: m.filename):
            if member.file_size > 10_000_000:
                raise ValueError("AZT1D CSV exceeds source-adapter limit")
            raw = archive.read(member)
            sha = hashlib.sha256(raw).hexdigest()
            participant = Path(member.filename).stem.removeprefix("Subject ")
            reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
            required = {"EventDateTime", "CarbSize", "TotalBolusInsulinDelivered", "Basal"}
            if not required <= set(reader.fieldnames or []):
                raise ValueError("Unexpected AZT1D columns")
            glucose_field = "CGM" if "CGM" in (reader.fieldnames or []) else "Readings (CGM / BGM)"
            if glucose_field not in (reader.fieldnames or []):
                raise ValueError("Missing AZT1D glucose column")
            events, rejected = [], 0
            for index, row in enumerate(reader, 1):
                try:
                    original = row.get("EventDateTime") or ""
                    when = parse_source_time(original, "azt1d")
                except ValueError:
                    rejected += 1
                    continue
                fields: tuple[tuple[str, Kind, str], ...] = (
                    (glucose_field, "glucose", "mg/dL"),
                    ("CarbSize", "carbohydrate", "g"),
                    ("TotalBolusInsulinDelivered", "bolus", "U"),
                    # The adapter preserves this source field without guessing its rate unit.
                    ("Basal", "basal", "source_unit_unverified"),
                )
                for field, kind, unit in fields:
                    try:
                        value = number(row.get(field), positive=kind == "glucose")
                    except ValueError:
                        rejected += 1
                        continue
                    if kind == "glucose" and value is None:
                        continue
                    status: Literal["recorded", "blank", "zero_encoding_unverified"] = "recorded"
                    if value is None:
                        status = "blank"
                    elif value == 0 and kind in {"carbohydrate", "bolus"}:
                        # Publisher uses zero for absent event records. Preserve ambiguity;
                        # this cannot establish complete observation or a true zero exposure.
                        status, value = "zero_encoding_unverified", None
                    events.append(
                        OfflineEvent(
                            "azt1d",
                            participant,
                            "unsplit",
                            kind,
                            when,
                            original,
                            value,
                            unit,
                            sha,
                            index,
                            observation_status=status,
                            device_mode=row.get("DeviceMode") or None,
                            glucose_type="unverified_cgm_or_bgm"
                            if kind == "glucose" and glucose_field != "CGM"
                            else "cgm",
                        )
                    )
            output.append(SourceData(tuple(events), rejected, sha))
    return tuple(output)


def elapsed_seconds(first: OfflineEvent, second: OfflineEvent) -> float:
    if first.scope != second.scope:
        raise ValueError("Elapsed time requires the same dataset and participant")
    if first.timezone_known != second.timezone_known:
        raise ValueError("Mixed known and unknown clocks require review")
    return (second.time - first.time).total_seconds()
