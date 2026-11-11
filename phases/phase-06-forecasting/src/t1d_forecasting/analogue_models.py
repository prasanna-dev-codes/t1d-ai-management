"""Artifact recipes for the offline CGM trajectory comparisons."""

from pathlib import Path
from typing import Any

import numpy as np

from t1d_forecasting.analogues import ANALOGUE_FEATURE_NAMES

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
