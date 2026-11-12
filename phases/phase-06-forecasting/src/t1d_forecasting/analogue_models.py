"""Artifact recipes for the offline CGM trajectory comparisons."""

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from t1d_forecasting.analogues import ANALOGUE_FEATURE_NAMES, ANALOGUE_FEATURE_VERSION
from t1d_forecasting.history_model import MODEL_COLUMNS, TARGET_SCALE

BASE_MODELS = {"v4": "long-context-huber", "v4-cgm": "long-cgm"}
ANALOGUE_MODELS = ("analogue-huber", "analogue-l1")
RECIPES = {
    "v4": {"v4": 1.0},
    "v4-cgm": {"v4-cgm": 1.0},
    "analogue-huber": {"analogue-huber": 1.0},
    "analogue-l1": {"analogue-l1": 1.0},
    "analogue-blend": {"analogue-huber": 0.5, "analogue-l1": 0.5},
    "v4-analogue-blend": {"v4": 0.5, "analogue-huber": 0.5},
}
NEURAL_RECIPES = {
    "neural": {"neural": 1.0},
    "v4-neural-blend": {"v4": 0.5, "neural": 0.5},
    "analogue-neural-blend": {"analogue-huber": 0.5, "neural": 0.5},
    "three-model-blend": {"v4": 0.4, "analogue-huber": 0.3, "neural": 0.3},
}
NEURAL_LAYERS = (96, 48, 24)
NEURAL_OUTPUT_SCALE = np.asarray([1.0, 1.0, 1.2, 1.35], dtype=np.float32)


def read_neural(path: Path) -> dict[str, Any]:
    sizes = (len(ANALOGUE_FEATURE_NAMES), *NEURAL_LAYERS, 4)
    shapes: dict[str, tuple[int, ...]] = {"mean": (sizes[0],), "scale": (sizes[0],)}
    for index, (width, output) in enumerate(zip(sizes, sizes[1:], strict=False)):
        shapes[f"weight_{index}"] = (width, output)
        shapes[f"bias_{index}"] = (output,)
    with np.load(path, allow_pickle=False) as artifact:
        if set(artifact.files) != set(shapes):
            raise ValueError("Unexpected neural forecast parameters")
        parameters = {key: np.asarray(artifact[key], dtype=np.float32) for key in shapes}
    if (
        any(
            parameters[key].shape != shape or not np.isfinite(parameters[key]).all()
            for key, shape in shapes.items()
        )
        or (parameters["scale"] <= 0).any()
    ):
        raise ValueError("Invalid neural forecast parameters")
    return parameters


def neural_predict(matrix: Any, parameters: dict[str, Any]) -> Any:
    state = np.clip((matrix - parameters["mean"]) / parameters["scale"], -8, 8)
    for index in range(len(NEURAL_LAYERS)):
        state = np.maximum(state @ parameters[f"weight_{index}"] + parameters[f"bias_{index}"], 0)
    final = len(NEURAL_LAYERS)
    return (
        state @ parameters[f"weight_{final}"] + parameters[f"bias_{final}"]
    ) / NEURAL_OUTPUT_SCALE


def predict_frozen(
    matrix: Any, last: Any, history_directory: Path, analogue_directory: Path
) -> tuple[Any, dict[str, Any], dict[str, str]]:
    """Replay the exported Phase 06 point forecast on one or more feature rows."""
    from xgboost import XGBRegressor

    report = json.loads((analogue_directory / "report.json").read_text(encoding="utf-8"))
    if (
        report["feature_version"] != ANALOGUE_FEATURE_VERSION
        or report["feature_names"] != list(ANALOGUE_FEATURE_NAMES)
        or report["context_policy"] != "event-time-replay"
    ):
        raise ValueError("Analogue model feature version, order or context policy mismatch")
    recipes = RECIPES | NEURAL_RECIPES
    profiles = report["selected_by_horizon"]
    if (
        not isinstance(profiles, list)
        or len(profiles) != 4
        or any(not isinstance(key, str) or key not in recipes for key in profiles)
    ):
        raise ValueError("Invalid horizon model profiles")
    if matrix.ndim != 2 or matrix.shape[1] != len(ANALOGUE_FEATURE_NAMES):
        raise ValueError("Invalid analogue feature dimensions")
    if (
        last.shape != (len(matrix), 1)
        or not np.isfinite(matrix).all()
        or not np.isfinite(last).all()
    ):
        raise ValueError("Invalid analogue inputs")
    components, artifacts = {}, {}
    for key in sorted({key for profile in profiles for key in recipes[profile]}):
        if key in BASE_MODELS:
            base_name = BASE_MODELS[key]
            path = history_directory / f"{base_name}.json"
            inputs = matrix[:, MODEL_COLUMNS[base_name]]
        elif key in ANALOGUE_MODELS:
            path = analogue_directory / f"{key}.json"
            inputs = matrix
        elif key == "neural":
            path = analogue_directory / "neural.npz"
            inputs = matrix
        else:
            raise ValueError("Unknown analogue model component")
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != report["model_sha256"][key]:
            raise ValueError("Point model checksum mismatch")
        if key == "neural":
            residual = neural_predict(inputs, read_neural(path))
        else:
            model = XGBRegressor(n_jobs=4)
            model.load_model(path)
            if model.n_features_in_ != inputs.shape[1]:
                raise ValueError("Point model dimensions mismatch")
            residual = model.predict(inputs)
        if residual.shape != (len(matrix), 4) or not np.isfinite(residual).all():
            raise ValueError("Point model horizon mismatch")
        components[key] = (residual * TARGET_SCALE).astype(float) + last
        artifacts[key] = actual
    points = np.column_stack(
        [
            sum(components[key][:, horizon] * mass for key, mass in recipes[profile].items())
            for horizon, profile in enumerate(profiles)
        ]
    )
    return points, report, artifacts
