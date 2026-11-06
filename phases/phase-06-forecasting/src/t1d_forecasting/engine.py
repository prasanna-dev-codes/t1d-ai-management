"""Deterministic feature/forecast engine with explicit technical abstention."""

import hashlib
import json
import math
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta
from importlib.resources import files
from uuid import UUID

from t1d_forecasting.contracts import (
    ForecastModel,
    ForecastPoint,
    Horizon,
    ModelBundle,
    Reading,
)


class Abstain(ValueError):
    pass


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


@dataclass(frozen=True)
class Snapshot:
    features: tuple[float, ...]
    readings: tuple[Reading, ...]
    cutoff: datetime
    sha256: str


def snapshot(readings: list[Reading], cutoff: datetime) -> Snapshot:
    if cutoff.utcoffset() is None:
        raise ValueError("Zoned cutoff required")
    visible = [
        r
        for r in readings
        if r.event_time <= cutoff
        and r.available_at <= cutoff
        and r.event_time >= cutoff - timedelta(minutes=65)
    ]
    if not visible:
        raise Abstain("NO_CGM_HISTORY")
    # Do not substitute older accepted data for a questionable current observation.
    if any(r.quality != "accepted" or not r.valid_sensor for r in visible):
        raise Abstain("CGM_QUALITY_UNRESOLVED")
    grouped: dict[datetime, list[Reading]] = {}
    for row in visible:
        grouped.setdefault(row.event_time, []).append(row)
    if any(len(rows) > 1 for rows in grouped.values()):
        raise Abstain("AMBIGUOUS_CGM_SENSORS")
    ordered = tuple(sorted(visible, key=lambda r: (r.event_time, r.id.int))[-12:])
    age = (cutoff - ordered[-1].event_time).total_seconds() / 60
    if age > 5:
        raise Abstain("STALE_CGM")
    if len(ordered) != 12:
        raise Abstain("INSUFFICIENT_CGM_HISTORY")
    if any(
        (b.event_time - a.event_time).total_seconds() != 300
        for a, b in zip(ordered, ordered[1:], strict=False)
    ):
        raise Abstain("IRREGULAR_CGM_GRID")
    values: list[float] = []
    for row in ordered:
        if row.value is None:
            raise Abstain("MISSING_CGM_VALUE")
        values.append(row.value if row.unit == "mg/dL" else row.value / 0.0555)
    mean = statistics.mean(values)
    # OLS slope over the observed 55-minute window, never over future labels.
    slope = sum((5 * i - 27.5) * (v - mean) for i, v in enumerate(values)) / 3575
    features = (
        1.0,
        values[-1] / 100,
        mean / 100,
        slope / 10,
        statistics.pstdev(values) / 100,
        age / 5,
    )
    if not all(math.isfinite(x) for x in features):
        raise Abstain("NONFINITE_FEATURES")
    identity = digest(
        {
            "cutoff": cutoff.isoformat(),
            "readings": [r.model_dump(mode="json") for r in ordered],
            "features": features,
        }
    )
    return Snapshot(features, ordered, cutoff, identity)


def point_value(features: tuple[float, ...], model: ForecastModel, horizon: Horizon) -> float:
    parameters = next(p for p in model.horizons if p.horizon == horizon)
    if model.profile == "persistence-v1":
        return features[1] * 100
    if model.profile == "linear-v1":
        return features[1] * 100 + features[3] * 10 * (horizon + features[5] * 5)
    return sum(a * b for a, b in zip(features, parameters.weights, strict=True))


def predict(
    state: Snapshot, model: ForecastModel, horizons: tuple[Horizon, ...]
) -> list[ForecastPoint]:
    points = []
    for horizon in sorted(horizons):
        parameters = next(p for p in model.horizons if p.horizon == horizon)
        value = point_value(state.features, model, horizon)
        if not math.isfinite(value) or value - parameters.radius <= 0:
            raise Abstain("FORECAST_OUTSIDE_MODEL_DOMAIN")
        points.append(
            ForecastPoint(
                horizon_minutes=horizon,
                target_time=state.cutoff + timedelta(minutes=horizon),
                glucose_mg_dl=value,
                lower_mg_dl=value - parameters.radius,
                upper_mg_dl=value + parameters.radius,
            )
        )
    return points


def load_bundle() -> tuple[ModelBundle, str, UUID]:
    # A fixed package resource, never a request-controlled path or pickle.
    from t1d_forecasting.manifest import ARTIFACT_SHA256

    path = files("t1d_forecasting").joinpath("artifacts/synthetic-v1.json")
    raw = path.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != ARTIFACT_SHA256:
        raise ValueError("Forecast artifact integrity failure")
    return ModelBundle.model_validate_json(raw), actual, UUID(actual[:32])
