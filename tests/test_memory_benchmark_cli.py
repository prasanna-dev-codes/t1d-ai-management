"""Actual evaluation CLI round trip and invalid-input rejection."""

import json
import subprocess
import sys
from pathlib import Path


def test_memory_benchmark_export_and_replay(tmp_path: Path) -> None:
    template, schema = tmp_path / "template.json", tmp_path / "schema.json"
    report, replay = tmp_path / "report.json", tmp_path / "replay.json"
    subprocess.run(
        [
            sys.executable,
            "scripts/evaluate_memory.py",
            "--export-template",
            str(template),
            "--export-schema",
            str(schema),
            "--output",
            str(report),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [
            sys.executable,
            "scripts/evaluate_memory.py",
            "--judged-input",
            str(template),
            "--output",
            str(replay),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(report.read_text())["patient_clustered_evaluation"] == json.loads(
        replay.read_text()
    )
    assert "JudgedQuery" in json.loads(schema.read_text())["$defs"]
    data = json.loads(template.read_text())
    data["queries"][0]["judgments"] = {}
    template.write_text(json.dumps(data), encoding="utf-8")
    failed = subprocess.run(
        [
            sys.executable,
            "scripts/evaluate_memory.py",
            "--judged-input",
            str(template),
        ],
        capture_output=True,
        text=True,
    )
    assert failed.returncode == 2
    assert "Invalid evaluation input" in failed.stderr
    assert "Traceback" not in failed.stderr
