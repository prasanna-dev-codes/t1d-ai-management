"""Offline subgroup calibration of experimental forecast intervals."""

from typing import Any

import numpy as np
from t1d_forecasting.uncertainty import balanced_quantiles
from t1d_forecasting.windows import HISTORY_FEATURE_NAMES, Window

_TREND = HISTORY_FEATURE_NAMES.index("cgm_change_15")


def trend_groups(rows: list[Window]) -> Any:
    change = np.asarray([row.features[_TREND] for row in rows])
    if not np.isfinite(change).all():
        raise ValueError("Finite observed CGM trends required")
    return np.where(change >= 0.15, "rising", np.where(change <= -0.15, "falling", "quiet"))


def trend_scales(rows: list[Window], absolute_error: Any, radii: Any) -> dict[str, Any]:
    """Fit scales on calibration people only; require three people per trend group."""
    errors = np.asarray(absolute_error, dtype=float)
    radius = np.asarray(radii, dtype=float)
    if (
        errors.shape != (len(rows), 4)
        or radius.shape != errors.shape
        or not np.isfinite(errors).all()
        or not np.isfinite(radius).all()
        or (errors < 0).any()
        or (radius <= 0).any()
    ):
        raise ValueError("Matched positive radii and finite calibration errors required")
    groups = trend_groups(rows)
    scales = {}
    for group in ("falling", "quiet", "rising"):
        mask = groups == group
        selected = [row for row, keep in zip(rows, mask, strict=True) if keep]
        if len({row.scope for row in selected}) >= 3:
            scales[group] = balanced_quantiles(selected, errors[mask] / radius[mask])
    return scales


def scaled_radii(rows: list[Window], radii: Any, scales: dict[str, Any]) -> Any:
    output = np.asarray(radii, dtype=float).copy()
    if output.shape != (len(rows), 4) or not np.isfinite(output).all() or (output <= 0).any():
        raise ValueError("Matched positive interval radii required")
    groups = trend_groups(rows)
    for group, scale in scales.items():
        output[groups == group] *= scale
    return output
