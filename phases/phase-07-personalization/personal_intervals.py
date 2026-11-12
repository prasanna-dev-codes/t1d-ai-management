"""Exploratory uncertainty calibration using each participant's past forecast errors."""

from dataclasses import dataclass
from typing import Any

import numpy as np
from t1d_forecasting.uncertainty import balanced_quantiles
from t1d_forecasting.windows import Window


@dataclass(frozen=True)
class PersonalIntervals:
    constant: Any
    normalized_quantile: Any | None
    calibration_participants: int

    def radii(self, recent_error: Any) -> Any:
        scale = np.asarray(recent_error, dtype=float)
        if scale.ndim != 2 or scale.shape[1] != 4 or np.isinf(scale).any() or (scale < 0).any():
            raise ValueError("Four horizons required for personal calibration")
        output = np.broadcast_to(self.constant, scale.shape).copy()
        supported = np.isfinite(scale).all(axis=1)
        if self.normalized_quantile is not None:
            output[supported] = (
                0.5 * self.constant + 0.5 * np.maximum(1.0, scale[supported])
            ) * self.normalized_quantile
        return output


def calibrate(
    rows: list[Window], absolute_error: Any, recent_error: Any, constant: Any
) -> PersonalIntervals:
    scale = np.asarray(recent_error, dtype=float)
    errors = np.asarray(absolute_error, dtype=float)
    reference = np.asarray(constant, dtype=float)
    if (
        scale.shape != (len(rows), 4)
        or errors.shape != scale.shape
        or reference.shape != (4,)
        or np.isinf(scale).any()
        or (scale < 0).any()
        or not np.isfinite(errors).all()
        or (errors < 0).any()
        or not np.isfinite(reference).all()
        or (reference < 0).any()
    ):
        raise ValueError("Aligned four-horizon calibration inputs required")
    supported = np.isfinite(scale).all(axis=1)
    eligible = [row for row, keep in zip(rows, supported, strict=True) if keep]
    participants = len({row.scope for row in eligible})
    quantile = None
    if participants >= 3:
        blended = 0.5 * reference + 0.5 * np.maximum(1.0, scale[supported])
        quantile = balanced_quantiles(eligible, errors[supported] / blended)
    return PersonalIntervals(reference, quantile, participants)
