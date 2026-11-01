"""Cross-layer drift and serialization compatibility checks."""

import json
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient
from pydantic import BaseModel
from t1d_api.app import create_app
from t1d_api.contracts import LivenessResponse, ReadinessResponse

ROOT = Path(__file__).resolve().parents[1]


def test_generated_contracts_are_current() -> None:
    subprocess.run([sys.executable, "scripts/export_contracts.py", "--check"], cwd=ROOT, check=True)


def test_served_health_uses_exported_schemas() -> None:
    schema = json.loads((ROOT / "packages/shared-contracts/schema.json").read_text())["$defs"]
    with TestClient(create_app()) as client:
        cases: list[tuple[str, type[BaseModel]]] = [
            ("live", LivenessResponse),
            ("ready", ReadinessResponse),
        ]
        for path, model in cases:
            result = client.get(f"/api/v1/health/{path}")
            assert result.status_code == 200
            assert schema[model.__name__] == model.model_json_schema(mode="serialization")
            assert (
                result.json()["status"] == schema[model.__name__]["properties"]["status"]["const"]
            )
