"""Exploratory recalibration of frozen v1 points; test outcomes never fit scales."""

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
from t1d_forecasting.datasets import read_azt1d, read_ohio, read_physiocgm
from t1d_forecasting.research_metrics import weights
from t1d_forecasting.uncertainty import balanced_quantiles, interval_metrics
from t1d_forecasting.windows import FEATURE_NAMES, make_windows, patient_partitions


def evaluate(windows: Any, original: Path, output: Path, external: str | None) -> dict[str, Any]:
    from xgboost import XGBRegressor

    report = json.loads((original / "report.json").read_text(encoding="utf-8"))
    # Freeze v1's validation-selected context model; no test-dependent model switching.
    selected = report["selected_context_on_validation"]
    if selected != "xgb-context":
        raise ValueError("This protocol expects the frozen v1 context candidate")
    model_path = original / (selected + ".json")
    if (
        hashlib.sha256(model_path.read_bytes()).hexdigest()
        != report["artifact_sha256"][model_path.name]
    ):
        raise ValueError("Frozen point model changed")
    model = XGBRegressor(n_jobs=4)
    model.load_model(model_path)
    parts = patient_partitions(windows, external)
    fingerprint = hashlib.sha256("".join(sorted(w.input_ref for w in windows)).encode()).hexdigest()
    if fingerprint != report["source_fingerprint"]:
        raise ValueError("Source window identity changed")
    x = {k: np.asarray([w.features for w in rows]) for k, rows in parts.items()}
    y = {k: np.asarray([w.targets for w in rows]) for k, rows in parts.items()}
    prediction = {k: model.predict(v) + v[:, 11:12] * 100 for k, v in x.items()}
    # Fixed scale learner: only chronological validation residuals, never calibration/test labels.
    learner = XGBRegressor(
        n_estimators=100,
        max_depth=3,
        learning_rate=0.05,
        objective="reg:squarederror",
        n_jobs=4,
        random_state=20261107,
    )
    learner.fit(
        x["validation"],
        np.abs(y["validation"] - prediction["validation"]),
        sample_weight=weights(parts["validation"]),
        verbose=False,
    )
    scales = {k: np.maximum(1.0, learner.predict(v)) for k, v in x.items()}
    residual = np.abs(y["calibration"] - prediction["calibration"])
    constant = balanced_quantiles(parts["calibration"], residual)
    scaled = balanced_quantiles(parts["calibration"], residual / scales["calibration"])
    radii = {
        "whole-patient-v1": np.asarray(report["calibration_radii"][selected]),
        "balanced-per-forecast-v2": constant,
        "scaled-per-forecast-v2": scales["test"] * scaled,
    }
    result: dict[str, Any] = {
        "protocol": "exploratory-pointwise-intervals-v2",
        "evaluation": report["evaluation"],
        "point_model_sha256": report["artifact_sha256"][model_path.name],
        "source_fingerprint": fingerprint,
        "feature_names": FEATURE_NAMES,
        "nominal_coverage": 0.9,
        "target": "individual forecast, not every forecast of a patient",
        "test_status": (
            "Previously inspected test sources; exploratory re-evaluation, "
            "not new independent confirmation"
        ),
        "calibration": {"constant_radii": constant.tolist(), "scaled_quantiles": scaled.tolist()},
        "by_method": {},
        "limitations": [
            "Patient-balanced empirical quantiles do not imply distribution-free patient coverage",
            "Correlated windows and dataset shift limit nominal coverage claims",
            "Scale learner fits validation residuals only; no test-label tuning",
            "One mg/dL numerical scale floor is not a treatment threshold",
            "Negative lower bounds are counted, never silently clipped",
            "Offline context availability and timezone assumptions remain unchanged",
        ],
    }
    for method, radius in radii.items():
        full = np.broadcast_to(radius, prediction["test"].shape)
        groups = {}
        for dataset in sorted({w.dataset for w in parts["test"]}):
            ids = [i for i, w in enumerate(parts["test"]) if w.dataset == dataset]
            groups[dataset] = interval_metrics(
                [parts["test"][i] for i in ids], prediction["test"][ids], full[ids]
            )
        result["by_method"][method] = {
            "all": interval_metrics(parts["test"], prediction["test"], full),
            "by_dataset": groups,
        }
    output.mkdir(parents=True, exist_ok=False)
    path = output / "residual-scale.json"
    learner.save_model(path)
    restored = XGBRegressor(n_jobs=4)
    restored.load_model(path)
    np.testing.assert_allclose(
        restored.predict(x["validation"][:32]), learner.predict(x["validation"][:32]), rtol=1e-6
    )
    result["scale_model_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    (output / "report.json").write_text(
        json.dumps(result, indent=2, allow_nan=False), encoding="utf-8"
    )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    for flag in ("ohio", "physiocgm", "azt", "original", "output"):
        parser.add_argument("--" + flag, type=Path, required=True)
    args = parser.parse_args()
    if args.output.resolve().is_relative_to(Path(__file__).resolve().parents[1]):
        parser.error("Research artifacts must remain outside Git")
    windows = []
    for name, sources in (
        ("ohio", read_ohio(args.ohio)),
        ("physiocgm", tuple(read_physiocgm(p) for p in sorted(args.physiocgm.glob("*.csv")))),
        ("azt1d", read_azt1d(args.azt)),
    ):
        rows, _ = make_windows(sources, allow_event_time_replay=True)
        windows.extend(rows)
        print("Prepared", name, len(rows), "windows", flush=True)
    reports = {}
    for external in (None, "ohio", "physiocgm", "azt1d"):
        name = "pooled" if external is None else "external-" + external
        reports[name] = evaluate(windows, args.original / name, args.output / name, external)
        print("Evaluated", name, flush=True)
    (args.output / "summary.json").write_text(
        json.dumps(reports, indent=2, allow_nan=False), encoding="utf-8"
    )
