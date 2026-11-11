"""Local research forecast from source history; no future labels or live API bypass."""

import argparse
import json
from pathlib import Path

from t1d_forecasting.datasets import read_azt1d, read_ohio, read_physiocgm
from t1d_forecasting.offline_inference import forecast, forecast_history

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", choices=["ohio", "physiocgm", "azt1d"], required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--participant", required=True)
    parser.add_argument("--models", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--uncertainty", type=Path)
    mode.add_argument("--history", type=Path, help="Directory for one history benchmark run")
    parser.add_argument(
        "--interval-method",
        choices=["balanced-per-forecast-v2", "scaled-per-forecast-v2"],
    )
    parser.add_argument(
        "--context-availability", required=True, choices=["verified-only", "event-time-replay"]
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.resolve().is_relative_to(Path(__file__).resolve().parents[1]):
        parser.error("Research predictions must remain outside Git")
    if args.history:
        if args.interval_method or args.context_availability != "event-time-replay":
            parser.error("History models require event-time replay and their own interval artifact")
    elif not args.interval_method:
        parser.error("The v1 model requires --interval-method")
    source = (
        read_ohio(args.source, extended_context=args.history is not None)
        if args.dataset == "ohio"
        else read_azt1d(args.source)
        if args.dataset == "azt1d"
        else (read_physiocgm(args.source),)
    )
    result = (
        forecast_history(source, args.dataset, args.participant, args.models, args.history)
        if args.history
        else forecast(
            source,
            args.dataset,
            args.participant,
            args.models,
            args.uncertainty,
            args.interval_method,
            args.context_availability == "event-time-replay",
        )
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    print("Offline research result saved:", result["status"])
