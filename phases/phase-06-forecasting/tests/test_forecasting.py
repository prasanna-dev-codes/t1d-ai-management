"""Numerical, temporal, uncertainty and frozen-artifact research checks."""

from dataclasses import replace
from datetime import timedelta
from uuid import UUID

import pytest
from pydantic import ValidationError
from t1d_forecasting.contracts import HORIZONS, ForecastRequest
from t1d_forecasting.engine import Abstain, load_bundle, point_value, predict, snapshot
from t1d_forecasting.experiment import examples, experiment, split_check


def test_straight_line_baseline_and_explicit_target_times() -> None:
    example = examples(range(1, 2), 1)[0]
    readings = [r.model_copy(update={"value": 100 + i * 5}) for i, r in enumerate(example.readings)]
    state = snapshot(readings, example.cutoff)
    bundle, digest, identity = load_bundle()
    linear = next(m for m in bundle.models if m.profile == "linear-v1")
    persistent = next(m for m in bundle.models if m.profile == "persistence-v1")
    assert len(digest) == 64 and identity != UUID(int=0)
    assert point_value(state.features, persistent, 30) == 155
    assert point_value(state.features, linear, 30) == pytest.approx(185 + 1 / 6)
    for p in predict(state, linear, HORIZONS):
        assert p.target_time == example.cutoff + timedelta(minutes=p.horizon_minutes)
        assert p.lower_mg_dl <= p.glucose_mg_dl <= p.upper_mg_dl


@pytest.mark.parametrize(
    "failure",
    [
        "empty",
        "short",
        "late",
        "stale",
        "gap",
        "duplicate",
        "warning",
        "quarantine",
        "sensor",
        "missing",
    ],
)
def test_forecast_abstains_on_unqualified_history(failure: str) -> None:
    example = examples(range(1, 2), 1)[0]
    rows = list(example.readings)
    cutoff = example.cutoff
    if failure == "empty":
        rows = []
    elif failure == "short":
        rows = rows[1:]
    elif failure == "late":
        rows[-1] = rows[-1].model_copy(update={"available_at": cutoff + timedelta(seconds=1)})
    elif failure == "stale":
        cutoff += timedelta(minutes=6)
    elif failure == "gap":
        rows[5] = rows[5].model_copy(
            update={"event_time": rows[5].event_time + timedelta(seconds=1)}
        )
    elif failure == "duplicate":
        rows.append(rows[-1].model_copy(update={"id": UUID(int=99)}))
    else:
        changes: dict[str, dict[str, object]] = {
            "warning": {"quality": "warning"},
            "quarantine": {"quality": "quarantined"},
            "sensor": {"valid_sensor": False},
            "missing": {"value": None},
        }
        rows[-1] = rows[-1].model_copy(update=changes[failure])
    with pytest.raises(Abstain):
        snapshot(rows, cutoff)


def test_future_observations_cannot_change_features_and_units_are_explicit() -> None:
    example = examples(range(1, 2), 1)[0]
    rows = list(example.readings)
    first = snapshot(rows, example.cutoff)
    future = rows[-1].model_copy(
        update={
            "id": UUID(int=999),
            "value": 900.0,
            "event_time": example.cutoff + timedelta(minutes=1),
        }
    )
    assert first == snapshot(rows + [future], example.cutoff)
    converted = [
        r.model_copy(update={"value": (r.value or 0.0) * 0.0555, "unit": "mmol/L"}) for r in rows
    ]
    assert snapshot(converted, example.cutoff).features == pytest.approx(first.features)


@pytest.mark.parametrize("cutoff", [12345, "2020-01-01", "2020-01-01T00:00:00"])
def test_forecast_timestamps_require_explicit_timezone(cutoff: object) -> None:
    with pytest.raises(ValidationError):
        ForecastRequest.model_validate({"input_cutoff": cutoff})


@pytest.mark.parametrize("horizons", [[], [30, 30], [15], [30, 120, 500]])
def test_unsupported_or_duplicate_horizons_refused(horizons: list[int]) -> None:
    with pytest.raises(ValidationError):
        ForecastRequest.model_validate(
            {"input_cutoff": "2020-01-01T00:00:00Z", "horizons_minutes": horizons}
        )


def test_patient_and_label_window_overlap_rejected() -> None:
    a, b, c = examples(range(1, 2), 1), examples(range(2, 3), 1), examples(range(3, 4), 1)
    split_check(a, b, c)
    with pytest.raises(ValueError, match="Patient overlap"):
        split_check(a, a, c)
    with pytest.raises(ValueError, match="label windows"):
        split_check(a, [replace(b[0], cutoff=a[0].cutoff)], c)


def test_training_reproducible_and_packaged_parameters_match() -> None:
    first, report = experiment()
    second, _ = experiment()
    assert first == second
    bundled, _, _ = load_bundle()
    for a, b in zip(first.models, bundled.models, strict=True):
        for x, y in zip(a.horizons, b.horizons, strict=True):
            assert x.weights == pytest.approx(y.weights, abs=1e-8)
            assert x.radius == pytest.approx(y.radius, abs=1e-8)
    assert report["split"] == {
        "train_patients": 20,
        "calibration_patients": 10,
        "test_patients": 10,
        "windows_per_patient": 16,
        "patient_overlap": 0,
        "label_window_overlap": 0,
    }


def test_artifact_integrity_failure_is_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    from t1d_forecasting import manifest

    monkeypatch.setattr(manifest, "ARTIFACT_SHA256", "0" * 64)
    with pytest.raises(ValueError, match="integrity"):
        load_bundle()
