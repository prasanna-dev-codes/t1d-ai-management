"""Regression coverage for causal history, missing factors and the v1 feature contract."""

from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from zipfile import ZipFile

from t1d_forecasting.datasets import OfflineEvent, SourceData, read_ohio
from t1d_forecasting.history_features import (
    HISTORY_CGM_FEATURES,
    HISTORY_CONTEXT_FEATURES,
    extended_cgm,
    extended_context,
)
from t1d_forecasting.offline_inference import observed_history_features
from t1d_forecasting.windows import FEATURE_NAMES, HISTORY_FEATURE_NAMES, make_windows

NOW = datetime(2020, 1, 3, 12)
ROW = OfflineEvent("ohio", "fake", "training", "glucose", NOW, "", 100, "mg/dL", "fake", 1)


def test_long_history_never_reads_after_cutoff() -> None:
    rows = [
        replace(ROW, time=NOW + timedelta(minutes=5 * i), value=float(100 + i / 10))
        for i in range(-576, 25)
    ]
    expected = extended_cgm(rows[:577], 576)
    assert extended_cgm(rows, 576) == expected
    features = dict(zip(HISTORY_CGM_FEATURES, expected, strict=True))
    assert features["cgm_clock_day_2_present"] == 1
    assert rows[24].value is not None and rows[0].value is not None
    assert features["cgm_clock_day_2_change_120"] == (rows[24].value - rows[0].value) / 100
    assert features["prior_morning_pair_present"] == 1
    rows[0] = replace(rows[0], available_at=NOW + timedelta(minutes=1))
    masked = dict(zip(HISTORY_CGM_FEATURES, extended_cgm(rows, 576), strict=True))
    assert masked["cgm_clock_day_2_present"] == 0


def test_recorded_factors_respect_completion_availability_and_overlap() -> None:
    sleep = replace(
        ROW,
        kind="sleep",
        time=NOW - timedelta(hours=9),
        end_time=NOW - timedelta(hours=3),
        value=None,
    )
    sensor = replace(sleep, kind="sensor_sleep")
    overlap = replace(sleep, time=NOW - timedelta(hours=6), end_time=NOW - timedelta(hours=2))
    unfinished = replace(sleep, time=NOW - timedelta(hours=1), end_time=NOW + timedelta(hours=1))
    bolus = replace(
        ROW,
        kind="bolus",
        time=NOW - timedelta(hours=2),
        value=2,
        unit="U",
        insulin_type="Humalog",
    )
    exercise = replace(
        ROW,
        kind="exercise",
        time=NOW - timedelta(hours=1),
        value=30,
        intensity=7,
        unit="minutes",
    )
    late = replace(exercise, available_at=NOW + timedelta(minutes=1), intensity=10)
    context = sorted(
        [sleep, overlap, unfinished, sensor, bolus, exercise, late], key=lambda e: e.time
    )
    times = [e.time for e in context]
    strict = extended_context(context, times, NOW, False)
    assert strict == (0.0,) * len(HISTORY_CONTEXT_FEATURES)
    features = dict(
        zip(HISTORY_CONTEXT_FEATURES, extended_context(context, times, NOW, True), strict=True)
    )
    assert features["reported_sleep_hours_24"] == 7 / 24
    assert features["sensor_sleep_hours_24"] == 6 / 24
    assert features["reported_exercise_intensity_240"] == 0.7
    assert features["reported_exercise_after_bolus_minutes_240"] == 0.5
    assert features["recorded_insulin_type_humalog"] == 1


def test_history_preserves_frozen_inputs_targets_and_scoring_anchors() -> None:
    rows = tuple(
        replace(ROW, time=NOW + timedelta(minutes=5 * i), source_row=i, value=float(100 + i))
        for i in range(72)
    )
    sources = (SourceData(rows, 0, "fake"),)
    original, _ = make_windows(sources)
    extended, _ = make_windows(sources, include_history=True)
    assert len(original) > 1
    for base, history in zip(original, extended, strict=True):
        assert history.features[: len(FEATURE_NAMES)] == base.features
        assert len(history.features) == len(HISTORY_FEATURE_NAMES)
        assert history.targets == base.targets and history.cutoff == base.cutoff
        assert history.input_ref != base.input_ref and history.input_start < base.input_start
    denser, _ = make_windows(sources, stride=3, include_history=True, score_stride=6)
    assert len(denser) > len(extended)
    assert [w for w in denser if not w.fit_only] == extended
    final = extended[-1]
    observed, _ = observed_history_features(
        (SourceData(tuple(e for e in rows if e.time <= final.cutoff), 0, "fake"),),
        "ohio",
        "fake",
    )
    assert observed == final.features


def test_ohio_sleep_streams_preserve_source_and_reject_reversed_intervals(tmp_path: Path) -> None:
    path = tmp_path / "test.zip"
    xml = """<patient id="1" insulin_type="Humalog">
    <sleep><event ts_begin="03-01-2020 08:00:00" ts_end="03-01-2020 02:00:00"
    quality="3"/></sleep>
    <basis_sleep><event tbegin="03-01-2020 02:00:00" tend="03-01-2020 08:00:00"
    quality=" "/></basis_sleep>
    </patient>"""
    with ZipFile(path, "w") as archive:
        archive.writestr("1-ws-training.xml", xml)
    assert read_ohio(path)[0].events == ()
    source = read_ohio(path, extended_context=True)[0]
    assert source.rejected_rows == 1
    assert len(source.events) == 1 and source.events[0].kind == "sensor_sleep"
