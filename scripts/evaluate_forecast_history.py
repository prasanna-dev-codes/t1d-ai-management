"""Compare causal history and recorded factor groups against the frozen v1 models."""

import argparse
import hashlib
import json
import time
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
from t1d_forecasting.datasets import SourceData, read_azt1d, read_ohio, read_physiocgm
from t1d_forecasting.history_model import MODEL_COLUMNS, MODEL_WEIGHTS, TARGET_SCALE, factor_masks
from t1d_forecasting.research_metrics import macro_mae, weights
from t1d_forecasting.uncertainty import balanced_quantiles, interval_metrics
from t1d_forecasting.windows import (
    HISTORY_FEATURE_NAMES,
    HISTORY_FEATURE_VERSION,
    Window,
    make_windows,
    patient_partitions,
)
from xgboost import XGBRegressor

HORIZONS = (30, 60, 90, 120)
PROFILES = {
    "long-cgm": "reg:squarederror",
    "long-context": "reg:squarederror",
    "long-context-huber": "reg:pseudohubererror",
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _train(
    columns: tuple[int, ...],
    objective: str,
    data: dict[str, Any],
    residual: dict[str, Any],
    mass: dict[str, Any],
) -> Any:
    model = XGBRegressor(
        n_estimators=360,
        max_depth=5,
        learning_rate=0.045,
        objective=objective,
        eval_metric="mae",
        tree_method="hist",
        n_jobs=4,
        random_state=20261111,
        early_stopping_rounds=25,
        min_child_weight=8,
        reg_lambda=4,
        colsample_bytree=0.85,
        subsample=0.9,
        base_score=0.0,
    )
    return model.fit(
        data["fit"][:, columns],
        residual["fit"],
        sample_weight=mass["fit"],
        eval_set=[(data["validation"][:, columns], residual["validation"])],
        sample_weight_eval_set=[mass["validation"]],
        verbose=False,
    )


def _point_scores(rows: list[Window], predicted: Any) -> dict[str, Any]:
    target = np.asarray([row.targets for row in rows])
    error = predicted - target
    mass = weights(rows)
    return {
        "windows": len(rows),
        "patients": len({w.scope for w in rows}),
        "balanced_mae": np.average(np.abs(error), axis=0, weights=mass).tolist(),
        "balanced_rmse": np.sqrt(np.average(error**2, axis=0, weights=mass)).tolist(),
        "balanced_bias": np.average(error, axis=0, weights=mass).tolist(),
    }


def _paired_delta(rows: list[Window], baseline: Any, candidate: Any) -> list[list[float]]:
    target = np.asarray([w.targets for w in rows])
    delta = np.abs(candidate - target) - np.abs(baseline - target)
    groups: dict[str, list[Any]] = {}
    scopes = np.asarray([w.scope for w in rows])
    for subject in sorted(set(scopes)):
        dataset = subject.split(":")[0]
        groups.setdefault(dataset, []).append(delta[scopes == subject].mean(axis=0))
    rng = np.random.default_rng(20261111)
    draws = []
    for subject_means in groups.values():
        values = np.asarray(subject_means)
        indices = rng.integers(len(values), size=(2000, len(values)))
        draws.append(values[indices].mean(axis=1))
    intervals = np.quantile(np.mean(draws, axis=0), [0.025, 0.975], axis=0).T
    return [[float(low), float(high)] for low, high in intervals]


def run_experiment(
    windows: list[Window], baseline_dir: Path, output: Path, external: str | None, fit_stride: int
) -> None:
    name = f"external-{external}" if external else "pooled"
    output = output / name
    output.mkdir()
    parts = patient_partitions(windows, external)
    x = {
        role: np.asarray([w.features for w in rows], dtype=np.float32)
        for role, rows in parts.items()
    }
    y = {role: np.asarray([w.targets for w in rows]) for role, rows in parts.items()}
    last = {
        role: np.asarray([w.features[11] * 100 for w in rows])[:, None]
        for role, rows in parts.items()
    }
    mass = {role: weights(parts[role]) for role in ("fit", "validation")}
    residual = {role: (y[role] - last[role]) / TARGET_SCALE for role in mass}
    frozen_dir = baseline_dir / name
    frozen_path = frozen_dir / "xgb-context.json"
    frozen_report = json.loads((frozen_dir / "report.json").read_text(encoding="utf-8"))
    if _sha(frozen_path) != frozen_report["artifact_sha256"][frozen_path.name]:
        raise ValueError("Frozen benchmark checksum mismatch")
    for role in ("test", "calibration"):
        if (
            dict(Counter(w.dataset for w in parts[role]))
            != frozen_report["partitions"][role]["by_dataset"]
        ):
            raise ValueError("Comparison requires matching frozen benchmark cohorts")

    frozen = XGBRegressor(n_jobs=4)
    frozen.load_model(frozen_path)
    models = {"frozen-v1": (frozen, MODEL_COLUMNS["frozen-v1"], 1.0)}
    for profile, objective in PROFILES.items():
        columns = MODEL_COLUMNS[profile]
        print(name, profile, flush=True)
        model = _train(columns, objective, x, residual, mass)
        path = output / f"{profile}.json"
        model.save_model(path)
        restored = XGBRegressor(n_jobs=4)
        restored.load_model(path)
        np.testing.assert_allclose(
            restored.predict(x["validation"][:32, columns]),
            model.predict(x["validation"][:32, columns]),
            rtol=1e-6,
        )
        models[profile] = (restored, columns, TARGET_SCALE)

    def predict(role: str) -> dict[str, Any]:
        points = {
            profile: last[role] + model.predict(x[role][:, columns]) * scale
            for profile, (model, columns, scale) in models.items()
        }
        return {
            profile: sum(points[component] * weight for component, weight in components.items())
            for profile, components in MODEL_WEIGHTS.items()
        }

    validation = predict("validation")
    scores = {
        profile: macro_mae(parts["validation"], points) for profile, points in validation.items()
    }
    selected = min(scores, key=lambda profile: scores[profile])

    # The selected profile is fixed before any held-out outcomes are scored.
    test, calibration = predict("test"), predict("calibration")
    test_rows = parts["test"]
    reference = _point_scores(test_rows, test["frozen-v1"])
    if not np.allclose(
        reference["balanced_mae"],
        [
            frozen_report["test_results"]["xgb-context"]["all"][str(h)]["patient_macro_mae"]
            for h in HORIZONS
        ],
        atol=0.005,
    ):
        raise ValueError("The reference could not reproduce the frozen benchmark MAE")
    results = {profile: _point_scores(test_rows, points) for profile, points in test.items()}
    radii = balanced_quantiles(
        parts["calibration"], np.abs(calibration[selected] - y["calibration"])
    )
    by_dataset, factors = {}, {}
    masks = factor_masks(x["test"])
    for dataset in sorted({w.dataset for w in test_rows}):
        indices = [i for i, w in enumerate(test_rows) if w.dataset == dataset]
        rows = [test_rows[i] for i in indices]
        by_dataset[dataset] = {
            profile: _point_scores(rows, test[profile][indices])
            for profile in ("frozen-v1", "long-cgm", "long-context", "long-context-huber", selected)
        }
        factors[dataset] = {factor: int(mask[indices].sum()) for factor, mask in masks.items()}

    subgroups = {}
    short_change = x["test"][:, HISTORY_FEATURE_NAMES.index("cgm_change_15")]
    for group, mask in (
        ("falling_at_least_15_in_15min", short_change <= -0.15),
        ("rising_at_least_15_in_15min", short_change >= 0.15),
        ("recorded_carbs_recent", masks["carbs"]),
        ("recorded_sleep_recent", masks["sleep_hours"]),
        ("recorded_activity_after_bolus", masks["activity_after_insulin"]),
    ):
        if mask.any():
            rows = [test_rows[i] for i, selected_row in enumerate(mask) if selected_row]
            subgroups[group] = {
                profile: _point_scores(rows, test[profile][mask])
                for profile in ("frozen-v1", selected)
            }
    report = {
        "feature_version": HISTORY_FEATURE_VERSION,
        "feature_names": HISTORY_FEATURE_NAMES,
        "context_policy": "event-time-replay",
        "fit_stride": fit_stride,
        "score_stride": 6,
        "external_dataset": external,
        "validation_mae": scores,
        "selected_on_validation": selected,
        "role_counts": {role: len(rows) for role, rows in parts.items()},
        "test": results,
        "test_selected_minus_frozen_mae_bootstrap_95": _paired_delta(
            test_rows, test["frozen-v1"], test[selected]
        ),
        "test_by_dataset": by_dataset,
        "test_subgroups": subgroups,
        "test_factor_observed_windows_by_dataset": factors,
        "test_intervals": interval_metrics(test_rows, test[selected], radii),
        "calibration_radii": radii.tolist(),
        "frozen_model_sha256": _sha(frozen_path),
        "artifact_sha256": {path.name: _sha(path) for path in output.glob("*.json")},
    }
    (output / "report.json").write_text(
        json.dumps(report, indent=2, allow_nan=False), encoding="utf-8"
    )
    print(name, "completed", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("ohio", "azt", "physiocgm", "baseline", "output"):
        parser.add_argument(f"--{name}", required=True, type=Path)
    parser.add_argument("--context-availability", choices=["event-time-replay"], required=True)
    parser.add_argument("--fit-stride", choices=(3, 6), default=6, type=int)
    args = parser.parse_args()
    if args.output.resolve().is_relative_to(Path(__file__).resolve().parents[1]):
        parser.error("Research artifacts must remain outside Git")
    args.output.mkdir(parents=True)
    loaders: tuple[tuple[str, Callable[[], tuple[SourceData, ...]]], ...] = (
        ("ohio", lambda: read_ohio(args.ohio, extended_context=True)),
        (
            "physiocgm",
            lambda: tuple(read_physiocgm(p) for p in sorted(args.physiocgm.glob("*.csv"))),
        ),
        ("azt1d", lambda: read_azt1d(args.azt)),
    )
    started = time.perf_counter()
    windows: list[Window] = []
    for dataset, load in loaders:
        eligible, _ = make_windows(
            load(),
            stride=args.fit_stride,
            allow_event_time_replay=True,
            include_history=True,
            score_stride=6,
        )
        if not eligible:
            raise ValueError(f"No eligible windows for {dataset}")
        windows.extend(eligible)
        print(dataset, len(eligible), "windows", flush=True)
    for external in (None, "ohio", "physiocgm", "azt1d"):
        run_experiment(windows, args.baseline, args.output, external, args.fit_stride)
    print(f"Completed in {time.perf_counter() - started:.1f}s", flush=True)


if __name__ == "__main__":
    main()
