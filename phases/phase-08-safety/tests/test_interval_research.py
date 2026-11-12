"""Check that exploratory interval scaling has a safe support fallback."""

from datetime import datetime, timedelta

import numpy as np
from interval_research import scaled_radii, trend_scales
from t1d_forecasting.windows import HISTORY_FEATURE_NAMES, Window


def test_trend_scales_apply_only_to_supported_observed_groups() -> None:
    index = HISTORY_FEATURE_NAMES.index("cgm_change_15")
    cutoff = datetime(2020, 1, 1)
    rows = []
    for i, trend in enumerate((0.2, 0.2, 0.2, -0.2, -0.2, 0.0)):
        features = [0.0] * len(HISTORY_FEATURE_NAMES)
        features[index] = trend
        rows.append(
            Window(
                "ohio",
                str(i),
                "training",
                cutoff - timedelta(hours=2),
                cutoff,
                cutoff + timedelta(hours=2),
                tuple(features),
                (100.0,) * 4,
                "fictional",
            )
        )
    errors = np.asarray([[20, 25, 30, 35]] * 6)
    original_radii = np.full((6, 4), 10.0)
    scales = trend_scales(rows, errors, original_radii)
    assert set(scales) == {"rising"}
    adjusted = scaled_radii(rows, original_radii, scales)
    np.testing.assert_array_equal(adjusted[:3], errors[:3])
    np.testing.assert_array_equal(adjusted[3:], original_radii[3:])
