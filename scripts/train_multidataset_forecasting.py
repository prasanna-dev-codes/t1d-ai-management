"""Offline three-dataset research training; raw records/models never enter Git."""

import argparse
import hashlib
import json
import platform
import time
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
from t1d_forecasting.datasets import SourceData, read_azt1d, read_ohio, read_physiocgm
from t1d_forecasting.research_metrics import calibrate, macro_mae, metrics, weights
from t1d_forecasting.windows import (
    CGM_FEATURES,
    FEATURE_NAMES,
    FEATURE_VERSION,
    Window,
    make_windows,
    patient_partitions,
)


def run(windows: list[Window], output: Path, external: str | None = None) -> dict[str, object]:
    from sklearn.linear_model import Ridge
    from sklearn.preprocessing import StandardScaler
    from xgboost import XGBRegressor

    if output.exists() and any(output.iterdir()):
        raise ValueError("Use a fresh output directory; preserve prior experiments")
    output.mkdir(parents=True, exist_ok=True)
    parts = patient_partitions(windows, external)
    x = {
        role: np.asarray([w.features for w in rows], dtype=np.float64)
        for role, rows in parts.items()
    }
    y = {
        role: np.asarray([w.targets for w in rows], dtype=np.float64)
        for role, rows in parts.items()
    }
    base = {role: data[:, 11:12] * 100 for role, data in x.items()}
    sample_weights = weights(parts["fit"])
    predictions: dict[str, dict[str, Any]] = {}
    metadata: dict[str, object] = {}
    for name in ("persistence", "linear", "ridge-cgm", "ridge-context", "xgb-cgm", "xgb-context"):
        print("Training", output.name, name, flush=True)
        started = time.perf_counter()
        values: dict[str, Any] = {}
        columns = len(CGM_FEATURES) if name.endswith("cgm") else len(FEATURE_NAMES)
        if name == "persistence":
            values = {role: np.repeat(value, 4, axis=1) for role, value in base.items()}
        elif name == "linear":
            values = {
                role: base[role] + matrix[:, 14:15] * 10 * np.asarray([[30, 60, 90, 120]])
                for role, matrix in x.items()
            }
        elif name.startswith("ridge"):
            scaler = StandardScaler().fit(x["fit"][:, :columns], sample_weight=sample_weights)
            model = Ridge(alpha=1.0, solver="svd").fit(
                scaler.transform(x["fit"][:, :columns]),
                y["fit"] - base["fit"],
                sample_weight=sample_weights,
            )
            values = {
                role: model.predict(scaler.transform(matrix[:, :columns])) + base[role]
                for role, matrix in x.items()
            }
            payload = {
                "feature_names": FEATURE_NAMES[:columns],
                "residual_base": "last_glucose",
                "mean": scaler.mean_.tolist(),
                "scale": scaler.scale_.tolist(),
                "coef": model.coef_.tolist(),
                "intercept": model.intercept_.tolist(),
            }
            (output / (name + ".json")).write_text(
                json.dumps(payload, allow_nan=False), encoding="utf-8"
            )
        else:
            model = XGBRegressor(
                n_estimators=200,
                max_depth=5,
                learning_rate=0.05,
                objective="reg:squarederror",
                tree_method="hist",
                n_jobs=4,
                random_state=20261107,
                early_stopping_rounds=20,
            )
            model.fit(
                x["fit"][:, :columns],
                y["fit"] - base["fit"],
                sample_weight=sample_weights,
                eval_set=[(x["validation"][:, :columns], y["validation"] - base["validation"])],
                sample_weight_eval_set=[weights(parts["validation"])],
                verbose=False,
            )
            values = {
                role: model.predict(matrix[:, :columns]) + base[role] for role, matrix in x.items()
            }
            model.save_model(output / (name + ".json"))
            restored = XGBRegressor()
            restored.load_model(output / (name + ".json"))
            np.testing.assert_allclose(
                restored.predict(x["validation"][:32, :columns]) + base["validation"][:32],
                values["validation"][:32],
                rtol=1e-6,
            )
        elapsed = time.perf_counter() - started
        predictions[name] = values
        metadata[name] = {
            "fit_and_evaluation_seconds": elapsed,
            "validation_dataset_patient_macro_mae": macro_mae(
                parts["validation"], values["validation"]
            ),
        }
    # Selection is fixed using validation only, before calibration/test metrics are summarized.
    chosen = min(
        predictions,
        key=lambda name: macro_mae(parts["validation"], predictions[name]["validation"]),
    )
    chosen_context = min(
        ("ridge-context", "xgb-context"),
        key=lambda name: macro_mae(parts["validation"], predictions[name]["validation"]),
    )
    report: dict[str, object] = {
        "evaluation": "pooled-patient-disjoint" if external is None else "external-" + external,
        "feature_version": FEATURE_VERSION,
        "partitions": {
            role: {
                "windows": len(rows),
                "patients": len({w.scope for w in rows}),
                "by_dataset": dict(Counter(w.dataset for w in rows)),
            }
            for role, rows in parts.items()
        },
        "selected_on_validation": chosen,
        "selected_context_on_validation": chosen_context,
        "training": metadata,
    }
    results = {}
    calibration = {}
    for name, value in predictions.items():
        radii = calibrate(parts["calibration"], value["calibration"])
        calibration[name] = radii.tolist()
        by_dataset = {}
        for dataset in sorted({w.dataset for w in parts["test"]}):
            indices = [i for i, w in enumerate(parts["test"]) if w.dataset == dataset]
            by_dataset[dataset] = metrics(
                [parts["test"][i] for i in indices], value["test"][indices], radii
            )
        results[name] = {
            "all": metrics(parts["test"], value["test"], radii),
            "by_dataset": by_dataset,
        }
    report["source_fingerprint"] = hashlib.sha256(
        "".join(sorted(w.input_ref for w in windows)).encode()
    ).hexdigest()
    report["test_results"] = results
    report["calibration_radii"] = calibration
    report["artifact_sha256"] = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in output.glob("*.json")
    }
    (output / "report.json").write_text(
        json.dumps(report, indent=2, allow_nan=False), encoding="utf-8"
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ohio", type=Path, required=True)
    parser.add_argument("--physiocgm", type=Path, required=True)
    parser.add_argument("--azt", type=Path, required=True, help="Inner original AZT1D 2025.zip")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--context-availability",
        choices=["verified-only", "event-time-replay"],
        required=True,
        help="Explicit approved research assumption; no implicit replay",
    )
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    if args.output.resolve().is_relative_to(repo):
        parser.error("Research records and trained models must remain outside Git")
    started = time.perf_counter()
    print("Building scoped windows for all three datasets", flush=True)
    windows = []
    inventory = {}
    loaders: dict[str, Callable[[], tuple[SourceData, ...]]] = {
        "ohio": lambda: read_ohio(args.ohio),
        "physiocgm": lambda: tuple(read_physiocgm(p) for p in sorted(args.physiocgm.glob("*.csv"))),
        "azt1d": lambda: read_azt1d(args.azt),
    }
    for dataset, loader in loaders.items():
        source = loader()
        rows, inventory[dataset] = make_windows(
            source, allow_event_time_replay=args.context_availability == "event-time-replay"
        )
        windows.extend(rows)
        print(dataset, len(rows), "eligible windows", flush=True)
        del source
    if {w.dataset for w in windows} != {"ohio", "physiocgm", "azt1d"}:
        raise ValueError("All three datasets must contribute eligible windows")
    args.output.mkdir(parents=True, exist_ok=True)
    summary: dict[str, Any] = {
        "protocol": "three-dataset-context-replay-v1",
        "python": platform.python_version(),
        "inventory": inventory,
        "data_assumptions": [
            "Unknown timezone retained; local elapsed time only; no UTC conversion",
            "Context policy: " + args.context_availability,
            "Context absence is unknown, not verified zero exposure",
            "Subject 14 mixed CGM/BGM retained but excluded from glucose training",
            "Calibration nominal 90% is not a clinical or domain-shift guarantee",
            "Shared-cohort aliases across datasets cannot be excluded by timestamps alone",
            "API real-data serving is unchanged and remains blocked",
        ],
        "runs": {},
    }
    for external in (None, "ohio", "physiocgm", "azt1d"):
        name = "pooled" if external is None else "external-" + external
        summary["runs"][name] = run(windows, args.output / name, external)
    summary["total_seconds"] = time.perf_counter() - started
    (args.output / "summary.json").write_text(
        json.dumps(summary, indent=2, allow_nan=False), encoding="utf-8"
    )
    print("Completed all three-dataset experiments", flush=True)


if __name__ == "__main__":
    main()
