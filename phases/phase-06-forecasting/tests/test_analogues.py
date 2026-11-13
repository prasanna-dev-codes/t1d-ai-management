"""Completed trajectories must be local to a participant and available at forecast time."""

from dataclasses import replace
from datetime import datetime, timedelta

import pytest
from t1d_forecasting.analogues import ANALOGUE_FEATURE_NAMES, AnalogueHistory, add_analogue_features
from t1d_forecasting.datasets import OfflineEvent, SourceData
from t1d_forecasting.offline_inference import observed_analogue_features
from t1d_forecasting.windows import HISTORY_FEATURE_NAMES, Window, make_windows

NOW = datetime(2020, 1, 3, 12)
INPUT = tuple(1.0 if index == 11 else 0.0 for index in range(len(HISTORY_FEATURE_NAMES)))


def window(hours_ago: int, level: float = 110.0) -> Window:
    cutoff = NOW - timedelta(hours=hours_ago)
    return Window(
        "ohio",
        "fictional",
        "training",
        cutoff - timedelta(hours=48),
        cutoff,
        cutoff + timedelta(hours=2),
        INPUT,
        (level,) * 4,
        f"fictional-{hours_ago}",
        label_available_at=cutoff + timedelta(hours=2),
    )


def test_only_completed_and_available_neighbours_can_contribute() -> None:
    eligible = [window(age) for age in range(3, 9)]
    future = window(1, 900.0)
    late = replace(window(10, 900.0), label_available_at=NOW + timedelta(minutes=1))
    unknown = replace(window(11, 900.0), label_available_at=None)
    outside = window(47, 900.0)
    examples = eligible + [future, late, unknown, outside]
    features = AnalogueHistory(examples).features("ohio:fictional", "training", NOW, INPUT)
    expected = AnalogueHistory(eligible).features("ohio:fictional", "training", NOW, INPUT)
    assert features == expected
    columns = ANALOGUE_FEATURE_NAMES[len(HISTORY_FEATURE_NAMES) :]
    lookup = dict(zip(columns, features, strict=True))
    assert lookup["analogue_count_scaled"] == 0.06
    assert lookup["analogue_matched_change_120"] == pytest.approx(0.1)
    assert lookup["analogue_present"] == 1


def test_foreign_participants_and_source_partitions_never_contribute() -> None:
    rows = [window(age) for age in range(3, 9)]
    with pytest.raises(ValueError, match="participant and partition"):
        AnalogueHistory(rows + [replace(rows[0], participant="other")])
    with pytest.raises(ValueError, match="foreign source"):
        AnalogueHistory(rows).features("ohio:fictional", "testing", NOW, INPUT)
    current = replace(window(0), partition="testing")
    augmented = add_analogue_features(rows + [current])
    assert augmented[-1].features[-1] == 0
    assert augmented[-1].targets == current.targets


def test_backward_source_clock_cannot_reveal_a_later_trajectory() -> None:
    earlier = [window(age) for age in range(8, 2, -1)]
    target = window(0)
    later_with_earlier_timestamp = window(11, 900.0)
    base = add_analogue_features(earlier + [target])[-1]
    replay = add_analogue_features(earlier + [target, later_with_earlier_timestamp])[-2]
    assert replay.features == base.features


def test_availability_uses_the_latest_of_all_four_outcomes() -> None:
    events = tuple(
        OfflineEvent(
            "ohio",
            "fictional",
            "training",
            "glucose",
            NOW + timedelta(minutes=5 * i),
            "",
            100.0,
            "mg/dL",
            "fictional-source",
            i,
            available_at=NOW + timedelta(hours=24) if i == 17 else None,
        )
        for i in range(36)
    )
    rows, _ = make_windows(
        (SourceData(events, 0, "fictional-source"),),
        include_history=True,
        allow_event_time_replay=True,
    )
    assert len(rows) == 1
    assert rows[0].label_available_at == NOW + timedelta(hours=24)


def test_replay_uses_the_same_features_from_history_without_future_labels() -> None:
    events = tuple(
        OfflineEvent(
            "ohio",
            "fictional",
            "training",
            "glucose",
            NOW + timedelta(minutes=5 * i),
            "",
            float(110 + i % 31),
            "mg/dL",
            "fictional-source",
            i,
        )
        for i in range(240)
    )
    rows, _ = make_windows(
        (SourceData(events, 0, "fictional-source"),),
        include_history=True,
        allow_event_time_replay=True,
    )
    training = add_analogue_features(rows)[-1]
    observed = tuple(event for event in events if event.time <= training.cutoff)
    features, _ = observed_analogue_features(
        (SourceData(observed, 0, "fictional-source"),), "ohio", "fictional"
    )
    assert features[-1] == 1
    assert features == training.features
