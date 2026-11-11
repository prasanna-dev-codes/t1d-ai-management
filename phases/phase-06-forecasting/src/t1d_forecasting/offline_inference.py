"""Retrospective forecast inference from observed history only, never future labels."""

import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from t1d_forecasting.datasets import OfflineEvent, SourceData
from t1d_forecasting.history_features import HISTORY_LOOKBACK
from t1d_forecasting.history_model import MODEL_COLUMNS, MODEL_WEIGHTS, TARGET_SCALE, factor_masks
from t1d_forecasting.windows import (
    FEATURE_NAMES,
    FEATURE_VERSION,
    HISTORY_FEATURE_NAMES,
    HISTORY_FEATURE_VERSION,
    causal_features,
    causal_history_features,
    detailed_context,
)


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
    return _forecast_result(points, radii) | {
        "model_sha256": actual,
        "feature_version": FEATURE_VERSION,
        "lineage": lineage,
        "method": method,
        "availability": "unverified-event-time-replay"
        if allow_event_time_replay
        else "verified-context-only",
    }


def observed_history_features(
    sources: tuple[SourceData, ...], dataset: str, participant: str
) -> tuple[tuple[float, ...], dict[str, object]]:
    """Apply the training transform to the latest contiguous history within one partition."""
    events = [e for source in sources for e in source.events if e.scope == (dataset, participant)]
    glucose = [
        e for e in events if e.kind == "glucose" and e.value is not None and e.glucose_type == "cgm"
    ]
    if not glucose:
        raise ValueError("No verified CGM history")
    if len({e.timezone_known for e in events}) > 1:
        raise ValueError("Mixed clock representations require review")
    cutoff = max(e.time for e in glucose)
    partitions = {e.partition for e in glucose if e.time == cutoff}
    if len(partitions) != 1:
        raise ValueError("Ambiguous latest source partition")
    partition = partitions.pop()
    start = cutoff - HISTORY_LOOKBACK
    glucose_start = start - timedelta(seconds=5)
    recent = [e for e in glucose if e.partition == partition and e.time >= glucose_start]
    if any(b.time < a.time for a, b in zip(recent, recent[1:], strict=False)):
        raise ValueError("Unresolved clock/order change")
    unique: dict[datetime, OfflineEvent] = {}
    conflicts = set()
    for row in recent:
        if unique.setdefault(row.time, row).value != row.value:
            conflicts.add(row.time)
    segment: list[OfflineEvent] = []
    for row in unique.values():
        if row.time in conflicts:
            continue
        if segment and not 295 <= (row.time - segment[-1].time).total_seconds() <= 305:
            segment = []
        segment.append(row)
    if not segment or segment[-1].time != cutoff:
        raise ValueError("Conflicting latest CGM observations")
    context = sorted(
        (
            e
            for e in events
            if e.partition == partition and e.kind != "glucose" and start <= e.time <= cutoff
        ),
        key=lambda e: e.time,
    )
    detailed = detailed_context(context)
    values = causal_history_features(
        segment,
        len(segment) - 1,
        context,
        [e.time for e in context],
        detailed,
        [e.time for e in detailed],
        True,
    )
    source_hashes = sorted({e.source_sha256 for e in segment + context})
    return values, {
        "input_cutoff_local": cutoff.isoformat(),
        "timezone": "unknown" if cutoff.tzinfo is None else "recorded",
        "input_sha256": hashlib.sha256(
            repr((source_hashes, cutoff.isoformat(), values, HISTORY_FEATURE_VERSION)).encode()
        ).hexdigest(),
        "source_sha256": source_hashes,
    }


def forecast_history(
    sources: tuple[SourceData, ...],
    dataset: str,
    participant: str,
    frozen_directory: Path,
    history_directory: Path,
) -> dict[str, Any]:
    from xgboost import XGBRegressor

    report_path = history_directory / "report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if (
        report["feature_version"] != HISTORY_FEATURE_VERSION
        or report["feature_names"] != list(HISTORY_FEATURE_NAMES)
        or report["context_policy"] != "event-time-replay"
    ):
        raise ValueError("History model feature version, order or context policy mismatch")
    values, lineage = observed_history_features(sources, dataset, participant)
    matrix = np.asarray([values], dtype=np.float32)
    profile = report["selected_on_validation"]
    if profile not in MODEL_WEIGHTS:
        raise ValueError("Unsupported history model profile")
    points = np.full((1, 4), values[11] * 100)
    artifacts = {}
    for component, weight in MODEL_WEIGHTS[profile].items():
        if component == "frozen-v1":
            path = frozen_directory / "xgb-context.json"
            expected = report["frozen_model_sha256"]
            scale = 1.0
        else:
            path = history_directory / f"{component}.json"
            expected = report["artifact_sha256"][path.name]
            scale = TARGET_SCALE
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError("Point model checksum mismatch")
        columns = MODEL_COLUMNS[component]
        model = XGBRegressor(n_jobs=4)
        model.load_model(path)
        if model.n_features_in_ != len(columns):
            raise ValueError("Point model dimensions mismatch")
        residual = model.predict(matrix[:, columns])
        if residual.shape != (1, 4):
            raise ValueError("Point model horizon mismatch")
        points += (residual * scale).astype(float) * weight
        artifacts[component] = actual
    return _forecast_result(points, np.asarray([report["calibration_radii"]], dtype=float)) | {
        "model_sha256": artifacts,
        "model_profile": profile,
        "feature_version": HISTORY_FEATURE_VERSION,
        "lineage": lineage,
        "method": "balanced-per-forecast-history",
        "availability": "unverified-event-time-replay",
        "observed_factor_flags": {key: bool(mask[0]) for key, mask in factor_masks(matrix).items()},
    }


def _forecast_result(points: Any, radii: Any) -> dict[str, Any]:
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
        "nominal_coverage": 0.9,
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
