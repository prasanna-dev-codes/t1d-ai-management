"""Retrospective forecast inference from observed history only, never future labels."""

import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from t1d_forecasting.datasets import OfflineEvent, SourceData
from t1d_forecasting.windows import FEATURE_NAMES, FEATURE_VERSION, causal_features


def observed_features(
    sources: tuple[SourceData, ...], dataset: str, participant: str, allow_event_time_replay: bool
) -> tuple[Any, dict[str, object]]:
    events = [e for s in sources for e in s.events if e.scope == (dataset, participant)]
    glucose = [
        e for e in events if e.kind == "glucose" and e.value is not None and e.glucose_type == "cgm"
    ]
    if not glucose:
        raise ValueError("No verified CGM history")
    cutoff = max(e.time for e in glucose)
    recent = [e for e in glucose if e.time >= cutoff - timedelta(minutes=65)]
    if any(b.time < a.time for a, b in zip(recent, recent[1:], strict=False)):
        raise ValueError("Unresolved clock/order change")
    unique: dict[datetime, OfflineEvent] = {}
    for e in recent:
        if e.time in unique and unique[e.time].value != e.value:
            raise ValueError("Conflicting observations")
        unique[e.time] = e
    inputs = list(unique.values())[-12:]
    if any(e.available_at is not None and e.available_at > cutoff for e in inputs):
        raise ValueError("Observation unavailable at cutoff")
    context = sorted(
        (e for e in events if e.kind != "glucose" and e.time <= cutoff), key=lambda e: e.time
    )
    values = causal_features(inputs, context, [e.time for e in context], allow_event_time_replay)
    source_hashes = sorted({e.source_sha256 for e in inputs + context})
    identity = hashlib.sha256(
        repr(
            (source_hashes, cutoff.isoformat(), values, FEATURE_VERSION, allow_event_time_replay)
        ).encode()
    ).hexdigest()
    return np.asarray([values]), {
        "input_cutoff_local": cutoff.isoformat(),
        "timezone": "unknown" if cutoff.tzinfo is None else "recorded",
        "input_sha256": identity,
        "source_sha256": source_hashes,
    }


def forecast(
    sources: tuple[SourceData, ...],
    dataset: str,
    participant: str,
    model_directory: Path,
    uncertainty_directory: Path,
    method: str,
    allow_event_time_replay: bool,
) -> dict[str, Any]:
    from xgboost import XGBRegressor

    x, lineage = observed_features(sources, dataset, participant, allow_event_time_replay)
    report = json.loads((model_directory / "report.json").read_text(encoding="utf-8"))
    intervals = json.loads((uncertainty_directory / "report.json").read_text(encoding="utf-8"))
    if report["feature_version"] != FEATURE_VERSION or intervals["feature_names"] != list(
        FEATURE_NAMES
    ):
        raise ValueError("Feature version/order mismatch")
    path = model_directory / "xgb-context.json"
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != report["artifact_sha256"][path.name] or actual != intervals["point_model_sha256"]:
        raise ValueError("Point model checksum mismatch")
    model = XGBRegressor(n_jobs=4)
    model.load_model(path)
    if model.n_features_in_ != x.shape[1]:
        raise ValueError("Point model dimensions mismatch")
    points = model.predict(x) + x[:, 11:12] * 100
    if method == "balanced-per-forecast-v2":
        radii = np.asarray(intervals["calibration"]["constant_radii"])[None, :]
    elif method == "scaled-per-forecast-v2":
        scale_path = uncertainty_directory / "residual-scale.json"
        if hashlib.sha256(scale_path.read_bytes()).hexdigest() != intervals["scale_model_sha256"]:
            raise ValueError("Scale model checksum mismatch")
        scale = XGBRegressor(n_jobs=4)
        scale.load_model(scale_path)
        radii = np.maximum(1.0, scale.predict(x)) * np.asarray(
            intervals["calibration"]["scaled_quantiles"]
        )
    else:
        raise ValueError("Select an explicit supported interval method")
    if (
        points.shape != (1, 4)
        or radii.shape != (1, 4)
        or not np.isfinite(points).all()
        or not np.isfinite(radii).all()
        or (radii < 0).any()
    ):
        raise ValueError("Invalid forecast computation")
    # No positive-clipping fiction: invalid physical-domain intervals abstain.
    eligible = bool((points - radii > 0).all())
    return {
        "status": "eligible_offline_research" if eligible else "abstained",
        "experimental": True,
        "review_required": True,
        "model_sha256": actual,
        "feature_version": FEATURE_VERSION,
        "lineage": lineage,
        "method": method,
        "nominal_coverage": 0.9,
        "availability": "unverified-event-time-replay"
        if allow_event_time_replay
        else "verified-context-only",
        "points": [
            {
                "horizon_minutes": h,
                "glucose_mg_dl": float(points[0, j]),
                "lower_mg_dl": float(points[0, j] - radii[0, j]),
                "upper_mg_dl": float(points[0, j] + radii[0, j]),
            }
            for j, h in enumerate((30, 60, 90, 120))
        ]
        if eligible
        else [],
        "reason_codes": [] if eligible else ["INTERVAL_OUTSIDE_POSITIVE_DOMAIN"],
        "warnings": [
            "OFFLINE_RESEARCH_ONLY",
            "EXPLORATORY_INTERVALS",
            "NOT_FOR_TREATMENT_DECISIONS",
            "CONTEXT_MAY_BE_MISSING",
            "NO_FUTURE_LABELS_USED",
            "LIVE_SERVING_NOT_ENABLED",
        ],
    }
