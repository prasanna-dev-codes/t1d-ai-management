"""Local research forecast from source history; no future labels or live API bypass."""

import argparse
import json
from pathlib import Path

from t1d_forecasting.datasets import read_azt1d, read_ohio, read_physiocgm
from t1d_forecasting.offline_inference import forecast

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", choices=["ohio", "physiocgm", "azt1d"], required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--participant", required=True)
    parser.add_argument("--models", type=Path, required=True)
    parser.add_argument("--uncertainty", type=Path, required=True)
    parser.add_argument(
        "--interval-method",
        required=True,
        choices=["balanced-per-forecast-v2", "scaled-per-forecast-v2"],
    )
    parser.add_argument(
        "--context-availability", required=True, choices=["verified-only", "event-time-replay"]
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.resolve().is_relative_to(Path(__file__).resolve().parents[1]):
        parser.error("Research predictions must remain outside Git")
    source = (
        read_ohio(args.source)
        if args.dataset == "ohio"
        else read_azt1d(args.source)
        if args.dataset == "azt1d"
        else (read_physiocgm(args.source),)
    )
    result = forecast(
        source,
        args.dataset,
        args.participant,
        args.models,
        args.uncertainty,
        args.interval_method,
        args.context_availability == "event-time-replay",
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    print("Offline research result saved:", result["status"])
