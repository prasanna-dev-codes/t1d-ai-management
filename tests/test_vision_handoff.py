"""Safe cloud artifact handoff integrity; no remote execution or real model files."""

import json
import runpy
from pathlib import Path

import pytest
from t1d_vision.handoff import REQUIRED, inventory, verify_inventory


@pytest.fixture
def bundle(tmp_path: Path) -> Path:
    for name in REQUIRED:
        (tmp_path / name).write_bytes(b"authored-software-fixture-only")
    return tmp_path


def test_bundle_checks_integrity_without_deserializing(bundle: Path) -> None:
    result = inventory(bundle)
    (bundle / "bundle-index.json").write_text(json.dumps(result))
    assert verify_inventory(bundle) == result
    (bundle / "model.onnx").write_bytes(b"modified")
    with pytest.raises(ValueError, match="mismatch"):
        verify_inventory(bundle)


@pytest.mark.parametrize("name", [".env", "image.png", "unapproved.json", "credentials.json"])
def test_bundle_rejects_unknown_files(bundle: Path, name: str) -> None:
    (bundle / name).write_text("synthetic-placeholder")
    with pytest.raises(ValueError, match="allowlisted"):
        inventory(bundle)


def test_cloud_probe_never_claims_training_approval() -> None:
    probe = runpy.run_path("scripts/vision_cloud_preflight.py")["report"]()
    assert probe["training_authorized"] is False and probe["gpu_verified"] is False
    assert not {"environment_variables", "hostname", "account", "serial_number"} & probe.keys()


def test_handoff_rejects_uninventoried_directories(bundle: Path) -> None:
    (bundle / "private").mkdir()
    with pytest.raises(ValueError, match="Flat export"):
        inventory(bundle)
