"""Hand-checkable uncertainty math; no health records."""

from datetime import datetime

import numpy as np
import pytest
from t1d_forecasting.uncertainty import balanced_quantiles, interval_metrics
from t1d_forecasting.windows import Window


def row(subject: str) -> Window:
    when = datetime(2020, 1, 1)
    return Window("fictional", subject, "calibration", when, when, when, (), (100.0,) * 4, "test")


def test_quantiles_balance_patients_instead_of_row_count() -> None:
    rows = [row("a") for _ in range(99)] + [row("b")]
    values = np.asarray([[1.0] * 4] * 99 + [[10.0] * 4])
    assert balanced_quantiles(rows, values) == pytest.approx([10.0] * 4)
    assert balanced_quantiles(rows, values, 0.4) == pytest.approx([1.0] * 4)


def test_interval_score_penalizes_both_width_and_misses() -> None:
    rows = [row("a"), row("b")]
    # First interval [99,101] contains 100; second [102,104] misses by two.
    report = interval_metrics(rows, np.asarray([[100.0] * 4, [103.0] * 4]), np.ones((2, 4)))
    h = report["30"]
    assert isinstance(h, dict)
    assert h["window_coverage"] == 0.5
    assert h["mean_width_mg_dl"] == 2
    assert h["mean_interval_score"] == pytest.approx(22)
    assert h["nonpositive_lower_bounds"] == 0


@pytest.mark.parametrize("value", [-1.0, float("nan"), float("inf")])
def test_invalid_calibration_or_intervals_rejected(value: float) -> None:
    rows = [row("a")]
    with pytest.raises(ValueError):
        balanced_quantiles(rows, np.full((1, 4), value))
    with pytest.raises(ValueError):
        interval_metrics(rows, np.full((1, 4), 100.0), np.full(4, value))


def test_one_patient_cannot_produce_patient_bootstrap_interval() -> None:
    report = interval_metrics([row("a")], np.full((1, 4), 100.0), np.ones(4))
    value = report["120"]
    assert isinstance(value, dict) and value["patient_bootstrap_coverage_ci95"] is None
