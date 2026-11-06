"""Context availability and local elapsed-time semantics must be explicit."""

from datetime import datetime, timedelta

from t1d_forecasting.datasets import OfflineEvent
from t1d_forecasting.windows import FEATURE_NAMES, Window, _context, patient_partitions


def event(kind: str = "glucose") -> OfflineEvent:
    return OfflineEvent(
        "ohio",
        "fictional",
        "training",
        kind,  # type: ignore[arg-type]
        datetime(2020, 1, 1, 12),
        "source-local-clock",
        30.0,
        "g",
        "fictional-hash",
        1,
    )


def test_context_with_unknown_availability_needs_explicit_replay() -> None:
    anchor, meal = event(), event("carbohydrate")
    strict = _context([meal], [meal.time], anchor)
    replay = _context([meal], [meal.time], anchor, allow_event_time_replay=True)
    assert strict[:2] == [0.0, 0.0]
    assert replay[:2] == [0.3, 1.0]
    assert anchor.time.tzinfo is None


def test_late_record_is_excluded_even_when_replay_allowed() -> None:
    from dataclasses import replace

    anchor, meal = event(), event("carbohydrate")
    late = replace(meal, available_at=meal.time + timedelta(minutes=1))
    assert _context([late], [late.time], anchor, allow_event_time_replay=True)[:2] == [0.0, 0.0]
    known = replace(meal, available_at=meal.time)
    assert _context([known], [known.time], anchor)[:2] == [0.3, 1.0]


def test_context_does_not_include_future_exercise_duration_or_unavailable_mode() -> None:
    from dataclasses import replace

    anchor = replace(event(), device_mode="sleep")
    exercise = event("exercise")
    strict = _context([], [], anchor)
    assert strict[-3:] == [0.0, 0.0, 0.0]
    replay = _context([exercise], [exercise.time], anchor, True)
    assert replay[12:18] == [0.0] * 6
    assert replay[-3:] == [1.0, 0.0, 1.0]


def test_patient_partitions_and_official_test_calibration_exclusion() -> None:
    windows = []
    for dataset in ("ohio", "physiocgm", "azt1d"):
        for participant in range(10):
            for i in range(20):
                cutoff = datetime(2020, 1, 1) + timedelta(hours=6 * i)
                for partition in ("training", "testing"):
                    windows.append(
                        Window(
                            dataset,
                            str(participant),
                            partition,
                            cutoff - timedelta(minutes=120),
                            cutoff,
                            cutoff + timedelta(minutes=120),
                            tuple(0.0 for _ in FEATURE_NAMES),
                            (100.0,) * 4,
                            f"{dataset}-{participant}-{i}-{partition}",
                        )
                    )
    for external in (None, "ohio", "physiocgm", "azt1d"):
        parts = patient_partitions(windows, external)
        fit = {w.scope for w in parts["fit"]}
        calibration = {w.scope for w in parts["calibration"]}
        test = {w.scope for w in parts["test"]}
        assert not (fit & calibration or fit & test or calibration & test)
        assert all(w.partition != "testing" for w in parts["calibration"])
        for subject in fit:
            assert max(w.label_end for w in parts["fit"] if w.scope == subject) < min(
                w.input_start for w in parts["validation"] if w.scope == subject
            )
        if external:
            assert all(w.dataset == external for w in parts["test"])
