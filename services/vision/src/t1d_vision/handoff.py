"""Offline cloud-export inventory. Never extracts archives or deserializes checkpoints."""

import hashlib
import json
from pathlib import Path
from typing import Any

from t1d_vision.artifacts import child_path

LIMITS = {
    "manifest.json": 1024**2,
    "evaluation.json": 1024**2,
    "class-map.json": 1024**2,
    "experiment.json": 1024**2,
    "environment.json": 1024**2,
    "split-summary.json": 1024**2,
    "metrics.jsonl": 10 * 1024**2,
    "model.onnx": 100 * 1024**2,
    "best.pt": 256 * 1024**2,
    "last.pt": 256 * 1024**2,
}
REQUIRED = {
    "manifest.json",
    "evaluation.json",
    "class-map.json",
    "experiment.json",
    "environment.json",
    "split-summary.json",
    "model.onnx",
}


def inventory(root: Path) -> dict[str, Any]:
    paths = list(root.iterdir())
    if any(p.is_symlink() or p.is_dir() for p in paths):
        raise ValueError("Flat export only; directories/symlinks forbidden")
    names = {p.name for p in paths}
    names.discard("bundle-index.json")
    if not REQUIRED <= names or not names <= set(LIMITS):
        raise ValueError("Missing required or non-allowlisted export file")
    entries = []
    total = 0
    for name in sorted(names):
        path = child_path(root, name, LIMITS[name])
        total += path.stat().st_size
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            while chunk := stream.read(1024**2):
                digest.update(chunk)
        entries.append({"file": name, "bytes": path.stat().st_size, "sha256": digest.hexdigest()})
    if total > 700 * 1024**2:
        raise ValueError("Export size budget exceeded")
    return {
        "schema_version": "1.0",
        "files": entries,
        "total_bytes": total,
        "checkpoint_policy": "inventory only; never execute untrusted pickle; "
        "future trusted loader must use weights_only=True and identity checks",
    }


def verify_inventory(root: Path) -> dict[str, Any]:
    expected = json.loads(child_path(root, "bundle-index.json", 1024**2).read_bytes())
    actual = inventory(root)
    if actual != expected:
        raise ValueError("Export inventory mismatch")
    return actual
