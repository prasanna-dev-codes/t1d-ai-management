"""Warm offline artifact inference timing, not API or clinical performance."""

import argparse
import json
import statistics
from functools import partial
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np


def ridge_prediction(x: Any, mean: Any, scale: Any, coefficient: Any, intercept: Any) -> Any:
    return ((x - mean) / scale) @ coefficient.T + intercept + 140.0


def boost_prediction(model: Any, x: Any) -> Any:
    return model.predict(x) + 140.0


def benchmark(directory: Path, repeats: int = 100) -> dict[str, object]:
    from xgboost import XGBRegressor

    results = {}
    for path in sorted(directory.glob("*.json")):
        if not path.stem.startswith(("ridge-", "xgb-")):
            continue
        if path.stem.startswith("ridge-"):
            payload = json.loads(path.read_text(encoding="utf-8"))
            dimensions = len(payload["feature_names"])
            x = np.zeros((1, dimensions))
            x[:, :12] = 1.4  # Fictional feature input, no patient records.
            mean, scale = np.asarray(payload["mean"]), np.asarray(payload["scale"])
            coefficient, intercept = np.asarray(payload["coef"]), np.asarray(payload["intercept"])

            predict = partial(ridge_prediction, x, mean, scale, coefficient, intercept)
        else:
            model = XGBRegressor(n_jobs=4)
            model.load_model(path)
            x = np.zeros((1, model.n_features_in_))
            x[:, :12] = 1.4

            predict = partial(boost_prediction, model, x)

        predict()
        elapsed = []
        for _ in range(repeats):
            start = perf_counter()
            result = predict()
            elapsed.append((perf_counter() - start) * 1000)
            if result.shape != (1, 4) or not np.isfinite(result).all():
                raise ValueError("Artifact inference validation failed")
        results[path.stem] = {
            "artifact_bytes": path.stat().st_size,
            "repeats": repeats,
            "warm_single_prediction_p50_ms": statistics.median(elapsed),
            "warm_single_prediction_p95_ms": sorted(elapsed)[int(0.95 * (repeats - 1))],
        }
    return {
        "scope": (
            "Warm model computation on fictional features; "
            "excludes I/O, feature extraction, API and DB"
        ),
        "models": results,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = benchmark(args.artifacts)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
