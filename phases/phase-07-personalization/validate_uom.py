"""Evaluate fixed Phase 07 forecasts on an independent T1D-UOM cohort."""

import argparse
import json
from pathlib import Path

import numpy as np
from adaptation import LAG_METHOD
from artifact import InferenceArtifact
from evaluate import _score, _selected, patient_tracks
from t1d_forecasting.analogue_models import predict_frozen
from t1d_forecasting.analogues import add_analogue_features
from t1d_forecasting.history_model import factor_masks
from t1d_forecasting.uncertainty import interval_metrics
from t1d_forecasting.windows import HISTORY_FEATURE_NAMES, make_windows
from uom import ARCHIVE_SHA256, read_official_uom


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "history", "analogues", "profile", "output"):
        parser.add_argument(f"--{name}", required=True, type=Path)
    parser.add_argument("--context-availability", choices=("event-time-replay",), required=True)
    args = parser.parse_args()
    if args.output.resolve().is_relative_to(Path(__file__).resolve().parents[2]):
        parser.error("Research outputs must remain outside Git")
    artifact, profile_hash = InferenceArtifact.read(args.profile)
    reference = list(artifact.point_profiles)
    timing = [LAG_METHOD if method == "context-offset" else method for method in reference]
    source, source_counts = read_official_uom(args.source)
    raw, window_counts = make_windows(source, include_history=True, allow_event_time_replay=True)
    windows = add_analogue_features(raw)
    print("T1D-UOM eligible windows:", len(windows), flush=True)
    if not windows:
        raise ValueError("No eligible five-minute T1D-UOM windows")
    features = np.asarray([row.features for row in windows], dtype=np.float32)
    last = np.asarray([[row.features[11] * 100] for row in windows])
    baseline, manifest, hashes = predict_frozen(features, last, args.history, args.analogues)
    artifact.verify_models(hashes, manifest["selected_by_horizon"])
    warm, cold = patient_tracks(windows, baseline, personal_intervals=True, recorded_timing=True)
    personalized = _selected(warm, reference)
    timing_points = _selected(warm, timing)
    warm_features = np.asarray([row.features for row in warm.rows])
    flags = factor_masks(warm_features)
    bolus = warm_features[:, HISTORY_FEATURE_NAMES.index("recorded_bolus_240_present")] == 1
    subgroups = {}
    for name, mask in (
        ("recent_carbs", flags["carbs"]),
        ("recent_bolus", bolus),
        ("carbs_and_bolus", flags["carbs"] & bolus),
    ):
        rows = [row for row, keep in zip(warm.rows, mask, strict=True) if keep]
        if len({row.scope for row in rows}) >= 3:
            subgroups[name] = {
                "phase07": _score(rows, personalized[mask]),
                "recorded_timing": _score(rows, timing_points[mask]),
            }
    local = artifact.intervals()
    report = {
        "cohort": "T1D-UOM v1.0.4",
        "archive_sha256": ARCHIVE_SHA256,
        "context_policy": "event-time-replay",
        "source_counts": source_counts,
        "window_counts": window_counts,
        "participants_with_eligible_windows": len({row.scope for row in windows}),
        "phase07_profiles": reference,
        "recorded_timing_profiles": timing,
        "baseline_model_sha256": hashes,
        "phase07_artifact_sha256": profile_hash,
        "cold": _score(cold.rows, cold.points("frozen-v5")),
        "cold_intervals": interval_metrics(
            cold.rows, cold.points("frozen-v5"), manifest["calibration_radii"]
        ),
        "warm": {
            "phase06": _score(warm.rows, warm.points("frozen-v5")),
            "phase07": _score(warm.rows, personalized),
            "recorded_timing": _score(warm.rows, timing_points),
        },
        "warm_intervals": {
            "phase07_constant": interval_metrics(warm.rows, personalized, local.constant),
            "phase07_personal": interval_metrics(
                warm.rows, personalized, local.radii(warm.recent_error)
            ),
        },
        "warm_subgroups": subgroups,
    }
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(report, output, indent=2, allow_nan=False)
        output.write("\n")
    print("Independent cohort report written", flush=True)


if __name__ == "__main__":
    main()
