"""Offline 15-minute research windows built only from measured CGM."""

import hashlib
from collections import Counter, defaultdict
from datetime import timedelta

from t1d_forecasting.datasets import OfflineEvent, SourceData
from t1d_forecasting.windows import Window, _context, glucose_segments

HORIZONS = (30, 60, 90, 120)
HISTORY_READINGS = 8
CGM_COLUMNS = HISTORY_READINGS + 4
CADENCE_VERSION = "offline-observed-cgm-15min-context-v1"


def make_cadence_windows(
    sources: tuple[SourceData, ...], *, native: bool
) -> tuple[list[Window], dict[str, int]]:
    """Decimate intact five-minute runs for training or use native 15-minute runs."""
    groups: dict[tuple[str, str, str], list[OfflineEvent]] = defaultdict(list)
    for source in sources:
        for event in source.events:
            groups[event.dataset, event.participant, event.partition].append(event)
    windows = []
    counts: Counter[str] = Counter()
    offsets = tuple(h // 15 for h in HORIZONS)
    for events in groups.values():
        if len({e.timezone_known for e in events}) > 1:
            raise ValueError("Mixed clock representations require review")
        segment_counts: Counter[str] = Counter()
        segments = glucose_segments(events, 900 if native else 300, segment_counts)
        if native:
            five = glucose_segments(events, 300, Counter())
            if sum(len(s) - 1 for s in segments) <= sum(len(s) - 1 for s in five):
                counts["non_native_partitions_excluded"] += 1
                continue
        counts.update(segment_counts)
        context = sorted((e for e in events if e.kind != "glucose"), key=lambda e: e.time)
        times = [event.time for event in context]
        for segment in segments:
            measured = segment if native else segment[::3]
            for i in range(HISTORY_READINGS - 1, len(measured) - offsets[-1], 2):
                past = measured[i - HISTORY_READINGS + 1 : i + 1]
                labels = [measured[i + offset] for offset in offsets]
                anchor = past[-1]
                cutoff = anchor.time
                if any(
                    abs((e.time - cutoff).total_seconds() - j * 900) > 5
                    for e, j in zip(
                        past + labels, (*range(1 - HISTORY_READINGS, 1), *offsets), strict=True
                    )
                ):
                    counts["misaligned_windows_excluded"] += 1
                    continue
                if any(e.available_at is not None and e.available_at > cutoff for e in past):
                    counts["unavailable_windows_excluded"] += 1
                    continue
                glucose = [float(e.value) / 100 for e in past if e.value is not None]
                features = (
                    *glucose,
                    glucose[-1] - glucose[-2],
                    glucose[-1] - glucose[-3],
                    glucose[-1] - glucose[-5],
                    max(glucose) - min(glucose),
                    *_context(context, times, anchor, allow_event_time_replay=True),
                )
                lineage = [(e.source_sha256, e.source_row) for e in past]
                ref = hashlib.sha256(
                    repr((CADENCE_VERSION, lineage, features)).encode()
                ).hexdigest()
                windows.append(
                    Window(
                        anchor.dataset,
                        anchor.participant,
                        anchor.partition,
                        min(past[0].time, cutoff - timedelta(minutes=120)),
                        cutoff,
                        labels[-1].time,
                        features,
                        tuple(float(e.value) for e in labels if e.value is not None),
                        ref,
                    )
                )
    counts["accepted_windows"] = len(windows)
    return windows, dict(counts)
