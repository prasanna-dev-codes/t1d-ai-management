"""Train/calibrate on disjoint fictional patients and evaluate held-out patients."""

import argparse
import hashlib
import json
from pathlib import Path

from t1d_forecasting.experiment import experiment

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--write-bundle",
        action="store_true",
        help="Regenerate the explicitly synthetic package artifact and manifest",
    )
    args = parser.parse_args()
    bundle, report = experiment()
    raw = (bundle.model_dump_json(indent=2) + "\n").encode()
    report["artifact_sha256"] = hashlib.sha256(raw).hexdigest()
    if args.write_bundle:
        root = (
            Path(__file__).resolve().parents[1] / "phases/phase-06-forecasting/src/t1d_forecasting"
        )
        (root / "artifacts").mkdir(exist_ok=True)
        filename = "synthetic-" + str(report["artifact_sha256"]) + ".json"
        (root / "artifacts" / filename).write_bytes(raw)
        (root / "manifest.py").write_text(
            '"""Approved fictional artifact digest; regeneration requires review."""\n\n'
            + f'ARTIFACT_SHA256 = "{report["artifact_sha256"]}"\n'
            + f'ARTIFACT_FILENAME = (\n    "{filename}"\n)\n',
            encoding="utf-8",
        )
    output = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    print(output)
