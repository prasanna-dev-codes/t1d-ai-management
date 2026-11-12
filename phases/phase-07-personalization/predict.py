"""Run an offline Phase 07 forecast using recorded history through the latest CGM reading."""

import argparse
import hashlib
import json
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
from adaptation import WARMUP, ForecastQuery, replay
from artifact import InferenceArtifact
from t1d_forecasting.analogue_models import predict_frozen
from t1d_forecasting.analogues import add_analogue_features
from t1d_forecasting.datasets import SourceData, read_azt1d, read_ohio, read_physiocgm
from t1d_forecasting.history_model import factor_masks
from t1d_forecasting.offline_inference import analogue_snapshot, forecast_payload
from t1d_forecasting.windows import make_windows
from uom import read_official_uom


def predict(
    sources: tuple[SourceData, ...],
    dataset: str,
    participant: str,
    history_directory: Path,
    analogue_directory: Path,
    profile_path: Path,
) -> dict[str, Any]:
    values, lineage, cutoff, _ = analogue_snapshot(sources, dataset, participant)
    scope = (dataset, participant)
    scoped = tuple(
        replace(
            source,
            events=tuple(
                row
                for row in source.events
                if row.scope == scope and row.partition != "testing" and row.time <= cutoff
            ),
        )
        for source in sources
    )
    history, _ = make_windows(scoped, include_history=True, allow_event_time_replay=True)
    last_by_partition: dict[str, datetime] = {}
    for row in history:
        previous = last_by_partition.get(row.partition)
        if previous is not None and row.cutoff <= previous:
            raise ValueError("Unresolved source-order change in adaptation history")
        last_by_partition[row.partition] = row.cutoff
    feedback = sorted(
        (
            row
            for row in add_analogue_features(history)
            if row.label_available_at is not None
            and max(row.label_end, row.label_available_at) <= cutoff
        ),
        key=lambda row: row.cutoff,
    )
    feature_rows = [row.features for row in feedback] + [values]
    matrix = np.asarray(feature_rows, dtype=np.float32)
    last = np.asarray([[features[11] * 100] for features in feature_rows])
    baseline, report, hashes = predict_frozen(matrix, last, history_directory, analogue_directory)
    artifact, profile_hash = InferenceArtifact.read(profile_path)
    artifact.verify_models(hashes, report["selected_by_horizon"])
    warm_until = (history[0].cutoff if history else cutoff) + WARMUP
    result = replay(
        feedback,
        baseline,
        warm_until,
        [True] * len(feedback),
        estimate_recent_error=True,
        query=ForecastQuery(f"{dataset}:{participant}", cutoff, values),
    )
    warm = cutoff >= warm_until
    profiles = artifact.point_profiles if warm else ("frozen-v5",) * 4
    points = np.asarray([[result.predictions[method][-1, j] for j, method in enumerate(profiles)]])
    radii = (
        artifact.intervals().radii(result.recent_error[-1:])
        if warm
        else np.asarray([report["calibration_radii"]], dtype=float)
    )
    digest = hashlib.sha256()
    for row in feedback:
        digest.update(repr((row.input_ref, row.label_available_at, row.targets)).encode())
    return forecast_payload(points, radii) | {
        "lineage": lineage | {"feedback_sha256": digest.hexdigest()},
        "base_model_sha256": hashes,
        "personalization_sha256": profile_hash,
        "profile_by_horizon": profiles,
        "availability": "unverified-event-time-replay",
        "history_track": "warm" if warm else "cold",
        "eligible_feedback_windows": len(feedback),
        "recent_feedback_supported": bool(result.rolling_support[-1]),
        "context_feedback_supported": bool(result.context_support[-1]),
        "observed_factor_flags": {
            key: bool(mask[0]) for key, mask in factor_masks(matrix[-1:]).items()
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", choices=("ohio", "azt1d", "physiocgm", "uom"), required=True)
    parser.add_argument("--participant", required=True)
    for name in ("source", "history", "analogues", "profile", "output"):
        parser.add_argument(f"--{name}", required=True, type=Path)
    parser.add_argument("--context-availability", choices=("event-time-replay",), required=True)
    args = parser.parse_args()
    if args.output.resolve().is_relative_to(Path(__file__).resolve().parents[2]):
        parser.error("Research outputs must remain outside Git")
    if args.dataset == "ohio":
        sources = read_ohio(args.source, extended_context=True)
    elif args.dataset == "azt1d":
        sources = read_azt1d(args.source)
    elif args.dataset == "uom":
        sources, _ = read_official_uom(args.source)
    else:
        sources = (read_physiocgm(args.source),)
    result = predict(
        sources, args.dataset, args.participant, args.history, args.analogues, args.profile
    )
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(result, output, indent=2, allow_nan=False)
        output.write("\n")
    print("Phase 07 offline forecast", result["status"])


if __name__ == "__main__":
    main()
