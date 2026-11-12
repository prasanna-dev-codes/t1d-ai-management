"""Offline comparison of Phase 05's carbohydrate distance on recorded meals."""

import math
from bisect import bisect_left, bisect_right
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from t1d_forecasting.datasets import OfflineEvent
from t1d_forecasting.windows import Window
from t1d_memory.contracts import DEFINITION
from t1d_memory.ranking import relative_amount_distance

METHOD = "meal-memory-offset"
_WINDOW = timedelta(minutes=DEFINITION.response_minutes)
_LIMIT = 5
_MIN_MATCHES = 3


@dataclass(frozen=True)
class MealAnchor:
    reference: tuple[str, int]
    event_time: datetime
    age_minutes: float
    carbs_g: float


def meal_anchors(
    events: list[OfflineEvent], windows: list[Window], *, allow_event_time_replay: bool
) -> dict[str, MealAnchor]:
    groups: dict[tuple[str, str], list[OfflineEvent]] = defaultdict(list)
    for event in events:
        if (
            event.kind == "carbohydrate"
            and event.unit == "g"
            and event.observation_status == "recorded"
            and event.value is not None
            and math.isfinite(event.value)
            and event.value > 0
            and (event.available_at is not None or allow_event_time_replay)
        ):
            groups[f"{event.dataset}:{event.participant}", event.partition].append(event)
    for meals in groups.values():
        meals.sort(key=lambda event: event.time)
    times = {key: [event.time for event in meals] for key, meals in groups.items()}
    anchors = {}
    for window in windows:
        key = window.scope, window.partition
        if key not in groups:
            continue
        left = bisect_left(times[key], window.cutoff - _WINDOW)
        right = bisect_right(times[key], window.cutoff)
        known = [
            event
            for event in groups[key][left:right]
            if (event.available_at is None or event.available_at <= window.cutoff)
            and (event.end_time is None or event.end_time <= window.cutoff)
        ]
        if len(known) != 1:
            continue
        meal = known[0]
        assert meal.value is not None
        anchors[window.input_ref] = MealAnchor(
            (meal.source_sha256, meal.source_row),
            meal.time,
            (window.cutoff - meal.time).total_seconds() / 60,
            meal.value,
        )
    return anchors


def matches(
    query: MealAnchor, candidates: Sequence[int], anchors: Sequence[MealAnchor | None]
) -> list[tuple[int, float]]:
    """Rank matured forecast histories without reading their glucose outcomes."""
    best: dict[tuple[str, int], tuple[int, float]] = {}
    for index in candidates:
        item = anchors[index]
        if item is None or item.reference == query.reference or item.event_time >= query.event_time:
            continue
        carb_distance = relative_amount_distance(query.carbs_g, item.carbs_g)
        age_distance = abs(query.age_minutes - item.age_minutes) / DEFINITION.response_minutes
        score = 1 - (0.75 * carb_distance + 0.25 * age_distance)
        prior = best.get(item.reference)
        if score >= 0.6 and (prior is None or score > prior[1]):
            best[item.reference] = (index, score)
    if len(best) < _MIN_MATCHES:
        return []
    return sorted(best.values(), key=lambda candidate: (-candidate[1], -candidate[0]))[:_LIMIT]
