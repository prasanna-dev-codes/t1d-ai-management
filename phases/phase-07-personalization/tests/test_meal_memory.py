"""Check the shared ranking component and the offline meal-memory boundary."""

from dataclasses import replace
from datetime import timedelta

import numpy as np
import pytest
from adaptation import WARMUP, replay
from evaluate import MEAL_ROUTED, Evaluation, route_meal_memory
from meal_memory import METHOD, MealAnchor, matches, meal_anchors
from t1d_forecasting.datasets import OfflineEvent
from t1d_memory.episodes import build_episodes, foods_and_nutrients
from t1d_memory.ranking import rank, relative_amount_distance
from t1d_memory.synthetic import PATIENT, START, STUDY, cohort, meal
from test_adaptation import START as LOCAL_START
from test_adaptation import row


def test_shared_carbohydrate_distance_matches_phase05_structured_ranking() -> None:
    anchor = meal(8, carbs="30")
    content = foods_and_nutrients(anchor)
    assert content is not None
    foods, nutrients = content
    episodes, _ = build_episodes(cohort(8), anchor.event_time, STUDY, PATIENT)
    evidence = rank(episodes, foods, nutrients, "structured-v1", 5)
    assert len(evidence) == 5
    by_id = {episode.id: episode for episode in episodes}
    for item in evidence:
        amount = float(by_id[item.episode_id].nutrients.carbohydrate_g)
        assert item.score == pytest.approx(1 - relative_amount_distance(30, amount) / 3)
        assert item.available_at <= anchor.event_time
    assert evidence[0].score == 1
    assert START < evidence[0].event_time < anchor.event_time


def test_meals_must_be_observed_scoped_and_unambiguous_at_cutoff() -> None:
    target = row(0)
    when = target.cutoff - timedelta(minutes=30)
    known = OfflineEvent(
        "ohio",
        target.participant,
        target.partition,
        "carbohydrate",
        when,
        "",
        30.0,
        "g",
        "fixture",
        1,
        available_at=when,
    )
    late = replace(known, source_row=2, available_at=target.cutoff + timedelta(seconds=1))
    foreign = replace(known, source_row=3, participant="other")
    other_partition = replace(known, source_row=4, partition="testing")
    missing = replace(known, source_row=5, available_at=None)
    anchors = meal_anchors(
        [known, late, foreign, other_partition, missing], [target], allow_event_time_replay=False
    )
    assert anchors[target.input_ref].reference == ("fixture", 1)
    assert meal_anchors([missing], [target], allow_event_time_replay=False) == {}
    assert meal_anchors([known, missing], [target], allow_event_time_replay=True) == {}


def test_retrieval_counts_each_earlier_meal_once() -> None:
    query = MealAnchor(("fixture", 5), LOCAL_START + WARMUP, 30, 40)
    previous = [
        MealAnchor(("fixture", number), LOCAL_START + timedelta(hours=number), 30, 40)
        for number in range(3)
    ]
    anchors = previous + [previous[0], query]
    picked = matches(query, [0, 1, 2, 3, 4], anchors)
    assert {index for index, _ in picked} == {0, 1, 2}
    assert matches(query, [0, 1, 3, 4], anchors) == []


def test_routing_changes_only_forecasts_with_memory_support() -> None:
    track = Evaluation(meal_support=[False, True])
    track.predictions["frozen-v5"] = [[100.0] * 4, [110.0] * 4]
    track.predictions["context-offset"] = [[115.0] * 4, [125.0] * 4]
    track.predictions[METHOD] = [[115.0] * 4, [135.0] * 4]
    route_meal_memory(track, ["frozen-v5", "frozen-v5", "context-offset", "context-offset"])
    assert track.points(MEAL_ROUTED).tolist() == [
        [100.0, 100.0, 115.0, 115.0],
        [135.0, 135.0, 135.0, 135.0],
    ]


def test_memory_correction_uses_only_matured_forecast_feedback() -> None:
    history = [row(hour) for hour in range(25)]
    current = row(168, glucose=900)
    query = MealAnchor(("fixture", 100), current.cutoff - timedelta(minutes=30), 30, 40)
    anchors = [
        MealAnchor(("fixture", i), item.cutoff - timedelta(minutes=30), 30, 40)
        if i % 4 == 0
        else None
        for i, item in enumerate(history)
    ]
    # The later-available version exists in the input but cannot enter this forecast.
    late = replace(
        history[0],
        targets=(900.0,) * 4,
        label_available_at=current.cutoff + timedelta(seconds=1),
    )
    modified = [late, *history[1:]]
    allowed = [True] * 26
    baseline = np.full((26, 4), 100.0)
    result = replay(
        modified + [current], baseline, LOCAL_START + WARMUP, allowed, anchors + [query]
    )
    without_late = replay(
        modified + [current],
        baseline,
        LOCAL_START + WARMUP,
        [False, *allowed[1:]],
        anchors + [query],
    )
    assert result.meal_support[-1]
    assert result.predictions[METHOD][-1] == pytest.approx(without_late.predictions[METHOD][-1])
    assert result.predictions[METHOD][-1] == pytest.approx([115.0] * 4)
