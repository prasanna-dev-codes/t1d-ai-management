"""Offline, participant-local correction of frozen four-horizon forecasts."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import numpy as np
from meal_memory import METHOD as MEAL_MEMORY
from meal_memory import MealAnchor, matches
from t1d_forecasting.windows import HISTORY_FEATURE_NAMES, Window

WARMUP = timedelta(days=7)
ROLLING_LOOKBACK = timedelta(days=14)
METHODS = ("frozen-v5", "initial-offset", "rolling-offset", "context-offset")
LAG_METHOD = "recorded-event-timing-offset"
_MIN_HISTORY = 24
_MIN_CONTEXT = 16
_SHRINKAGE = 48
_MAX_CORRECTION = 15.0


@dataclass(frozen=True)
class Replay:
    predictions: dict[str, Any]
    rolling_support: Any
    context_support: Any
    meal_support: Any
    recent_error: Any


@dataclass(frozen=True)
class ForecastQuery:
    scope: str
    cutoff: datetime
    features: tuple[float, ...]


def _context(inputs: list[tuple[float, ...]]) -> Any:
    features = np.asarray(inputs)
    slope = features[:, HISTORY_FEATURE_NAMES.index("cgm_change_15")]
    trend = np.where(slope >= 0.15, 1, np.where(slope <= -0.15, -1, 0))
    carbs = features[:, HISTORY_FEATURE_NAMES.index("recorded_carbs_240_present")] == 1
    exercise = (
        features[:, HISTORY_FEATURE_NAMES.index("reported_exercise_after_bolus_present")] == 1
    )
    return np.column_stack((trend, carbs, exercise))


def _recorded_timing(inputs: list[tuple[float, ...]], context: Any) -> Any:
    features = np.asarray(inputs)
    groups = []
    for event in ("carbs", "bolus"):
        kind = "carbohydrate" if event == "carbs" else event
        recent = features[:, HISTORY_FEATURE_NAMES.index(f"recorded_{kind}_60_present")] == 1
        earlier = features[:, HISTORY_FEATURE_NAMES.index(f"recorded_{event}_240_present")] == 1
        groups.append(np.where(recent, 2, np.where(earlier, 1, 0)))
    return np.column_stack((*groups, context[:, 0], context[:, 2]))


def replay(
    rows: list[Window],
    baseline: Any,
    warm_until: datetime,
    feedback_allowed: list[bool],
    meals: list[MealAnchor | None] | None = None,
    *,
    estimate_recent_error: bool = False,
    query: ForecastQuery | None = None,
    recorded_timing: bool = False,
) -> Replay:
    """Use observed errors only after their outcome windows and source availability mature."""
    points = np.asarray(baseline, dtype=float)
    cutoffs = [row.cutoff for row in rows]
    inputs = [row.features for row in rows]
    scopes = {row.scope for row in rows}
    if query is not None:
        if cutoffs and query.cutoff <= cutoffs[-1]:
            raise ValueError("Forecast query must follow its feedback history")
        cutoffs.append(query.cutoff)
        inputs.append(query.features)
        scopes.add(query.scope)
    if (
        not cutoffs
        or len(scopes) != 1
        or len({(row.partition, row.cutoff) for row in rows}) != len(rows)
        or len(feedback_allowed) != len(rows)
        or (meals is not None and len(meals) != len(cutoffs))
        or any(row.label_end <= row.cutoff for row in rows)
        or any(a.cutoff > b.cutoff for a, b in zip(rows, rows[1:], strict=False))
        or points.shape != (len(cutoffs), 4)
        or not np.isfinite(points).all()
        or (points <= 0).any()
    ):
        raise ValueError("Invalid chronological single-participant replay")
    target = np.asarray([row.targets for row in rows]) if rows else np.empty((0, 4))
    if target.shape != (len(rows), 4) or not np.isfinite(target).all() or (target <= 0).any():
        raise ValueError("Invalid reference glucose observations")
    residual = target - points[: len(rows)]
    context = _context(inputs)
    timing = _recorded_timing(inputs, context) if recorded_timing else None
    feedback: list[tuple[datetime, int]] = []
    for index, row in enumerate(rows):
        available = row.label_available_at
        if feedback_allowed[index] and available is not None:
            feedback.append((max(available, row.label_end), index))
    feedback.sort()
    initial = [i for known, i in feedback if known <= warm_until]
    initial_offset = (
        np.clip(
            np.median(residual[initial], axis=0) * len(initial) / (len(initial) + _SHRINKAGE),
            -_MAX_CORRECTION,
            _MAX_CORRECTION,
        )
        if len(initial) >= _MIN_HISTORY
        else np.zeros(4)
    )
    forecasts = {method: points.copy() for method in METHODS}
    if meals is not None:
        forecasts[MEAL_MEMORY] = points.copy()
    if timing is not None:
        forecasts[LAG_METHOD] = points.copy()
    rolling_support = np.zeros(len(cutoffs), dtype=bool)
    context_support = np.zeros(len(cutoffs), dtype=bool)
    meal_support = np.zeros(len(cutoffs), dtype=bool)
    recent_error = np.full(points.shape, np.nan)
    next_feedback = 0
    active: list[int] = []
    for index, cutoff in enumerate(cutoffs):
        if cutoff < warm_until:
            continue
        while next_feedback < len(feedback) and feedback[next_feedback][0] <= cutoff:
            active.append(feedback[next_feedback][1])
            next_feedback += 1
        oldest = cutoff - ROLLING_LOOKBACK
        active = [i for i in active if rows[i].label_end >= oldest]
        forecasts["initial-offset"][index] += initial_offset
        if len(active) < _MIN_HISTORY:
            continue
        rolling_support[index] = True
        if estimate_recent_error:
            recent_error[index] = np.quantile(np.abs(residual[active]), 0.8, axis=0)
        rolling_median = np.median(residual[active], axis=0)
        rolling = rolling_median * len(active) / (len(active) + _SHRINKAGE)
        forecasts["rolling-offset"][index] += np.clip(rolling, -_MAX_CORRECTION, _MAX_CORRECTION)
        matching = np.asarray(active)[np.all(context[active] == context[index], axis=1)]
        correction = rolling
        if len(matching) >= _MIN_CONTEXT:
            context_support[index] = True
            median = np.median(residual[matching], axis=0)
            correction = rolling + (median - rolling_median) * len(matching) / (
                len(matching) + _SHRINKAGE
            )
        forecasts["context-offset"][index] += np.clip(correction, -_MAX_CORRECTION, _MAX_CORRECTION)
        if timing is not None:
            timing_offset = correction
            if timing[index, :2].any():
                similar = np.asarray(active)[np.all(timing[active] == timing[index], axis=1)]
                if len(similar) >= _MIN_CONTEXT:
                    evidence = np.median(residual[similar], axis=0)
                    share = len(similar) / (len(similar) + _SHRINKAGE)
                    timing_offset = (1 - share) * correction + share * evidence
            forecasts[LAG_METHOD][index] += np.clip(
                timing_offset, -_MAX_CORRECTION, _MAX_CORRECTION
            )
        if meals is not None:
            meal_query = meals[index]
            retrieved = matches(meal_query, active, meals) if meal_query is not None else []
            if retrieved:
                meal_support[index] = True
                indices, scores = zip(*retrieved, strict=True)
                estimate = np.average(residual[list(indices)], axis=0, weights=scores)
                contribution = len(retrieved) / (len(retrieved) + 8)
                correction = (1 - contribution) * correction + contribution * estimate
            forecasts[MEAL_MEMORY][index] += np.clip(correction, -_MAX_CORRECTION, _MAX_CORRECTION)
    for prediction in forecasts.values():
        prediction[prediction <= 0] = points[prediction <= 0]
    return Replay(forecasts, rolling_support, context_support, meal_support, recent_error)
