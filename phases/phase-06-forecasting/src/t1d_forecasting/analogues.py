"""Find similar completed CGM trajectories in a participant's observed history."""

import hashlib
from bisect import bisect_left, bisect_right
from collections import defaultdict
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any

import numpy as np

from t1d_forecasting.windows import HISTORY_FEATURE_NAMES, Window

# The matching features look back no more than two hours from the earlier anchor.
# This keeps the full transform inside the existing 48-hour validation embargo.
ANALOGUE_LOOKBACK = timedelta(hours=46)
RESPONSE_GAP = timedelta(hours=1)
ANALOGUE_FEATURE_VERSION = "offline-causal-analogues-v5"
ANALOGUE_FEATURE_NAMES = (
    HISTORY_FEATURE_NAMES
    + tuple(
        f"analogue_{kind}_{minutes}"
        for kind in ("matched_change", "recent_median_change", "matched_dispersion")
        for minutes in (30, 60, 90, 120)
    )
    + ("analogue_count_scaled", "analogue_distance", "analogue_present")
)
_MATCH_FEATURES = (
    ("glucose_lag_0_scaled", 0.45),
    ("cgm_change_15", 0.17),
    ("cgm_change_30", 0.28),
    ("observed_slope_scaled", 0.10),
    ("observed_std_scaled", 0.23),
    ("recorded_clock_sine", 1.4),
    ("recorded_clock_cosine", 1.4),
    ("recorded_carbohydrate_120_scaled", 0.65),
    ("recorded_bolus_120_scaled", 0.45),
)
_MATCH_COLUMNS = tuple(HISTORY_FEATURE_NAMES.index(name) for name, _ in _MATCH_FEATURES)
_MATCH_SCALES = np.asarray([scale for _, scale in _MATCH_FEATURES])
_MATCHED = 12
_MINIMUM = 6
_MISSING = (0.0,) * (len(ANALOGUE_FEATURE_NAMES) - len(HISTORY_FEATURE_NAMES))


class AnalogueHistory:
    """Index one source partition. Query eligibility uses both event and availability time."""

    def __init__(self, windows: list[Window]) -> None:
        indexed = sorted(
            (
                (index, row)
                for index, row in enumerate(windows)
                if row.label_available_at is not None and not row.fit_only
            ),
            key=lambda pair: pair[1].cutoff,
        )
        rows = [row for _, row in indexed]
        identities = {(row.scope, row.partition) for row in rows}
        if len(identities) > 1:
            raise ValueError("Analogue history must stay inside one participant and partition")
        self.identity = next(iter(identities), None)
        self.times = [row.cutoff for row in rows]
        self.order = [index for index, _ in indexed]
        self.available = [
            max(row.label_available_at, row.label_end)
            for row in rows
            if row.label_available_at is not None
        ]
        inputs = np.asarray([row.features for row in rows], dtype=float).reshape(
            len(rows), len(HISTORY_FEATURE_NAMES)
        )
        self.inputs = inputs[:, _MATCH_COLUMNS] / _MATCH_SCALES
        self.changes = (
            np.asarray([row.targets for row in rows], dtype=float).reshape(len(rows), 4) / 100
            - inputs[:, 11:12]
        )

    def features(
        self,
        scope: str,
        partition: str,
        cutoff: datetime,
        current: tuple[float, ...],
        *,
        before_order: int | None = None,
    ) -> tuple[float, ...]:
        if self.identity is not None and self.identity != (scope, partition):
            raise ValueError("Analogue history has a foreign source scope")
        complete_by = cutoff - RESPONSE_GAP
        left = bisect_left(self.times, cutoff - ANALOGUE_LOOKBACK)
        right = bisect_right(self.times, complete_by)
        indices = [
            i
            for i in range(left, right)
            if self.available[i] <= complete_by
            and (before_order is None or self.order[i] < before_order)
        ]
        if len(indices) < _MINIMUM:
            return _MISSING
        query = np.asarray(current)[list(_MATCH_COLUMNS)] / _MATCH_SCALES
        distance = np.sum((self.inputs[indices] - query) ** 2, axis=1)
        closest = np.argsort(distance, kind="stable")[:_MATCHED]
        changes = self.changes[indices]
        neighbours = changes[closest]
        mass = 1 / (1 + distance[closest])
        mean = np.average(neighbours, axis=0, weights=mass)
        median = np.median(changes, axis=0)
        spread = np.sqrt(np.average((neighbours - mean) ** 2, axis=0, weights=mass))
        return tuple(float(value) for value in np.concatenate((mean, median, spread))) + (
            len(indices) / 100,
            float(np.sqrt(distance[closest[0]])),
            1.0,
        )


def add_analogue_features(windows: list[Window]) -> list[Window]:
    grouped: dict[tuple[str, str], list[Window]] = defaultdict(list)
    for row in windows:
        grouped[row.scope, row.partition].append(row)
    result: list[Window] = []
    for (scope, partition), rows in grouped.items():
        history = AnalogueHistory(rows)
        for index, row in enumerate(rows):
            extra = history.features(scope, partition, row.cutoff, row.features, before_order=index)
            identity = hashlib.sha256(
                repr((row.input_ref, ANALOGUE_FEATURE_VERSION, extra)).encode()
            ).hexdigest()
            result.append(replace(row, features=row.features + extra, input_ref=identity))
    return result


def active_analogues(matrix: Any) -> Any:
    return matrix[:, ANALOGUE_FEATURE_NAMES.index("analogue_present")] == 1
