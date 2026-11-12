"""Run the first Phase 07 offline benchmark against frozen Phase 06 artifacts."""

import argparse
import hashlib
import json
import time
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
from adaptation import METHODS, WARMUP, replay
from artifact import write_artifact
from meal_memory import METHOD as MEAL_MEMORY
from meal_memory import MealAnchor, meal_anchors
from personal_intervals import calibrate as calibrate_personal
from t1d_forecasting.analogue_models import predict_frozen
from t1d_forecasting.analogues import add_analogue_features
from t1d_forecasting.datasets import SourceData, read_azt1d, read_ohio, read_physiocgm
from t1d_forecasting.history_model import factor_masks
from t1d_forecasting.research_metrics import weights
from t1d_forecasting.uncertainty import balanced_quantiles, interval_metrics
from t1d_forecasting.windows import Window, make_windows, patient_partitions

MEAL_ROUTED = "meal-memory-routed"


@dataclass
class Evaluation:
    rows: list[Window] = field(default_factory=list)
    predictions: dict[str, list[Any]] = field(
        default_factory=lambda: {method: [] for method in METHODS}
    )
    rolling_support: list[bool] = field(default_factory=list)
    context_support: list[bool] = field(default_factory=list)
    early_warm: list[bool] = field(default_factory=list)
    meal_support: list[bool] = field(default_factory=list)
    recent_error: list[Any] = field(default_factory=list)

    def points(self, method: str) -> Any:
        return np.asarray(self.predictions[method], dtype=float)


def development_scopes(rows: list[Window]) -> set[str]:
    """Reserve some v5 calibration participants for method selection, by dataset."""
    by_dataset: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        by_dataset[row.dataset].add(row.scope)
    selected = set()
    for scopes in by_dataset.values():
        if len(scopes) < 2:
            raise ValueError("Separate development and interval-calibration participants required")
        ordered = sorted(
            scopes, key=lambda scope: hashlib.sha256(("phase07-v1:" + scope).encode()).digest()
        )
        selected.update(ordered[: len(scopes) // 2])
    return selected


def patient_tracks(
    rows: list[Window],
    baseline: Any,
    meals: dict[str, MealAnchor] | None = None,
    *,
    personal_intervals: bool = False,
    recorded_timing: bool = False,
    contextual_meals: bool = False,
    feedback_routing: tuple[str, ...] | None = None,
) -> tuple[Evaluation, Evaluation]:
    warm, cold = Evaluation(), Evaluation()
    grouped: dict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(rows):
        grouped[row.scope].append(index)
    for positions in grouped.values():
        last_by_partition: dict[str, datetime] = {}
        for index in positions:
            row = rows[index]
            previous = last_by_partition.get(row.partition)
            if previous is not None and row.cutoff <= previous:
                raise ValueError("Unresolved source-order change in adaptation history")
            last_by_partition[row.partition] = row.cutoff
        positions.sort(key=lambda index: rows[index].cutoff)
        patient = [rows[index] for index in positions]
        feedback = [row.partition != "testing" for row in patient]
        history = [row for row, allowed in zip(patient, feedback, strict=True) if allowed]
        if not history:
            raise ValueError("No adaptation history for a held-out participant")
        warm_until = history[0].cutoff + WARMUP
        anchors = [row.input_ref for row in patient]
        result = replay(
            patient,
            baseline[positions],
            warm_until,
            feedback,
            [meals.get(key) for key in anchors] if meals is not None else None,
            estimate_recent_error=personal_intervals,
            recorded_timing=recorded_timing,
            contextual_meals=contextual_meals,
            feedback_routing=feedback_routing,
        )
        official_testing = any(not flag for flag in feedback)
        warm_start = next(
            (
                row.cutoff
                for row in patient
                if row.cutoff >= warm_until and (not official_testing or row.partition == "testing")
            ),
            None,
        )
        for index, row in enumerate(patient):
            if row.cutoff < warm_until and feedback[index]:
                track = cold
            elif (
                warm_start is not None
                and row.cutoff >= warm_start
                and (not official_testing or row.partition == "testing")
            ):
                track = warm
            else:
                continue
            track.rows.append(row)
            track.rolling_support.append(bool(result.rolling_support[index]))
            track.context_support.append(bool(result.context_support[index]))
            track.meal_support.append(bool(result.meal_support[index]))
            if personal_intervals:
                track.recent_error.append(result.recent_error[index])
            track.early_warm.append(
                track is warm
                and warm_start is not None
                and row.cutoff < warm_start + timedelta(days=7)
            )
            for method, predictions in result.predictions.items():
                track.predictions.setdefault(method, []).append(predictions[index])
    if not warm.rows or not cold.rows:
        raise ValueError("Empty warm or cold evaluation track")
    return warm, cold


def _score(rows: list[Window], points: Any) -> dict[str, Any]:
    errors = points - np.asarray([row.targets for row in rows])
    mass = weights(rows)
    return {
        "windows": len(rows),
        "participants": len({row.scope for row in rows}),
        "mae_mg_dl": np.average(np.abs(errors), axis=0, weights=mass).tolist(),
        "rmse_mg_dl": np.sqrt(np.average(errors**2, axis=0, weights=mass)).tolist(),
    }


def choose(scores: dict[str, dict[str, Any]]) -> list[str]:
    base = scores["frozen-v5"]["mae_mg_dl"]
    return [
        best if base[index] - scores[best]["mae_mg_dl"][index] >= 0.1 else "frozen-v5"
        for index, best in enumerate(
            min(METHODS, key=lambda method: scores[method]["mae_mg_dl"][horizon])
            for horizon in range(4)
        )
    ]


def _selected(track: Evaluation, methods: Sequence[str]) -> Any:
    return np.column_stack([track.points(method)[:, j] for j, method in enumerate(methods)])


def route_meal_memory(track: Evaluation, reference: list[str]) -> None:
    """Change a point forecast only when its meal-memory query has evidence."""
    supported = np.asarray(track.meal_support)[:, None]
    points = np.where(supported, track.points(MEAL_MEMORY), _selected(track, reference))
    track.predictions[MEAL_ROUTED] = list(points)


def _run(
    windows: list[Window],
    history: Path,
    analogues: Path,
    output: Path,
    external: str | None,
    meals: dict[str, MealAnchor] | None = None,
    *,
    personal_intervals: bool = False,
) -> None:
    name = "pooled" if external is None else f"external-{external}"
    parts = patient_partitions(windows, external)
    locked_scopes = development_scopes(parts["calibration"])
    roles = {
        "development": [row for row in parts["calibration"] if row.scope in locked_scopes],
        "calibration": [row for row in parts["calibration"] if row.scope not in locked_scopes],
        "test": parts["test"],
    }

    def tracks(role: str) -> tuple[Evaluation, Evaluation, dict[str, str], list[str]]:
        rows = roles[role]
        print(name, role, len(rows), flush=True)
        x = np.asarray([row.features for row in rows], dtype=np.float32)
        last = np.asarray([[row.features[11] * 100] for row in rows])
        points, manifest, artifacts = predict_frozen(x, last, history / name, analogues / name)
        if role == "test":
            np.testing.assert_allclose(
                _score(rows, points)["mae_mg_dl"],
                manifest["test"]["selected"]["balanced_mae"],
                atol=1e-6,
            )
        warm, cold = patient_tracks(rows, points, meals, personal_intervals=personal_intervals)
        return warm, cold, artifacts, manifest["selected_by_horizon"]

    dev, _, _, _ = tracks("development")
    development = {method: _score(dev.rows, dev.points(method)) for method in dev.predictions}
    reference = choose(development)
    selected = reference
    if meals is not None:
        route_meal_memory(dev, reference)
        development[MEAL_ROUTED] = _score(dev.rows, dev.points(MEAL_ROUTED))
        selected = [
            MEAL_ROUTED
            if development[method]["mae_mg_dl"][index]
            - development[MEAL_ROUTED]["mae_mg_dl"][index]
            >= 0.1
            else method
            for index, method in enumerate(reference)
        ]
    cal, _, _, _ = tracks("calibration")
    warm, cold, artifacts, frozen_profiles = tracks("test")
    if meals is not None:
        route_meal_memory(cal, reference)
        route_meal_memory(warm, reference)
    warm_points = _selected(warm, selected)
    cal_target = np.asarray([row.targets for row in cal.rows])
    cal_base = cal.points("frozen-v5")
    cal_selected = _selected(cal, selected)
    base_radius = balanced_quantiles(cal.rows, np.abs(cal_target - cal_base))
    selected_radius = balanced_quantiles(cal.rows, np.abs(cal_target - cal_selected))
    subgroups = {}
    factors = factor_masks(np.asarray([row.features for row in warm.rows]))
    for group, mask in (
        ("first_warm_week", np.asarray(warm.early_warm)),
        ("later_warm_history", ~np.asarray(warm.early_warm)),
        ("carbs_recorded", factors["carbs"]),
        ("exercise_after_bolus", factors["activity_after_insulin"]),
        ("insufficient_recent_feedback", ~np.asarray(warm.rolling_support)),
    ):
        rows = [row for row, included in zip(warm.rows, mask, strict=True) if included]
        if len({row.scope for row in rows}) >= 3:
            subgroups[group] = {
                "frozen-v5": _score(rows, warm.points("frozen-v5")[mask]),
                "selected": _score(rows, warm_points[mask]),
            }
    report = {
        "protocol": "chronological-forecast-residuals-v1",
        "external_dataset": external,
        "context_policy": "event-time-replay",
        "frozen_model_sha256": artifacts,
        "selected_by_horizon": selected,
        "development": development,
        "role_counts": {
            role: {"windows": len(track.rows), "participants": len({w.scope for w in track.rows})}
            for role, track in (("development", dev), ("calibration", cal), ("test", warm))
        },
        "cold_start_frozen": _score(cold.rows, cold.points("frozen-v5")),
        "warm_test": {method: _score(warm.rows, warm.points(method)) for method in warm.predictions}
        | {"selected": _score(warm.rows, warm_points)},
        "warm_support": {
            "rolling_windows": sum(warm.rolling_support),
            "context_windows": sum(warm.context_support),
        },
        "warm_subgroups": subgroups,
        "warm_intervals": {
            "frozen-v5": interval_metrics(warm.rows, warm.points("frozen-v5"), base_radius),
            "selected": interval_metrics(warm.rows, warm_points, selected_radius),
        },
    }
    if meals is not None:
        mask = np.asarray(warm.meal_support)
        matching = [row for row, eligible in zip(warm.rows, mask, strict=True) if eligible]
        report["meal_memory"] = {
            "profile": "recorded-carbs-relative-distance-v1",
            "reference_phase07_by_horizon": reference,
            "reference_phase07": _score(warm.rows, _selected(warm, reference)),
            "test_anchors_with_one_known_meal": sum(row.input_ref in meals for row in warm.rows),
            "test_anchors_with_matches": len(matching),
            "participants_with_matches": len({row.scope for row in matching}),
            "matched_comparison": {
                method: _score(matching, warm.points(method)[mask])
                for method in ("context-offset", MEAL_MEMORY)
            }
            if len({row.scope for row in matching}) >= 3
            else {},
        }
    if personal_intervals:
        reference_points = _selected(warm, reference)
        reference_error = np.abs(cal_target - _selected(cal, reference))
        reference_radii = balanced_quantiles(cal.rows, reference_error)
        local = calibrate_personal(cal.rows, reference_error, cal.recent_error, reference_radii)
        write_artifact(
            output / f"{name}-inference.json", reference, frozen_profiles, artifacts, local
        )
        report["personal_intervals"] = {
            "point_profiles": reference,
            "calibration_participants_with_history": local.calibration_participants,
            "test_windows_with_history": sum(warm.rolling_support),
            "constant_width": interval_metrics(warm.rows, reference_points, reference_radii),
            "personal_width": interval_metrics(
                warm.rows, reference_points, local.radii(warm.recent_error)
            ),
        }
    (output / f"{name}.json").write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    print(name, "completed", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("ohio", "azt", "physiocgm", "history", "analogues", "output"):
        parser.add_argument(f"--{name}", required=True, type=Path)
    parser.add_argument("--context-availability", choices=["event-time-replay"], required=True)
    parser.add_argument("--meal-memory", action="store_true")
    parser.add_argument("--personal-intervals", action="store_true")
    args = parser.parse_args()
    if args.output.resolve().is_relative_to(Path(__file__).resolve().parents[2]):
        parser.error("Research outputs must remain outside Git")
    args.output.mkdir(parents=True)
    started = time.perf_counter()
    loaders: tuple[tuple[str, Callable[[], tuple[SourceData, ...]]], ...] = (
        ("ohio", lambda: read_ohio(args.ohio, extended_context=True)),
        (
            "physiocgm",
            lambda: tuple(read_physiocgm(p) for p in sorted(args.physiocgm.glob("*.csv"))),
        ),
        ("azt1d", lambda: read_azt1d(args.azt)),
    )
    windows: list[Window] = []
    anchors: dict[str, MealAnchor] | None = {} if args.meal_memory else None
    for name, load in loaders:
        source = load()
        raw, _ = make_windows(source, include_history=True, allow_event_time_replay=True)
        if not raw:
            raise ValueError(f"No eligible windows for {name}")
        derived = add_analogue_features(raw)
        windows.extend(derived)
        if anchors is not None:
            events = [
                event for item in source for event in item.events if event.kind == "carbohydrate"
            ]
            anchors.update(meal_anchors(events, derived, allow_event_time_replay=True))
        del source
        print(name, len(raw), "eligible windows", flush=True)
    for external in (None, "ohio", "physiocgm", "azt1d"):
        _run(
            windows,
            args.history,
            args.analogues,
            args.output,
            external,
            anchors,
            personal_intervals=args.personal_intervals,
        )
    print(f"Completed in {time.perf_counter() - started:.1f}s", flush=True)


if __name__ == "__main__":
    main()
