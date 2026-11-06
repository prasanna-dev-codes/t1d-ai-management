"""Offline, participant-scoped windows with causal inputs and explicit context masks."""

import hashlib
import math
import statistics
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta

from t1d_forecasting.datasets import OfflineEvent, SourceData

CGM_FEATURES = tuple(f"glucose_lag_{i}_scaled" for i in range(11, -1, -1)) + (
    "observed_mean_scaled",
    "observed_std_scaled",
    "observed_slope_scaled",
)
CONTEXT_FEATURES = tuple(
    field
    for kind in ("carbohydrate", "bolus", "exercise")
    for duration in (30, 60, 120)
    for field in (f"recorded_{kind}_{duration}_scaled", f"recorded_{kind}_{duration}_present")
) + ("last_basal_rate_scaled", "basal_rate_present", "sleep_mode", "exercise_mode", "mode_present")
FEATURE_NAMES = CGM_FEATURES + CONTEXT_FEATURES
FEATURE_VERSION = "offline-local12-context-mask-replay-v1"


@dataclass(frozen=True)
class Window:
    dataset: str
    participant: str
    partition: str
    input_start: datetime
    cutoff: datetime
    label_end: datetime
    features: tuple[float, ...]
    targets: tuple[float, ...]
    input_ref: str

    @property
    def scope(self) -> str:
        return self.dataset + ":" + self.participant


def _context(
    history: list[OfflineEvent],
    times: list[datetime],
    anchor: OfflineEvent,
    allow_event_time_replay: bool = False,
) -> list[float]:
    cutoff = anchor.time
    left = bisect_left(times, cutoff - timedelta(minutes=120))
    right = bisect_right(times, cutoff)
    recent = [
        e
        for e in history[left:right]
        if (e.available_at is not None and e.available_at <= cutoff)
        or (allow_event_time_replay and e.available_at is None)
    ]
    output: list[float] = []
    for kind, scale in (("carbohydrate", 100.0), ("bolus", 10.0), ("exercise", 60.0)):
        for duration in (30, 60, 120):
            known = [
                e
                for e in recent
                if e.kind == kind
                and e.value is not None
                and e.time >= cutoff - timedelta(minutes=duration)
                and (e.end_time is None or e.end_time <= cutoff)
                and (kind != "exercise" or e.time + timedelta(minutes=e.value) <= cutoff)
            ]
            # Zero is a numeric placeholder with a mask, never verified zero exposure.
            output.extend(
                (
                    sum(float(e.value) for e in known if e.value is not None) / scale,
                    float(bool(known)),
                )
            )
    rates = [e for e in recent if e.kind == "basal" and e.unit == "U/hour" and e.value is not None]
    if any(
        e.kind == "temporary_basal" and (e.end_time is None or e.end_time > cutoff) for e in recent
    ):
        rates = []  # Do not claim the normal rate while a temporary override is active.
    output.extend((float(rates[-1].value) / 10.0 if rates else 0.0, float(bool(rates))))  # type: ignore[arg-type]
    mode_known = allow_event_time_replay or (
        anchor.available_at is not None and anchor.available_at <= cutoff
    )
    mode = (anchor.device_mode or "").casefold().strip() if mode_known else ""
    output.extend((float(mode == "sleep"), float(mode == "exercise"), float(bool(mode))))
    return output


def make_windows(
    sources: tuple[SourceData, ...], stride: int = 6, *, allow_event_time_replay: bool = False
) -> tuple[list[Window], dict[str, int]]:
    if not 1 <= stride <= 36:
        raise ValueError("Bounded positive stride required")
    groups: dict[tuple[str, str, str], list[OfflineEvent]] = defaultdict(list)
    for source in sources:
        for event in source.events:
            groups[event.dataset, event.participant, event.partition].append(event)
    windows = []
    counts: Counter[str] = Counter()
    for (_, _, _), events in sorted(groups.items()):
        if len({e.timezone_known for e in events}) > 1:
            raise ValueError("Mixed clock representations require review")
        glucose = [
            e
            for e in events
            if e.kind == "glucose" and e.value is not None and e.glucose_type == "cgm"
        ]
        counts["ambiguous_glucose_excluded"] += sum(
            e.kind == "glucose" and e.glucose_type != "cgm" for e in events
        )
        values: dict[datetime, set[float]] = defaultdict(set)
        for e in glucose:
            assert e.value is not None
            values[e.time].add(e.value)
        conflicts = {time for time, data in values.items() if len(data) > 1}
        counts["conflicting_timestamps_excluded"] += len(conflicts)
        seen: set[datetime] = set()
        segments: list[list[OfflineEvent]] = [[]]
        for event in glucose:
            if event.time in conflicts:
                continue
            if event.time in seen:
                counts["identical_timestamp_duplicates_collapsed"] += 1
                continue
            seen.add(event.time)
            if segments[-1]:
                gap = (event.time - segments[-1][-1].time).total_seconds()
                # Keep measured timestamps: tolerate at most five seconds of cadence jitter.
                if not 295 <= gap <= 305:
                    counts["cadence_or_clock_breaks"] += 1
                    segments.append([])
            segments[-1].append(event)
        context = sorted((e for e in events if e.kind != "glucose"), key=lambda e: e.time)
        context_times = [e.time for e in context]
        for segment in segments:
            counts["verified_glucose_records"] += len(segment)
            for index in range(11, len(segment) - 24, stride):
                counts["candidate_windows"] += 1
                inputs = segment[index - 11 : index + 1]
                labels = [segment[index + h] for h in (6, 12, 18, 24)]
                anchor = inputs[-1]
                if any(
                    abs((e.time - anchor.time).total_seconds() - h * 60) > 5
                    for e, h in zip(labels, (30, 60, 90, 120), strict=True)
                ):
                    counts["horizon_alignment_excluded"] += 1
                    continue
                observed = [float(e.value) for e in inputs if e.value is not None]
                offsets = [(e.time - anchor.time).total_seconds() / 60 for e in inputs]
                mx, my = statistics.mean(offsets), statistics.mean(observed)
                denominator = sum((x - mx) ** 2 for x in offsets)
                slope = (
                    sum((x - mx) * (y - my) for x, y in zip(offsets, observed, strict=True))
                    / denominator
                )
                features = [v / 100 for v in observed] + [
                    my / 100,
                    statistics.pstdev(observed) / 100,
                    slope / 10,
                ]
                features.extend(_context(context, context_times, anchor, allow_event_time_replay))
                if len(features) != len(FEATURE_NAMES) or not all(
                    math.isfinite(v) for v in features
                ):
                    raise ValueError("Invalid offline features")
                lineage = [(e.source_sha256, e.source_row) for e in inputs]
                # Input fingerprint includes context features, masks and raw source hashes.
                ref = hashlib.sha256(
                    repr((lineage, features, FEATURE_VERSION, allow_event_time_replay)).encode()
                ).hexdigest()
                windows.append(
                    Window(
                        anchor.dataset,
                        anchor.participant,
                        anchor.partition,
                        min(inputs[0].time, anchor.time - timedelta(minutes=120)),
                        anchor.time,
                        labels[-1].time,
                        tuple(features),
                        tuple(float(e.value) for e in labels if e.value is not None),
                        ref,
                    )
                )
    counts["accepted_windows"] = len(windows)
    return windows, dict(counts)


def patient_partitions(
    windows: list[Window], external: str | None = None
) -> dict[str, list[Window]]:
    """Patient-disjoint calibration/test; chronological validation inside fit patients."""
    by_dataset: dict[str, set[str]] = defaultdict(set)
    for w in windows:
        by_dataset[w.dataset].add(w.scope)
    roles: dict[str, str] = {}
    for dataset, subjects in sorted(by_dataset.items()):
        ordered = sorted(
            subjects, key=lambda s: hashlib.sha256(("patient-split-v1:" + s).encode()).hexdigest()
        )
        if dataset == external:
            roles.update({s: "test" for s in ordered})
        else:
            calibration = 5 if external else 3
            testing = 0 if external else 3
            if len(ordered) <= calibration + testing:
                raise ValueError("Insufficient patients for declared protocol")
            roles.update({s: "fit" for s in ordered[: len(ordered) - calibration - testing]})
            roles.update(
                {
                    s: "calibration"
                    for s in ordered[
                        len(ordered) - calibration - testing : len(ordered) - testing
                        if testing
                        else None
                    ]
                }
            )
            if testing:
                roles.update({s: "test" for s in ordered[-testing:]})
    train_by_subject: dict[str, list[Window]] = defaultdict(list)
    result: dict[str, list[Window]] = {
        key: [] for key in ("fit", "validation", "calibration", "test")
    }
    for w in windows:
        if roles[w.scope] == "fit":
            # Preserve the supplied Ohio testing files, including for model selection.
            if w.partition != "testing":
                train_by_subject[w.scope].append(w)
        else:
            if roles[w.scope] == "calibration" and w.partition == "testing":
                continue  # Official Ohio test labels never calibrate a model.
            result[roles[w.scope]].append(w)
    for rows in train_by_subject.values():
        rows.sort(key=lambda w: w.cutoff)
        boundary = rows[int(0.8 * len(rows))].cutoff
        result["fit"].extend(w for w in rows if w.label_end < boundary)
        result["validation"].extend(w for w in rows if w.input_start >= boundary)
    if not all(result.values()):
        raise ValueError("An evaluation partition is empty")
    sets = {role: {w.scope for w in rows} for role, rows in result.items()}
    if (sets["fit"] | sets["validation"]) & (sets["calibration"] | sets["test"]) or sets[
        "calibration"
    ] & sets["test"]:
        raise ValueError("Patient split violation")
    return result
