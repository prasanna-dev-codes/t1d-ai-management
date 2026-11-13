"""Verify offline model exports against their recorded hashes; no live promotion."""

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
from t1d_forecasting.windows import CGM_FEATURES, FEATURE_NAMES, FEATURE_VERSION


def ridge_parameters(payload: dict[str, Any], columns: int) -> tuple[Any, ...]:
    names = payload["feature_names"]
    if names != list(FEATURE_NAMES[:columns]) or payload["residual_base"] != "last_glucose":
        raise ValueError("Unsupported feature order or residual base")
    arrays = tuple(
        np.asarray(payload[key], dtype=float) for key in ("mean", "scale", "coef", "intercept")
    )
    if [a.shape for a in arrays] != [(columns,), (columns,), (4, columns), (4,)]:
        raise ValueError("Invalid ridge dimensions")
    if not all(np.isfinite(a).all() for a in arrays) or not (arrays[1] > 0).all():
        raise ValueError("Invalid ridge parameters")
    return arrays


def verify(directory: Path) -> dict[str, object]:
    from xgboost import XGBRegressor

    report = json.loads((directory / "report.json").read_text(encoding="utf-8"))
    if report["feature_version"] != FEATURE_VERSION:
        raise ValueError("Unsupported feature version")
    checked = []
    for name in ("ridge-cgm", "ridge-context", "xgb-cgm", "xgb-context"):
        path = directory / (name + ".json")
        if path.stat().st_size > 50_000_000:
            raise ValueError("Artifact exceeds verification limit")
        raw = path.read_bytes()
        sha = hashlib.sha256(raw).hexdigest()
        if sha != report["artifact_sha256"][path.name]:
            raise ValueError("Artifact checksum mismatch")
        columns = len(CGM_FEATURES) if name.endswith("cgm") else len(FEATURE_NAMES)
        example = np.zeros((1, columns))
        example[:, :12] = 1.4  # Fictional vector; no records or predictions exported.
        if name.startswith("ridge"):
            mean, scale, coefficient, intercept = ridge_parameters(json.loads(raw), columns)
            prediction = ((example - mean) / scale) @ coefficient.T + intercept + 140.0
        else:
            model = XGBRegressor(n_jobs=4)
            model.load_model(path)
            if model.n_features_in_ != columns:
                raise ValueError("Invalid boosted-tree feature count")
            prediction = model.predict(example) + 140.0
        if prediction.shape != (1, 4) or not np.isfinite(prediction).all():
            raise ValueError("Artifact inference failed")
        checked.append({"model": name, "sha256": sha, "finite_four_horizon_output": True})
    return {
        "evaluation": report["evaluation"],
        "checked": checked,
        "scope": (
            "Local consistency and loadability; not independent authenticity or clinical validation"
        ),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = verify(args.artifacts)
    output = json.dumps(result, indent=2)
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    print(output)
