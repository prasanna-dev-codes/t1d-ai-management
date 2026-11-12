"""Compare Phase 06 15-minute models on held-out and native-cadence CGM."""

import argparse
import json
import time
from pathlib import Path
from typing import Any

import numpy as np
from t1d_forecasting.cadence import CGM_COLUMNS, HISTORY_READINGS, HORIZONS, make_cadence_windows
from t1d_forecasting.datasets import read_azt1d, read_ohio, read_physiocgm
from t1d_forecasting.research_metrics import weights
from t1d_forecasting.uncertainty import balanced_quantiles, interval_metrics
from t1d_forecasting.windows import Window, patient_partitions
from uom import ARCHIVE_SHA256, read_official_uom


def arrays(rows: list[Window]) -> tuple[Any, Any, Any]:
    features = np.asarray([w.features for w in rows], dtype=np.float32)
    last = features[:, HISTORY_READINGS - 1 : HISTORY_READINGS] * 100
    return features, last, np.asarray([w.targets for w in rows])


def scores(rows: list[Window], points: Any) -> list[float]:
    target = np.asarray([w.targets for w in rows])
    errors = np.average(np.abs(points - target), axis=0, weights=weights(rows))
    return [float(value) for value in errors]


def native_cross_validation(rows: list[Window]) -> dict[str, Any]:
    """Explore native-cadence training with each participant excluded from their own fit."""
    from sklearn.linear_model import Ridge

    features, last, target = arrays(rows)
    scopes = np.asarray([row.scope for row in rows])
    participants = sorted(set(scopes))
    if len(participants) < 3:
        raise ValueError("Native-cadence cross-validation requires three or more participants")
    forecast = np.repeat(last, 4, axis=1)
    for scope in participants:
        held_out = scopes == scope
        train = [row for row, test in zip(rows, held_out, strict=True) if not test]
        model = Ridge(alpha=10.0).fit(
            features[~held_out], (target - last)[~held_out], sample_weight=weights(train)
        )
        points = last[held_out] + model.predict(features[held_out])
        forecast[held_out] = np.where(points > 0, points, last[held_out])
    baseline = np.repeat(last, 4, axis=1)
    paired = np.abs(forecast - target) - np.abs(baseline - target)
    differences = np.asarray([paired[scopes == scope].mean(axis=0) for scope in participants])
    rng = np.random.default_rng(20261112)
    resampled = rng.integers(len(participants), size=(1000, len(participants)))
    intervals = np.quantile(differences[resampled].mean(axis=1), (0.025, 0.975), axis=0)
    return {
        "protocol": "exploratory native-trained leave-one-participant-out",
        "ridge_context_mae_mg_dl": scores(rows, forecast),
        "persistence_mae_mg_dl": scores(rows, baseline),
        "paired_mae_difference_mg_dl": differences.mean(axis=0).tolist(),
        "paired_participant_bootstrap_ci95": intervals.T.tolist(),
    }


def compare(splits: dict[str, list[Window]], native: list[Window]) -> dict[str, Any]:
    from sklearn.linear_model import Ridge
    from xgboost import XGBRegressor

    cohorts = {key: rows for key, rows in splits.items() if key != "fit"} | {"native": native}
    matrices = {key: arrays(rows) for key, rows in cohorts.items()}
    x, last, target = arrays(splits["fit"])
    y = target - last
    mass = weights(splits["fit"])
    started = time.perf_counter()
    ridge = Ridge(alpha=10.0).fit(x, y, sample_weight=mass)
    models = {}
    for name, columns in (("boost-cgm", CGM_COLUMNS), ("boost-context", x.shape[1])):
        models[name] = [
            XGBRegressor(
                n_estimators=250,
                max_depth=4,
                learning_rate=0.05,
                objective="reg:pseudohubererror",
                huber_slope=20.0,
                tree_method="hist",
                n_jobs=2,
                random_state=20261112,
            ).fit(x[:, :columns], y[:, j], sample_weight=mass)
            for j in range(4)
        ]
    fitting_seconds = time.perf_counter() - started
    all_points = {}
    for key, (features, previous, _) in matrices.items():
        points = {
            "persistence": np.repeat(previous, 4, axis=1),
            "ridge-context": previous + ridge.predict(features),
            "boost-cgm": previous
            + np.column_stack([m.predict(features[:, :CGM_COLUMNS]) for m in models["boost-cgm"]]),
            "boost-context": previous
            + np.column_stack([m.predict(features) for m in models["boost-context"]]),
        }
        all_points[key] = {
            name: np.where(values > 0, values, points["persistence"])
            for name, values in points.items()
        }
    validation = {
        method: scores(cohorts["validation"], points)
        for method, points in all_points["validation"].items()
    }
    selected = [min(validation, key=lambda method: validation[method][j]) for j in range(4)]
    for points in all_points.values():
        points["selected"] = np.column_stack(
            [points[method][:, j] for j, method in enumerate(selected)]
        )
    calibration = cohorts["calibration"]
    radii = {
        name: balanced_quantiles(calibration, np.abs(points - matrices["calibration"][2]))
        for name, points in all_points["calibration"].items()
        if name in {"persistence", "selected"}
    }
    return {
        "fitting_seconds": fitting_seconds,
        "selected_by_horizon": selected,
        "split_sizes": {
            key: {"windows": len(rows), "participants": len({w.scope for w in rows})}
            for key, rows in (splits | {"native": native}).items()
        },
        "mae_mg_dl": {
            key: {name: scores(cohorts[key], points) for name, points in all_points[key].items()}
            for key in ("validation", "test", "native")
        },
        "intervals": {
            key: {
                name: interval_metrics(cohorts[key], all_points[key][name], radius)
                for name, radius in radii.items()
            }
            for key in ("test", "native")
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("ohio", "azt", "physio", "uom", "output"):
        parser.add_argument(f"--{name}", required=True, type=Path)
    args = parser.parse_args()
    if args.output.resolve().is_relative_to(Path(__file__).resolve().parents[2]):
        parser.error("Research outputs must remain outside Git")
    training = (
        read_ohio(args.ohio)
        + read_azt1d(args.azt)
        + tuple(read_physiocgm(path) for path in sorted(args.physio.glob("*.csv")))
    )
    if {e.dataset for source in training for e in source.events} != {"ohio", "azt1d", "physiocgm"}:
        parser.error("Training requires OhioT1DM, AZT1D, and PhysioCGM")
    independent, _ = read_official_uom(args.uom)
    decimated, decimated_counts = make_cadence_windows(training, native=False)
    native, native_counts = make_cadence_windows(independent, native=True)
    if not native:
        parser.error("No eligible native 15-minute CGM windows")
    splits = patient_partitions(decimated)
    print(f"Training on {len(splits['fit'])} windows. Native cohort has {len(native)}.", flush=True)
    report = compare(splits, native) | {
        "horizons_min": HORIZONS,
        "context_policy": "event-time-replay",
        "decimated_counts": decimated_counts,
        "native_counts": native_counts,
        "native_archive_sha256": ARCHIVE_SHA256,
        "native_exploratory_cross_validation": native_cross_validation(native),
    }
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(report, output, indent=2, allow_nan=False)
        output.write("\n")
    print("15-minute cadence report written", flush=True)


if __name__ == "__main__":
    main()
