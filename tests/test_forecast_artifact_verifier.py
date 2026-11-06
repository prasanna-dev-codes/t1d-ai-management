"""Offline export parameter checks on fictional model payloads."""

import runpy

import pytest
from t1d_forecasting.windows import CGM_FEATURES


@pytest.mark.parametrize("failure", ["none", "scale", "nan", "order", "dimensions"])
def test_exported_ridge_parameters_are_checked(failure: str) -> None:
    validate = runpy.run_path("scripts/verify_forecast_research_artifacts.py")["ridge_parameters"]
    width = len(CGM_FEATURES)
    payload = {
        "feature_names": list(CGM_FEATURES),
        "residual_base": "last_glucose",
        "mean": [0.0] * width,
        "scale": [1.0] * width,
        "coef": [[0.0] * width for _ in range(4)],
        "intercept": [0.0] * 4,
    }
    if failure == "none":
        assert len(validate(payload, width)) == 4
        return
    if failure == "scale":
        payload["scale"] = [0.0] * width
    elif failure == "nan":
        payload["mean"] = [float("nan")] * width
    elif failure == "order":
        payload["feature_names"] = list(reversed(CGM_FEATURES))
    else:
        payload["intercept"] = [0.0]
    with pytest.raises(ValueError):
        validate(payload, width)
