"""Reproducible fictional cohort, patient-disjoint fit/calibration/test experiment."""

import math
import statistics
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from t1d_forecasting.contracts import (
    HORIZONS,
    ForecastModel,
    HorizonModel,
    ModelBundle,
    Reading,
)
from t1d_forecasting.engine import digest, point_value, snapshot


@dataclass(frozen=True)
class Example:
    patient: UUID
    cutoff: datetime
    readings: tuple[Reading, ...]
    targets: tuple[float, ...]


def signal(patient: int, minutes: float) -> float:
    # Authored oscillations, not a simulator of human physiology.
    phase = patient * 0.37
    return (
        145
        + patient % 7 * 2
        + 22 * math.sin(minutes / 130 + phase)
        + 8 * math.cos(minutes / 42 + phase)
        + 2 * math.sin(minutes / 7 + phase)
    )


def examples(patients: range, windows: int = 16) -> list[Example]:
    output = []
    for patient in patients:
        start = datetime(2020, 1, 1, tzinfo=UTC) + timedelta(days=patient * 5)
        for window in range(windows):
            last = 60 + window * 180
            age = window % 5 + 1 / 6
            readings = tuple(
                Reading(
                    id=UUID(int=patient * 1000000 + window * 100 + i),
                    event_time=start + timedelta(minutes=last - (11 - i) * 5),
                    available_at=start + timedelta(minutes=last - (11 - i) * 5, seconds=1),
                    value=signal(patient, last - (11 - i) * 5),
                    unit="mg/dL",
                    quality="accepted",
                    valid_sensor=True,
                )
                for i in range(12)
            )
            output.append(
                Example(
                    UUID(int=patient),
                    start + timedelta(minutes=last + age),
                    readings,
                    tuple(signal(patient, last + age + h) for h in HORIZONS),
                )
            )
    return output


def ridge(features: list[tuple[float, ...]], targets: list[float]) -> tuple[float, ...]:
    """Small fixed-dimensional ridge solve with partial-pivot elimination."""
    width = 6
    matrix = [
        [sum(row[i] * row[j] for row in features) + (0.1 if i == j else 0.0) for j in range(width)]
        + [sum(row[i] * y for row, y in zip(features, targets, strict=True))]
        for i in range(width)
    ]
    for column in range(width):
        pivot = max(range(column, width), key=lambda i: abs(matrix[i][column]))
        matrix[column], matrix[pivot] = matrix[pivot], matrix[column]
        divisor = matrix[column][column]
        if abs(divisor) < 1e-12:
            raise ValueError("Singular fit")
        matrix[column] = [x / divisor for x in matrix[column]]
        for i in range(width):
            if i != column:
                factor = matrix[i][column]
                matrix[i] = [a - factor * b for a, b in zip(matrix[i], matrix[column], strict=True)]
    return tuple(matrix[i][-1] for i in range(width))


def split_check(train: list[Example], calibration: list[Example], test: list[Example]) -> None:
    scopes = [{e.patient for e in part} for part in (train, calibration, test)]
    if any(scopes[i] & scopes[j] for i in range(3) for j in range(i + 1, 3)):
        raise ValueError("Patient overlap between partitions")
    if not (
        max(e.cutoff + timedelta(minutes=120) for e in train) < min(e.cutoff for e in calibration)
        and max(e.cutoff + timedelta(minutes=120) for e in calibration)
        < min(e.cutoff for e in test)
    ):
        raise ValueError("Overlapping label windows between chronological partitions")


def experiment() -> tuple[ModelBundle, dict[str, object]]:
    train, calibration, test = (
        examples(range(1, 21)),
        examples(range(21, 31)),
        examples(range(31, 41)),
    )
    split_check(train, calibration, test)
    train_features = [snapshot(list(e.readings), e.cutoff).features for e in train]
    calibration_features = [snapshot(list(e.readings), e.cutoff).features for e in calibration]
    test_features = [snapshot(list(e.readings), e.cutoff).features for e in test]
    fitted = tuple(
        HorizonModel(
            horizon=h, weights=ridge(train_features, [e.targets[i] for e in train]), radius=0
        )
        for i, h in enumerate(HORIZONS)
    )
    models = []
    report: dict[str, object] = {
        "data": "authored-oscillations-v1-not-human-physiology",
        "split": {
            "train_patients": 20,
            "calibration_patients": 10,
            "test_patients": 10,
            "windows_per_patient": 16,
            "patient_overlap": 0,
            "label_window_overlap": 0,
        },
        "limitations": [
            "No real patient validation",
            "Fixed ridge penalty, no test-set tuning",
            "Calibration uses per-patient maximum absolute residual across windows",
            "Nominal 90% intervals are not patient-specific clinical guarantees",
            "No meal/insulin/activity covariates or retrieval benefit established",
        ],
    }
    measures = {}
    for profile in ("persistence-v1", "linear-v1", "ridge-v1"):
        base = ForecastModel(profile=profile, horizons=fitted)
        calibrated = []
        horizon_results = {}
        for i, h in enumerate(HORIZONS):
            maxima: dict[UUID, float] = {}
            for e, features in zip(calibration, calibration_features, strict=True):
                residual = abs(point_value(features, base, h) - e.targets[i])
                maxima[e.patient] = max(maxima.get(e.patient, 0.0), residual)
            # ceil((n+1)*.9)-th order statistic, no test outcomes used.
            index = math.ceil((len(maxima) + 1) * 0.9) - 1
            if index >= len(maxima):
                raise ValueError("Insufficient independent calibration patients")
            radius = sorted(maxima.values())[index]
            calibrated.append(base.horizons[i].model_copy(update={"radius": radius}))
            errors = [
                point_value(f, base, h) - e.targets[i]
                for e, f in zip(test, test_features, strict=True)
            ]
            by_patient = []
            for patient in sorted({e.patient for e in test}):
                values = [
                    abs(error) <= radius
                    for e, error in zip(test, errors, strict=True)
                    if e.patient == patient
                ]
                by_patient.append(all(values))
            horizon_results[str(h)] = {
                "mae_mg_dl": statistics.mean(abs(x) for x in errors),
                "rmse_mg_dl": math.sqrt(statistics.mean(x * x for x in errors)),
                "bias_mg_dl": statistics.mean(errors),
                "window_coverage": statistics.mean(abs(x) <= radius for x in errors),
                "whole_patient_coverage": statistics.mean(by_patient),
                "interval_width_mg_dl": 2 * radius,
                "prespecified_subgroups": {
                    label: {
                        "windows": len(selected),
                        "mae_mg_dl": statistics.mean(abs(x) for x in selected)
                        if selected
                        else None,
                        "coverage": statistics.mean(abs(x) <= radius for x in selected)
                        if selected
                        else None,
                    }
                    for label, selected in (
                        (
                            "nonnegative_observed_trend",
                            [
                                error
                                for error, f in zip(errors, test_features, strict=True)
                                if f[3] >= 0
                            ],
                        ),
                        (
                            "negative_observed_trend",
                            [
                                error
                                for error, f in zip(errors, test_features, strict=True)
                                if f[3] < 0
                            ],
                        ),
                    )
                },
            }
        models.append(ForecastModel(profile=base.profile, horizons=tuple(calibrated)))
        measures[profile] = horizon_results
    manifest = digest(
        {
            "train": [(str(e.patient), e.cutoff.isoformat(), e.targets) for e in train],
            "calibration": [(str(e.patient), e.cutoff.isoformat(), e.targets) for e in calibration],
            "ridge_penalty": 0.1,
            "generator": "authored-oscillations-v1",
        }
    )
    bundle = ModelBundle(
        training_manifest_sha256=manifest, calibration_patients=10, models=tuple(models)
    )
    report["profiles"] = measures
    report["training_manifest_sha256"] = manifest
    return bundle, report
