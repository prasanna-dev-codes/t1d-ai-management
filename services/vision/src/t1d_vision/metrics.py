"""Deterministic metrics; caller must distinguish engineering fixtures from food evaluation."""

import math
from typing import Any, Literal

import numpy as np
from numpy.typing import NDArray

Array = NDArray[np.float64]


def probabilities(logits: Array, temperature: float = 1) -> Array:
    x = np.asarray(logits, dtype=np.float64)
    if (
        x.ndim != 2
        or x.shape[0] < 1
        or x.shape[1] < 2
        or not np.isfinite(x).all()
        or not math.isfinite(temperature)
        or temperature <= 0
    ):
        raise ValueError("Invalid logits or temperature")
    x = x / temperature
    shifted = x - x.max(axis=1, keepdims=True)
    values = np.exp(shifted)
    return np.asarray(values / values.sum(axis=1, keepdims=True), dtype=np.float64)


def validated(p: Array, y: NDArray[np.int64]) -> tuple[Array, NDArray[np.int64]]:
    p = np.asarray(p, dtype=np.float64)
    y = np.asarray(y)
    if (
        p.ndim != 2
        or p.shape[0] < 1
        or p.shape[1] < 2
        or y.shape != (p.shape[0],)
        or not np.issubdtype(y.dtype, np.integer)
    ):
        raise ValueError("Metric shape/type mismatch")
    if (
        not np.isfinite(p).all()
        or (p < 0).any()
        or (p > 1).any()
        or not np.allclose(p.sum(axis=1), 1, atol=1e-8, rtol=0)
        or (y < 0).any()
        or (y >= p.shape[1]).any()
    ):
        raise ValueError("Invalid probabilities or class indices")
    return p, np.asarray(y, dtype=np.int64)


def evaluate(p: Array, y: NDArray[np.int64], bins: int = 15) -> dict[str, Any]:
    p, y = validated(p, y)
    if not 2 <= bins <= 100:
        raise ValueError("Invalid calibration bin count")
    n, c = p.shape
    predicted = p.argmax(axis=1)
    confusion = np.zeros((c, c), dtype=np.int64)
    np.add.at(confusion, (y, predicted), 1)
    support = confusion.sum(axis=1)
    guessed = confusion.sum(axis=0)
    tp = np.diag(confusion)
    precision = np.divide(tp, guessed, out=np.zeros(c, dtype=float), where=guessed > 0)
    recall = np.divide(tp, support, out=np.zeros(c, dtype=float), where=support > 0)
    f1 = np.divide(
        2 * precision * recall,
        precision + recall,
        out=np.zeros(c, dtype=float),
        where=precision + recall > 0,
    )
    topk = min(3, c)
    rank = np.argsort(-p, axis=1, kind="stable")
    confidence = p.max(axis=1)
    correct = predicted == y
    bin_ids = np.minimum((confidence * bins).astype(int), bins - 1)
    ece = 0.0
    for i in range(bins):
        mask = bin_ids == i
        if mask.any():
            ece += float(mask.mean() * abs(correct[mask].mean() - confidence[mask].mean()))
    truth = np.eye(c)[y]
    eps = 1e-12
    return {
        "samples": n,
        "classes": c,
        "top1": float(correct.mean()),
        "top3": float((rank[:, :topk] == y[:, None]).any(axis=1).mean()),
        "topk_effective": topk,
        "macro_f1": float(f1.mean()),
        "weighted_f1": float(np.sum(f1 * support) / n),
        "precision": precision.tolist(),
        "recall": recall.tolist(),
        "class_f1": f1.tolist(),
        "support": support.tolist(),
        "confusion_matrix": confusion.tolist(),
        "nll": float(-np.log(np.maximum(p[np.arange(n), y], eps)).mean()),
        "nll_epsilon": eps,
        "brier": float(((p - truth) ** 2).sum(axis=1).mean()),
        "ece": ece,
        "ece_bins": bins,
        "zero_support_policy": "zero precision/recall/F1; retain class in macro average",
    }


def temperature_scale(
    logits: Array, y: NDArray[np.int64], role: Literal["train", "validation", "calibration", "test"]
) -> float:
    if role != "calibration":
        raise ValueError("Temperature fitting requires calibration split")
    probabilities(logits)
    validated(probabilities(logits), y)
    if len(set(y.tolist())) < 2:
        raise ValueError("Calibration needs at least two observed classes")

    def objective(log_t: float) -> float:
        p = probabilities(logits, math.exp(log_t))
        return float(-np.log(np.maximum(p[np.arange(len(y)), y], 1e-12)).mean())

    lo, hi = -3.0, 3.0
    ratio = (math.sqrt(5) - 1) / 2
    for _ in range(70):
        left = hi - ratio * (hi - lo)
        right = lo + ratio * (hi - lo)
        if objective(left) < objective(right):
            hi = right
        else:
            lo = left
    return math.exp((lo + hi) / 2)


def risk_coverage(p: Array, y: NDArray[np.int64]) -> list[dict[str, float]]:
    p, y = validated(p, y)
    order = np.argsort(-p.max(axis=1), kind="stable")
    error = (p.argmax(axis=1) != y)[order]
    return [
        {"coverage": float(k / len(y)), "risk": float(error[:k].mean())}
        for k in sorted(set(max(1, round(len(y) * fraction / 10)) for fraction in range(1, 11)))
    ]
