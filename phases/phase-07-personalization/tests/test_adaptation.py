"""Verify cutoff handling, cold start and separation from official Ohio testing."""

from dataclasses import replace
from datetime import datetime, timedelta

import numpy as np
import pytest
from adaptation import WARMUP, replay
from evaluate import development_scopes, patient_tracks
from t1d_forecasting.windows import HISTORY_FEATURE_NAMES, Window

START = datetime(2020, 1, 1)
FEATURES = (0.0,) * len(HISTORY_FEATURE_NAMES)


def row(hours: int, *, glucose: float = 130.0, partition: str = "training") -> Window:
    cutoff = START + timedelta(hours=hours)
    outcome = cutoff + timedelta(hours=2)
    return Window(
        "ohio",
        "synthetic",
        partition,
        cutoff - timedelta(hours=48),
        cutoff,
        outcome,
        FEATURES,
        (glucose,) * 4,
        f"synthetic-{hours}",
        label_available_at=outcome,
    )


def test_feedback_waits_for_both_outcome_and_availability() -> None:
    old = [row(hour) for hour in range(24)]
    cutoff = START + WARMUP
    late = replace(row(166, glucose=280), label_available_at=cutoff + timedelta(hours=2))
    forged_early = replace(row(167, glucose=270), label_available_at=cutoff)
    current = row(168, glucose=900)
    rows = old + [late, forged_early, current]
    baseline = np.full((len(rows), 4), 100.0)
    result = replay(rows, baseline, cutoff, [True] * len(rows))
    expected = replay(old + [current], baseline[:-2], cutoff, [True] * (len(rows) - 2))
    for method, estimates in result.predictions.items():
        assert estimates[-1] == pytest.approx(expected.predictions[method][-1])
        assert (estimates[:24] == baseline[:24]).all()
    assert result.predictions["rolling-offset"][-1] == pytest.approx([110.0] * 4)


def test_unavailable_and_expired_history_falls_back_to_frozen_model() -> None:
    initial = [replace(row(hour), label_available_at=None) for hour in range(24)]
    expired = [row(hour + 25) for hour in range(24)]
    rows = initial + expired + [row(24 * 23)]
    base = np.full((len(rows), 4), 100.0)
    result = replay(rows, base, START + WARMUP, [True] * len(rows))
    assert result.predictions["rolling-offset"][-1] == pytest.approx([100.0] * 4)
    assert not result.rolling_support[-1]
    assert result.predictions["initial-offset"][-1] == pytest.approx([110.0] * 4)


def test_official_testing_outcomes_never_update_later_forecasts() -> None:
    initial = [row(hour) for hour in range(24)]
    test = [row(170 + hour * 3, partition="testing", glucose=300) for hour in range(30)]
    base = np.full((len(initial + test), 4), 100.0)
    altered = [replace(item, targets=(500.0,) * 4) for item in test]
    warm, cold = patient_tracks(initial + test, base)
    changed, _ = patient_tracks(initial + altered, base)
    assert warm.rows == test and cold.rows == initial
    assert np.array_equal(warm.points("context-offset"), changed.points("context-offset"))


def test_replay_rejects_mixed_participants_and_reverse_order() -> None:
    point = np.full((2, 4), 100.0)
    with pytest.raises(ValueError, match="single-participant"):
        replay([row(0), replace(row(1), participant="foreign")], point, START, [True, True])
    with pytest.raises(ValueError, match="chronological"):
        replay([row(1), row(0)], point, START, [True, True])
    with pytest.raises(ValueError, match="source-order"):
        patient_tracks([row(1), row(0)], point)


def test_development_assignment_is_patient_level_and_deterministic() -> None:
    source = [
        replace(row(0), dataset=dataset, participant=str(index))
        for dataset in ("ohio", "azt1d")
        for index in range(3)
    ]
    first = development_scopes(source)
    assert first == development_scopes(list(reversed(source)))
    assert {scope.split(":")[0] for scope in first} == {"ohio", "azt1d"}
    assert len(first) == 2
