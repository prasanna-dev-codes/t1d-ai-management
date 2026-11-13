"""Compare causal CGM episode features against the frozen Phase 06 v4 forecasts."""

import argparse
import json
import shutil
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
from evaluate_forecast_history import _paired_delta, _point_scores, _sha
from t1d_forecasting.analogue_models import (
    BASE_MODELS,
    NEURAL_LAYERS,
    NEURAL_OUTPUT_SCALE,
    NEURAL_RECIPES,
    RECIPES,
    neural_predict,
    read_neural,
)
from t1d_forecasting.analogues import (
    ANALOGUE_FEATURE_NAMES,
    ANALOGUE_FEATURE_VERSION,
    active_analogues,
    add_analogue_features,
)
from t1d_forecasting.datasets import SourceData, read_azt1d, read_ohio, read_physiocgm
from t1d_forecasting.history_model import MODEL_COLUMNS, TARGET_SCALE, factor_masks
from t1d_forecasting.research_metrics import weights
from t1d_forecasting.uncertainty import balanced_quantiles, interval_metrics
from t1d_forecasting.windows import HISTORY_FEATURE_NAMES, Window, make_windows, patient_partitions
from xgboost import XGBRegressor

OBJECTIVES = {"analogue-huber": "reg:pseudohubererror", "analogue-l1": "reg:absoluteerror"}


def _fit(
    objective: str, parts: dict[str, list[Window]], x: dict[str, Any], last: dict[str, Any]
) -> Any:
    data = {
        role: (np.asarray([row.targets for row in parts[role]]) - last[role]) / TARGET_SCALE
        for role in ("fit", "validation")
    }
    model = XGBRegressor(
        n_estimators=400,
        max_depth=5,
        learning_rate=0.045,
        objective=objective,
        eval_metric="mae",
        tree_method="hist",
        n_jobs=5,
        random_state=20261111,
        early_stopping_rounds=25,
        min_child_weight=8,
        reg_lambda=4,
        colsample_bytree=0.85,
        subsample=0.9,
        base_score=0.0,
    )
    return model.fit(
        x["fit"],
        data["fit"],
        sample_weight=weights(parts["fit"]),
        eval_set=[(x["validation"], data["validation"])],
        sample_weight_eval_set=[weights(parts["validation"])],
        verbose=False,
    )


def _choose(scores: dict[str, list[float]]) -> list[str]:
    # Select per horizon on development only, keeping v4 for gains below 0.05 mg/dL.
    choices = []
    for horizon in range(4):
        best = min(scores, key=lambda profile: scores[profile][horizon])
        choices.append(best if scores["v4"][horizon] - scores[best][horizon] >= 0.05 else "v4")
    return choices


def _train_neural(
    parts: dict[str, list[Window]], x: dict[str, Any], last: dict[str, Any], path: Path
) -> dict[str, Any]:
    from sklearn.neural_network import MLPRegressor
    from sklearn.preprocessing import StandardScaler

    fit_mass = weights(parts["fit"])
    scaler = StandardScaler().fit(x["fit"], sample_weight=fit_mass)
    parameters = {
        "mean": scaler.mean_.astype(np.float32),
        "scale": scaler.scale_.astype(np.float32),
    }
    inputs = {
        role: np.clip((x[role] - parameters["mean"]) / parameters["scale"], -8, 8)
        for role in ("fit", "validation")
    }
    target = {
        role: (np.asarray([row.targets for row in parts[role]]) - last[role]) / TARGET_SCALE
        for role in inputs
    }
    fit_target = np.clip(target["fit"], -6, 6).astype(np.float32) * NEURAL_OUTPUT_SCALE
    val_mass = weights(parts["validation"])
    model = MLPRegressor(
        hidden_layer_sizes=NEURAL_LAYERS,
        batch_size=256,
        learning_rate_init=0.001,
        alpha=0.02,
        random_state=20261111,
    )
    best, stalled = float("inf"), 0
    for _ in range(60):
        model.partial_fit(inputs["fit"], fit_target, sample_weight=fit_mass)
        estimate = model.predict(inputs["validation"]) / NEURAL_OUTPUT_SCALE
        horizon_mae = np.average(np.abs(estimate - target["validation"]), axis=0, weights=val_mass)
        score = float(np.average(horizon_mae, weights=[1, 1, 2, 2]))
        if score < best - 0.0005:
            best, stalled = score, 0
            for index, (layer, bias) in enumerate(
                zip(model.coefs_, model.intercepts_, strict=True)
            ):
                parameters[f"weight_{index}"] = layer.copy()
                parameters[f"bias_{index}"] = bias.copy()
            best_predictions = estimate.copy()
        else:
            stalled += 1
            if stalled == 10:
                break
    if not np.isfinite(best):
        raise ValueError("Neural training did not yield finite validation predictions")
    np.savez(path, **parameters)
    restored = read_neural(path)
    np.testing.assert_allclose(
        neural_predict(x["validation"][:32], restored), best_predictions[:32], atol=1e-5
    )
    return restored


def _selected(predictions: dict[str, Any], choices: list[str]) -> Any:
    return np.column_stack([predictions[profile][:, j] for j, profile in enumerate(choices)])


def run(
    windows: list[Window],
    base: Path,
    output: Path,
    external: str | None,
    neural_from: Path | None,
) -> None:
    name = "pooled" if external is None else f"external-{external}"
    directory = output / name
    directory.mkdir()
    base = base / name
    frozen = json.loads((base / "report.json").read_text(encoding="utf-8"))
    if frozen["selected_on_validation"] != BASE_MODELS["v4"] or frozen["fit_stride"] != 6:
        raise ValueError("The benchmark requires the standard v4 history report")

    parts = patient_partitions(windows, external)
    counts = {role: len(rows) for role, rows in parts.items()}
    if counts != frozen["role_counts"]:
        raise ValueError("Comparison requires identical v4 partition counts")
    x = {
        role: np.asarray([row.features for row in rows], dtype=np.float32)
        for role, rows in parts.items()
    }
    last = {
        role: np.asarray([row.features[11] * 100 for row in rows])[:, None]
        for role, rows in parts.items()
    }
    models: dict[str, tuple[Any, tuple[int, ...] | slice]] = {}
    hashes = {}
    for key, source_name in BASE_MODELS.items():
        path = base / f"{source_name}.json"
        hashes[key] = _sha(path)
        if hashes[key] != frozen["artifact_sha256"][path.name]:
            raise ValueError("Frozen model checksum mismatch")
        model = XGBRegressor(n_jobs=5)
        model.load_model(path)
        models[key] = (model, MODEL_COLUMNS[source_name])
    reuse = neural_from / name if neural_from else None
    reuse_report = (
        json.loads((reuse / "report.json").read_text(encoding="utf-8")) if reuse else None
    )
    if reuse_report is not None and (
        reuse_report["role_counts"] != counts
        or reuse_report["feature_names"] != list(ANALOGUE_FEATURE_NAMES)
    ):
        raise ValueError("Analogue artifact does not match this benchmark split")
    for key, objective in OBJECTIVES.items():
        print(name, key, flush=True)
        path = directory / f"{key}.json"
        if reuse and reuse_report:
            original = reuse / path.name
            if _sha(original) != reuse_report["model_sha256"][key]:
                raise ValueError("Analogue artifact checksum mismatch")
            shutil.copyfile(original, path)
        else:
            model = _fit(objective, parts, x, last)
            model.save_model(path)
        hashes[key] = _sha(path)
        restored = XGBRegressor(n_jobs=5)
        restored.load_model(path)
        if reuse is None:
            np.testing.assert_allclose(
                restored.predict(x["validation"][:32]), model.predict(x["validation"][:32])
            )
        models[key] = (restored, slice(None))
    neural = None
    recipes = RECIPES
    if reuse is not None:
        print(name, "neural", flush=True)
        path = directory / "neural.npz"
        neural = _train_neural(parts, x, last, path)
        hashes["neural"] = _sha(path)
        recipes = RECIPES | NEURAL_RECIPES

    def predict(role: str) -> dict[str, Any]:
        components = {
            key: last[role] + model.predict(x[role][:, columns]) * TARGET_SCALE
            for key, (model, columns) in models.items()
        }
        if neural is not None:
            components["neural"] = last[role] + neural_predict(x[role], neural) * TARGET_SCALE
        return {
            key: sum(mass * components[component] for component, mass in recipe.items())
            for key, recipe in recipes.items()
        }

    validation = predict("validation")
    scores = {
        key: _point_scores(parts["validation"], predictions)["balanced_mae"]
        for key, predictions in validation.items()
    }
    choices = _choose(scores)
    (directory / "selection.json").write_text(
        json.dumps({"validation_mae": scores, "selected_by_horizon": choices}, indent=2),
        encoding="utf-8",
    )
    # Held-out outcomes are scored only after horizon selections have been written.
    test, calibration = predict("test"), predict("calibration")
    rows = parts["test"]
    baseline, selected = test["v4"], _selected(test, choices)
    baseline_result = _point_scores(rows, baseline)
    np.testing.assert_allclose(
        baseline_result["balanced_mae"],
        frozen["test"][BASE_MODELS["v4"]]["balanced_mae"],
        atol=0.005,
    )
    cal_target = np.asarray([row.targets for row in parts["calibration"]])
    cal_predictions = _selected(calibration, choices)
    radii = balanced_quantiles(parts["calibration"], np.abs(cal_predictions - cal_target))
    subgroup_masks = {
        "analogue_available": active_analogues(x["test"]),
        "analogue_unavailable": ~active_analogues(x["test"]),
        "exercise_after_bolus": factor_masks(x["test"])["activity_after_insulin"],
        "rising_at_least_15_in_15min": x["test"][:, HISTORY_FEATURE_NAMES.index("cgm_change_15")]
        >= 0.15,
        "falling_at_least_15_in_15min": x["test"][:, HISTORY_FEATURE_NAMES.index("cgm_change_15")]
        <= -0.15,
    }
    subgroups = {}
    for group, mask in subgroup_masks.items():
        if mask.any():
            matching = [row for row, included in zip(rows, mask, strict=True) if included]
            subgroups[group] = {
                "v4": _point_scores(matching, baseline[mask]),
                "selected": _point_scores(matching, selected[mask]),
            }
    report = {
        "feature_version": ANALOGUE_FEATURE_VERSION,
        "feature_names": ANALOGUE_FEATURE_NAMES,
        "context_policy": "event-time-replay",
        "external_dataset": external,
        "role_counts": counts,
        "validation_mae": scores,
        "selected_by_horizon": choices,
        "test": {
            key: _point_scores(rows, values)
            for key, values in (test | {"selected": selected}).items()
        },
        "paired_selected_minus_v4_ci95": _paired_delta(rows, baseline, selected),
        "test_subgroups": subgroups,
        "test_intervals": interval_metrics(rows, selected, radii),
        "calibration_radii": radii.tolist(),
        "model_sha256": hashes,
    }
    (directory / "report.json").write_text(
        json.dumps(report, indent=2, allow_nan=False), encoding="utf-8"
    )
    print(name, "completed", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("ohio", "azt", "physiocgm", "history", "output"):
        parser.add_argument(f"--{name}", required=True, type=Path)
    parser.add_argument("--context-availability", choices=["event-time-replay"], required=True)
    parser.add_argument(
        "--neural-from",
        type=Path,
        help="Reuse a completed analogue run and add the neural comparison",
    )
    args = parser.parse_args()
    if args.output.resolve().is_relative_to(Path(__file__).resolve().parents[1]):
        parser.error("Research artifacts must remain outside Git")
    args.output.mkdir(parents=True)
    started = time.perf_counter()
    loaders: tuple[tuple[str, Callable[[], tuple[SourceData, ...]]], ...] = (
        ("ohio", lambda: read_ohio(args.ohio, extended_context=True)),
        (
            "physiocgm",
            lambda: tuple(read_physiocgm(p) for p in sorted(args.physiocgm.glob("*.csv"))),
        ),
        ("azt1d", lambda: read_azt1d(args.azt)),
    )
    windows = []
    for dataset, load in loaders:
        raw, _ = make_windows(load(), allow_event_time_replay=True, include_history=True)
        if not raw:
            raise ValueError(f"No eligible windows for {dataset}")
        windows.extend(add_analogue_features(raw))
        print(dataset, len(raw), "windows", flush=True)
    for external in (None, "ohio", "physiocgm", "azt1d"):
        run(windows, args.history, args.output, external, args.neural_from)
    print(f"Completed in {time.perf_counter() - started:.1f}s", flush=True)


if __name__ == "__main__":
    main()
