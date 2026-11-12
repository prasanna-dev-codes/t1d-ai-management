"""Compare offline meal matching, correction routing, and interval calibration."""

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
from artifact import InferenceArtifact
from evaluate import Evaluation, _score, _selected, development_scopes, patient_tracks
from interval_research import scaled_radii, trend_groups, trend_scales
from meal_memory import CONTEXT_METHOD, METHOD, meal_anchors
from t1d_forecasting.analogue_models import predict_frozen
from t1d_forecasting.analogues import add_analogue_features
from t1d_forecasting.datasets import SourceData, read_azt1d, read_ohio, read_physiocgm
from t1d_forecasting.uncertainty import interval_metrics
from t1d_forecasting.windows import Window, make_windows, patient_partitions
from uom import ARCHIVE_SHA256, read_official_uom


def windows_for(sources: tuple[SourceData, ...]) -> list[Window]:
    rows, _ = make_windows(sources, include_history=True, allow_event_time_replay=True)
    return add_analogue_features(rows)


def compare(
    warm: Evaluation,
    reference: Any,
    radius: Any,
    scales: dict[str, Any],
) -> dict[str, Any]:
    mask = np.asarray(warm.meal_support)
    matched = [row for row, include in zip(warm.rows, mask, strict=True) if include]
    meal = {
        "matched_windows": len(matched),
        "matched_participants": len({row.scope for row in matched}),
        "scores": {
            "locked": _score(matched, reference[mask]),
            **{
                method: _score(matched, warm.points(method)[mask])
                for method in ("context-offset", METHOD, CONTEXT_METHOD)
            },
        }
        if len({row.scope for row in matched}) >= 3
        else {},
    }
    revised = scaled_radii(warm.rows, radius, scales)
    groups = trend_groups(warm.rows)
    intervals = {
        "personal": interval_metrics(warm.rows, reference, radius),
        "trend-scaled": interval_metrics(warm.rows, reference, revised),
    }
    by_trend = {}
    for group in ("falling", "quiet", "rising"):
        selected = groups == group
        rows = [row for row, keep in zip(warm.rows, selected, strict=True) if keep]
        if len({row.scope for row in rows}) >= 3:
            by_trend[group] = {
                "windows": len(rows),
                "participants": len({row.scope for row in rows}),
                "personal": interval_metrics(rows, reference[selected], radius[selected]),
                "trend-scaled": interval_metrics(rows, reference[selected], revised[selected]),
            }
    return {
        "meal_memory": meal,
        "correction_routing": {
            "locked": _score(warm.rows, reference),
            "feedback-routed": _score(warm.rows, warm.points("feedback-routed")),
            "changed_windows": np.any(reference != warm.points("feedback-routed"), axis=1)
            .sum()
            .item(),
        },
        "intervals": intervals,
        "intervals_by_trend": by_trend,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("ohio", "azt", "physio", "uom", "history", "analogues", "profile", "output"):
        parser.add_argument(f"--{name}", required=True, type=Path)
    args = parser.parse_args()
    if args.output.resolve().is_relative_to(Path(__file__).resolve().parents[2]):
        parser.error("Research outputs must remain outside Git")
    artifact, fingerprint = InferenceArtifact.read(args.profile)
    local = artifact.intervals()

    def prepare(
        sources: tuple[SourceData, ...], rows: list[Window], *, research: bool
    ) -> tuple[Evaluation, Any, Any]:
        print(f"Scoring {len(rows)} forecast windows", flush=True)
        features = np.asarray([row.features for row in rows], dtype=np.float32)
        last = np.asarray([[row.features[11] * 100] for row in rows])
        points, manifest, hashes = predict_frozen(features, last, args.history, args.analogues)
        artifact.verify_models(hashes, manifest["selected_by_horizon"])
        meals = None
        if research:
            scopes = {row.scope for row in rows}
            meals = meal_anchors(
                [
                    event
                    for source in sources
                    for event in source.events
                    if event.kind == "carbohydrate" and ":".join(event.scope) in scopes
                ],
                rows,
                allow_event_time_replay=True,
            )
        warm, _ = patient_tracks(
            rows,
            points,
            meals,
            personal_intervals=True,
            contextual_meals=research,
            feedback_routing=artifact.point_profiles if research else None,
        )
        return warm, _selected(warm, artifact.point_profiles), local.radii(warm.recent_error)

    original = (
        read_ohio(args.ohio, extended_context=True)
        + read_azt1d(args.azt)
        + tuple(read_physiocgm(path) for path in sorted(args.physio.glob("*.csv")))
    )
    partitions = patient_partitions(windows_for(original))
    development = development_scopes(partitions["calibration"])
    calibration = [row for row in partitions["calibration"] if row.scope not in development]
    warm_cal, cal_points, cal_radii = prepare(original, calibration, research=False)
    errors = np.abs(np.asarray([row.targets for row in warm_cal.rows]) - cal_points)
    scales = trend_scales(warm_cal.rows, errors, cal_radii)
    report = {
        "context_policy": "event-time-replay",
        "profile_sha256": fingerprint,
        "native_archive_sha256": ARCHIVE_SHA256,
        "calibration_participants": len({row.scope for row in warm_cal.rows}),
        "trend_scales": {group: scale.tolist() for group, scale in scales.items()},
        "pooled_test": compare(*prepare(original, partitions["test"], research=True), scales),
    }
    independent, _ = read_official_uom(args.uom)
    report["uom_five_minute"] = compare(
        *prepare(independent, windows_for(independent), research=True), scales
    )
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(report, output, indent=2, allow_nan=False)
        output.write("\n")
    print("Held-out comparisons written", flush=True)


if __name__ == "__main__":
    main()
