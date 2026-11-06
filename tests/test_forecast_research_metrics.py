"""Small deterministic checks for research weighting/calibration, no health records."""

from datetime import datetime, timedelta

import numpy as np
import pytest
from t1d_forecasting.research_metrics import calibrate, metrics, weights
from t1d_forecasting.windows import FEATURE_NAMES, Window


def row(dataset: str, subject: str, index: int = 0) -> Window:
    cutoff = datetime(2020, 1, 1) + timedelta(hours=index)
    return Window(
        dataset,
        subject,
        "training",
        cutoff - timedelta(minutes=120),
        cutoff,
        cutoff + timedelta(minutes=120),
        (0.0,) * len(FEATURE_NAMES),
        (100.0,) * 4,
        "fictional",
    )


def test_weights_do_not_allow_large_cohort_or_patient_to_dominate() -> None:
    rows = [row("a", "1", i) for i in range(10)] + [row("a", "2"), row("b", "3")]
    result = weights(rows)
    assert result[:11].sum() == pytest.approx(result[11])
    assert result[:10].sum() == pytest.approx(result[10])
    assert result.sum() == pytest.approx(len(rows))


def test_calibration_uses_patient_maxima_and_refuses_too_few_patients() -> None:
    rows = [row("fictional", str(i), j) for i in range(9) for j in range(2)]
    prediction = np.asarray([[101.0] * 4, [102.0] * 4] * 9)
    assert calibrate(rows, prediction) == pytest.approx([2.0] * 4)
    with pytest.raises(ValueError, match="nine"):
        calibrate(rows[:16], prediction[:16])


def test_metrics_match_known_errors_and_refuse_nonfinite_predictions() -> None:
    rows = [row("fictional", str(i)) for i in range(9)]
    prediction = np.full((9, 4), 102.0)
    report = metrics(rows, prediction, np.full(4, 2.0))
    early, late = report["30"], report["120"]
    assert isinstance(early, dict) and isinstance(late, dict)
    assert early["mae_mg_dl"] == 2
    assert early["window_coverage"] == 1
    assert late["interval_width_mg_dl"] == 4
    with pytest.raises(ValueError, match="Invalid"):
        metrics(rows, np.full((9, 4), float("nan")), np.ones(4))
