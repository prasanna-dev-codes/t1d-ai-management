"""Authored pixels and mathematical fixtures: software evidence, never food accuracy."""

import hashlib
import io
import math
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np
import onnx
import onnxruntime as ort
import pytest
from onnx import TensorProto, helper, numpy_helper
from PIL import Image
from t1d_vision.artifacts import ArtifactManifest, child_path, load_artifact
from t1d_vision.contracts import ClassLabel, VisionFault
from t1d_vision.datasets import (
    ImageRecord,
    SourceManifest,
    duplicate_groups,
    index_directory,
    split_records,
    validate_boxes,
    validate_mask,
    validate_split,
)
from t1d_vision.images import MAX_BYTES, decode, tensor
from t1d_vision.metrics import evaluate, probabilities, temperature_scale
from t1d_vision.runtime import ProcessBudget, VisionRuntime


def image_bytes(mode: str = "RGB", size: tuple[int, int] = (64, 32), format: str = "PNG") -> bytes:
    output = io.BytesIO()
    Image.new(mode, size).save(output, format=format)
    return output.getvalue()


@pytest.mark.parametrize("mode", ["RGB", "RGBA", "L", "LA", "P"])
def test_preprocess_modes(mode: str) -> None:
    result = decode(image_bytes(mode), "image/png")
    assert result.rgb.mode == "RGB" and result.rgb.info == {}
    output = tensor(result.rgb)
    assert (
        output.shape == (1, 3, 224, 224)
        and output.dtype == np.float32
        and np.isfinite(output).all()
    )
    assert output.flags.c_contiguous
    np.testing.assert_allclose(
        output[0, :, 112, 112],
        -np.array([0.485, 0.456, 0.406]) / np.array([0.229, 0.224, 0.225])
        if mode not in {"RGBA", "LA"}
        else (1 - np.array([0.485, 0.456, 0.406])) / np.array([0.229, 0.224, 0.225]),
        atol=1e-6,
    )


def test_exif_rotation_and_metadata_removal() -> None:
    image = Image.new("RGB", (64, 32))
    exif = Image.Exif()
    exif[274] = 6
    exif[270] = "synthetic-private-metadata"
    stream = io.BytesIO()
    image.save(stream, format="JPEG", exif=exif)
    result = decode(stream.getvalue(), "image/jpeg")
    assert result.rgb.size == (32, 64) and result.rgb.info == {} and not result.rgb.getexif()


@pytest.mark.parametrize(
    ("data", "mime", "code"),
    [
        (b"", "image/png", "INVALID_IMAGE"),
        (b"not-image", "image/png", "INVALID_IMAGE"),
        (image_bytes(), "image/jpeg", "IMAGE_FORMAT_MISMATCH"),
        (image_bytes(size=(16, 32)), "image/png", "IMAGE_DIMENSIONS"),
        (image_bytes(), "image/gif", "UNSUPPORTED_IMAGE_FORMAT"),
        (b"a" * (MAX_BYTES + 1), "image/png", "PAYLOAD_TOO_LARGE"),
    ],
)
def test_rejected_images(data: bytes, mime: str, code: str) -> None:
    with pytest.raises(VisionFault) as exc:
        decode(data, mime)
    assert exc.value.code == code and "not-image" not in str(exc.value)


def record(index: int, group: str | None = None, official: str | None = None) -> ImageRecord:
    digest = hashlib.sha256(str(index).encode()).hexdigest()
    return ImageRecord.model_validate(
        dict(
            record_id=digest,
            relative_path=f"food/{index}.png",
            canonical_id="food.fixture",
            source_group=group,
            file_sha256=digest,
            pixel_sha256=digest,
            perceptual_hash=hashlib.sha256(f"phash{index}".encode()).hexdigest()[:16],
            official_split=official,
        )
    )


def test_group_split_seals_test_and_excludes_duplicate_train() -> None:
    rows = [record(i, f"session{i}") for i in range(20)]
    rows[0] = rows[0].model_copy(update={"official_split": "test", "source_group": "shared"})
    rows[1] = rows[1].model_copy(update={"source_group": "shared"})
    plan = split_records(rows)
    assert (
        plan.assignments[rows[0].record_id] == "test"
        and rows[1].record_id in plan.excluded_training_ids
    )
    assert plan == split_records(list(reversed(rows)))
    broken = plan.model_copy(
        update={"assignments": {**plan.assignments, rows[1].record_id: "train"}}
    )
    with pytest.raises(ValueError, match="leakage"):
        validate_split(broken)


def test_duplicate_conflicting_labels_and_near_matches() -> None:
    a, b = record(1), record(2)
    b = b.model_copy(update={"pixel_sha256": a.pixel_sha256, "canonical_id": "food.other"})
    with pytest.raises(ValueError, match="label conflict"):
        duplicate_groups([a, b])
    b = record(2).model_copy(
        update={"perceptual_hash": f"{int(a.perceptual_hash, 16) ^ 0b10101:016x}"}
    )
    groups = duplicate_groups([a, b])
    assert groups[a.record_id] == groups[b.record_id]


def test_rights_gate_and_index_corruption(tmp_path: Path) -> None:
    blocked = SourceManifest(
        dataset_id="blocked",
        version="1",
        source_url="https://invalid.example",
        rights_reference="unverified",
    )
    with pytest.raises(ValueError, match="approval"):
        index_directory(tmp_path, blocked, "draft", {})
    source = blocked.model_copy(
        update={"engineering_only": True, "source_url": "authored-synthetic-software-fixture"}
    )
    folder = tmp_path / "fixture"
    folder.mkdir()
    (folder / "ok.png").write_bytes(image_bytes())
    (folder / "bad.png").write_bytes(b"invalid")
    indexed = index_directory(tmp_path, source, "draft", {"fixture": "food.fixture"})
    assert len(indexed.records) == 1
    assert {i.code for i in indexed.issues} == {"CORRUPT_IMAGE", "SOURCE_GROUP_MISSING"}
    with pytest.raises(ValueError):
        ImageRecord.model_validate(
            {**indexed.records[0].model_dump(), "relative_path": "../outside.png"}
        )


@pytest.mark.parametrize(
    "box", [[0, 0, 0, 2, 1], [2, 0, 0, 1, 1], [0, 0, 0, float("nan"), 1], [0.5, 0, 0, 1, 1]]
)
def test_annotation_bounds(box: list[float]) -> None:
    with pytest.raises(ValueError):
        validate_boxes([box], 2)


def test_masks_validate_ids_and_shape() -> None:
    validate_boxes([[0, 0, 0, 0.5, 0.5]], 2)
    validate_mask(np.zeros((4, 5), dtype=np.uint8), {0, 1}, (4, 5))
    with pytest.raises(ValueError):
        validate_mask(np.ones((4, 5), dtype=np.uint8) * 9, {0, 1}, (4, 5))
    with pytest.raises(ValueError):
        validate_mask(np.zeros((4, 5)), {0, 1}, (4, 5))


def test_metrics_against_hand_calculated_values() -> None:
    result = evaluate(np.array([[0.8, 0.2], [0.3, 0.7]]), np.array([0, 1]))
    assert result["top1"] == 1 and result["macro_f1"] == 1
    assert result["nll"] == pytest.approx(-math.log(0.8 * 0.7) / 2)
    assert result["brier"] == pytest.approx(0.13) and result["ece"] == pytest.approx(0.25)
    with pytest.raises(ValueError):
        evaluate(np.array([[float("nan"), 1]]), np.array([0]))
    with pytest.raises(ValueError):
        temperature_scale(np.ones((4, 2)), np.array([0, 1, 0, 1]), "test")
    logits = np.array([[4.0, 0.0], [0.0, 4.0], [4.0, 0.0], [0.0, 4.0]])
    temperature = temperature_scale(logits, np.array([0, 1, 1, 0]), "calibration")
    assert temperature > 1
    assert (
        evaluate(probabilities(logits, temperature), np.array([0, 1, 1, 0]))["nll"]
        < evaluate(probabilities(logits), np.array([0, 1, 1, 0]))["nll"]
    )


def engineering_artifact(root: Path) -> Path:
    import json

    weights = np.array([[1, 0], [0, 1], [0, 0]], dtype=np.float32)
    graph = helper.make_graph(
        [
            helper.make_node("ReduceMean", ["image"], ["pooled"], axes=[2, 3], keepdims=0),
            helper.make_node("MatMul", ["pooled", "weights"], ["logits"]),
        ],
        "authored-engineering-only",
        [helper.make_tensor_value_info("image", TensorProto.FLOAT, [1, 3, 224, 224])],
        [helper.make_tensor_value_info("logits", TensorProto.FLOAT, [1, 2])],
        [numpy_helper.from_array(weights, "weights")],
    )
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)], ir_version=10)
    onnx.save(model, root / "model.onnx")
    identity = uuid4()
    report = {
        "model_id": str(identity),
        "dataset_manifest_sha256": "a" * 64,
        "split_manifest_sha256": "b" * 64,
        "class_ids": ["food.fixture_a", "food.fixture_b"],
        "engineering_only": True,
        "test_samples": 0,
        "rights_approved": False,
    }
    (root / "evaluation.json").write_text(json.dumps(report))
    manifest = ArtifactManifest(
        model_id=identity,
        version="engineering-1",
        taxonomy_version="test",
        dataset_version="synthetic",
        dataset_manifest_sha256="a" * 64,
        split_manifest_sha256="b" * 64,
        preprocessing_version="rgb-letterbox224-v1",
        code_revision="abcdef1234",
        evaluation_state="engineering_only",
        evaluation_report="evaluation.json",
        evaluation_sha256=hashlib.sha256((root / "evaluation.json").read_bytes()).hexdigest(),
        onnx_file="model.onnx",
        onnx_sha256=hashlib.sha256((root / "model.onnx").read_bytes()).hexdigest(),
        classes=[
            ClassLabel(canonical_id="food.fixture_a", label="Synthetic A"),
            ClassLabel(canonical_id="food.fixture_b", label="Synthetic B"),
        ],
        temperature=1,
        calibrated=False,
        rights_reference="authored-software-fixture",
        approval_reference="software-tests-only",
        exported_at=datetime.now(UTC),
    )
    (root / "manifest.json").write_text(manifest.model_dump_json())
    return root


def test_native_onnx_engineering_parity_and_serving_refusal(tmp_path: Path) -> None:
    root = engineering_artifact(tmp_path)
    _, graph = load_artifact(root, serving=False)
    x = np.ones((1, 3, 224, 224), dtype=np.float32)
    x[:, 1] *= 2
    session = ort.InferenceSession(str(graph), providers=["CPUExecutionProvider"])
    np.testing.assert_allclose(session.run(None, {"image": x})[0], [[1, 2]], atol=1e-6)
    with pytest.raises(VisionFault, match="MODEL_UNAVAILABLE"):
        load_artifact(root)
    graph.write_bytes(graph.read_bytes() + b"changed")
    with pytest.raises(VisionFault):
        load_artifact(root, serving=False)


def test_artifact_escape_and_symlinks(tmp_path: Path) -> None:
    (tmp_path / "data").write_bytes(b"a")
    (tmp_path / "alias").symlink_to(tmp_path / "data")
    with pytest.raises(ValueError):
        child_path(tmp_path, "alias", 100)
    with pytest.raises(ValueError):
        child_path(tmp_path, "../escape", 100)


def fast_processor(data: bytes, mime: str, root: str, operation: str) -> dict[str, Any]:
    return {"safe": "ok"}


def slow_processor(data: bytes, mime: str, root: str, operation: str) -> dict[str, Any]:
    time.sleep(10)
    return {}


def test_process_budget_success_and_default_unavailability() -> None:
    budget = ProcessBudget(processor=fast_processor)
    assert budget.run(b"", "", "", "status") == {"safe": "ok"}
    assert not VisionRuntime().status().available
    with pytest.raises(VisionFault, match="MODEL_UNAVAILABLE"):
        VisionRuntime().analyze(b"a", "image/png", "single_label_classification")


def test_process_deadline_kills_work_and_releases_slot() -> None:
    budget = ProcessBudget(deadline_seconds=0.1, processor=slow_processor)
    start = time.monotonic()
    with pytest.raises(VisionFault, match="VISION_TIMEOUT"):
        budget.run(b"", "", "", "status")
    assert time.monotonic() - start < 3
    budget.processor = fast_processor
    budget.deadline_seconds = 5
    assert budget.run(b"", "", "", "status") == {"safe": "ok"}


def test_process_memory_guard_and_cancellation() -> None:
    with pytest.raises(VisionFault, match="VISION_MEMORY_LIMIT"):
        ProcessBudget(memory_bytes=32 * 1024**2, processor=slow_processor).run(
            b"", "", "", "status"
        )
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(VisionFault, match="VISION_CANCELLED"):
        ProcessBudget(processor=slow_processor).run(b"", "", "", "status", cancel)


def test_pixel_bomb_header_rejected_before_decode() -> None:
    import struct
    import zlib

    data = bytearray(image_bytes())
    data[16:24] = struct.pack(">II", 5000, 5000)
    data[29:33] = struct.pack(">I", zlib.crc32(data[12:29]))
    with pytest.raises(VisionFault, match="IMAGE_DIMENSIONS"):
        decode(bytes(data), "image/png")


def test_animated_png_rejected() -> None:
    output = io.BytesIO()
    Image.new("RGB", (32, 32)).save(
        output,
        format="PNG",
        save_all=True,
        append_images=[Image.new("RGB", (32, 32), "white")],
        duration=100,
        loop=0,
    )
    with pytest.raises(VisionFault, match="ANIMATED_IMAGE_UNSUPPORTED"):
        decode(output.getvalue(), "image/png")


def oversized_reply(data: bytes, mime: str, root: str, operation: str) -> dict[str, Any]:
    return {"message": "x" * 256 * 1024}


def test_worker_reply_size_and_large_input_do_not_bypass_supervision() -> None:
    with pytest.raises(VisionFault, match="VISION_PROCESS_FAILED"):
        ProcessBudget(processor=oversized_reply).run(b"", "", "", "status")
    start = time.monotonic()
    with pytest.raises(VisionFault, match="VISION_TIMEOUT"):
        ProcessBudget(deadline_seconds=0.1, processor=slow_processor).run(
            b"x" * MAX_BYTES, "", "", "status"
        )
    assert time.monotonic() - start < 3


def noisy_processor(data: bytes, mime: str, root: str, operation: str) -> dict[str, Any]:
    import os

    os.write(1, b"synthetic-private-media-marker")
    os.write(2, b"synthetic-private-media-marker")
    raise ValueError("synthetic-private-media-marker")


def forged_fault(data: bytes, mime: str, root: str, operation: str) -> dict[str, Any]:
    raise VisionFault(200, "synthetic-private-media-marker")


def test_worker_redacts_diagnostics_and_rejects_untrusted_error_codes(
    capfd: pytest.CaptureFixture[str],
) -> None:
    for processor in [noisy_processor, forged_fault]:
        with pytest.raises(VisionFault, match="VISION_PROCESS_FAILED") as exc:
            ProcessBudget(processor=processor).run(b"", "", "", "status")
        assert exc.value.status == 503
    output = capfd.readouterr()
    assert "synthetic-private-media-marker" not in output.out + output.err
