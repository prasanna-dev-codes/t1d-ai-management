"""Exploratory per-forecast intervals; no whole-patient or clinical guarantee."""

from typing import Any

import numpy as np

from t1d_forecasting.research_metrics import weights
from t1d_forecasting.windows import Window


def balanced_quantiles(rows: list[Window], scores: Any, coverage: float = 0.9) -> Any:
    values = np.asarray(scores, dtype=float)
    if not rows or values.shape != (len(rows), 4) or not np.isfinite(values).all():
        raise ValueError("Finite matched four-horizon calibration scores required")
    if (values < 0).any() or not 0 < coverage < 1:
        raise ValueError("Nonnegative scores and valid coverage required")
    mass = weights(rows)
    result = []
    for j in range(4):
        order = np.argsort(values[:, j], kind="stable")
        cumulative = np.cumsum(mass[order]) / mass.sum()
        index = min(int(np.searchsorted(cumulative, coverage)), len(order) - 1)
        result.append(values[order[index], j])
    return np.asarray(result)


def interval_metrics(
    rows: list[Window], prediction: Any, radii: Any, coverage: float = 0.9
) -> dict[str, object]:
    points = np.asarray(prediction, dtype=float)
    radius = np.broadcast_to(np.asarray(radii, dtype=float), (len(rows), 4))
    target = np.asarray([w.targets for w in rows])
    if not rows or points.shape != target.shape or not np.isfinite(points).all():
        raise ValueError("Finite matched predictions required")
    if not np.isfinite(radius).all() or (radius < 0).any() or not 0 < coverage < 1:
        raise ValueError("Valid interval radii and coverage required")
    lower, upper = points - radius, points + radius
    inside = (target >= lower) & (target <= upper)
    score = 2 * radius + 2 / (1 - coverage) * (
        np.maximum(lower - target, 0) + np.maximum(target - upper, 0)
    )
    result: dict[str, object] = {}
    for j, h in enumerate((30, 60, 90, 120)):
        by_patient = [
            float(inside[[i for i, w in enumerate(rows) if w.scope == scope], j].mean())
            for scope in sorted({w.scope for w in rows})
        ]
        rng = np.random.default_rng(20261107)
        ci = None
        if len(by_patient) > 1:
            draws = rng.choice(by_patient, size=(1000, len(by_patient))).mean(axis=1)
            ci = [float(v) for v in np.quantile(draws, [0.025, 0.975])]
        result[str(h)] = {
            "window_coverage": float(inside[:, j].mean()),
            "patient_macro_coverage": float(np.mean(by_patient)),
            "patient_bootstrap_coverage_ci95": ci,
            "mean_width_mg_dl": float((2 * radius[:, j]).mean()),
            "p95_width_mg_dl": float(np.quantile(2 * radius[:, j], 0.95)),
            "mean_interval_score": float(score[:, j].mean()),
            "nonpositive_lower_bounds": int((lower[:, j] <= 0).sum()),
            "nonpositive_point_predictions": int((points[:, j] <= 0).sum()),
        }
    return result
