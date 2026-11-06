"""Offline patient-balanced metrics and calibration; no serving policy."""

from collections import Counter, defaultdict
from typing import Any

import numpy as np

from t1d_forecasting.windows import Window


def weights(rows: list[Window]) -> Any:
    counts = Counter(w.scope for w in rows)
    datasets: dict[str, set[str]] = defaultdict(set)
    for w in rows:
        datasets[w.dataset].add(w.scope)
    return np.asarray(
        [len(rows) / (len(datasets) * len(datasets[w.dataset]) * counts[w.scope]) for w in rows]
    )


def macro_mae(rows: list[Window], prediction: Any) -> float:
    errors = np.mean(np.abs(prediction - np.asarray([w.targets for w in rows])), axis=1)
    groups: dict[str, list[float]] = defaultdict(list)
    for row, error in zip(rows, errors, strict=True):
        groups[row.scope].append(float(error))
    datasets: dict[str, list[float]] = defaultdict(list)
    for subject, values in groups.items():
        datasets[subject.split(":")[0]].append(float(np.mean(values)))
    return float(np.mean([np.mean(v) for v in datasets.values()]))


def metrics(rows: list[Window], prediction: Any, radii: Any) -> dict[str, object]:
    target = np.asarray([w.targets for w in rows])
    error = prediction - target
    if prediction.shape != target.shape or not np.isfinite(prediction).all():
        raise ValueError("Invalid model prediction matrix")
    result: dict[str, object] = {}
    for j, horizon in enumerate((30, 60, 90, 120)):
        patient_errors = []
        patient_covered = []
        for subject in sorted({w.scope for w in rows}):
            selected = np.asarray([i for i, w in enumerate(rows) if w.scope == subject])
            patient_errors.append(float(np.mean(np.abs(error[selected, j]))))
            patient_covered.append(bool(np.all(np.abs(error[selected, j]) <= radii[j])))
        rng = np.random.default_rng(20261107)
        means = rng.choice(patient_errors, size=(1000, len(patient_errors))).mean(axis=1)
        result[str(horizon)] = {
            "mae_mg_dl": float(np.mean(np.abs(error[:, j]))),
            "rmse_mg_dl": float(np.sqrt(np.mean(error[:, j] ** 2))),
            "bias_mg_dl": float(np.mean(error[:, j])),
            "patient_macro_mae": float(np.mean(patient_errors)),
            "patient_bootstrap_mae_ci95": [float(v) for v in np.quantile(means, [0.025, 0.975])],
            "window_coverage": float(np.mean(np.abs(error[:, j]) <= radii[j])),
            "whole_patient_coverage": float(np.mean(patient_covered)),
            "interval_width_mg_dl": float(2 * radii[j]),
            "nonpositive_predictions": int(np.sum(prediction[:, j] <= 0)),
        }
    return result


def calibrate(rows: list[Window], prediction: Any) -> Any:
    residual = np.abs(prediction - np.asarray([w.targets for w in rows]))
    maxima = []
    for scope in sorted({w.scope for w in rows}):
        ids = [i for i, w in enumerate(rows) if w.scope == scope]
        maxima.append(residual[ids].max(axis=0))
    index = int(np.ceil((len(maxima) + 1) * 0.9)) - 1
    if index >= len(maxima):
        raise ValueError("At least nine calibration patients required")
    return np.sort(np.asarray(maxima), axis=0)[index]
