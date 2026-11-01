"""Strict artifact handoff; engineering-only artifacts can never serve food predictions."""

import hashlib
import json
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

import onnx
from google.protobuf.message import DecodeError
from pydantic import AwareDatetime, Field, model_validator

from t1d_vision.contracts import ClassLabel, Contract, ModelInfo, Version, VisionFault


class ArtifactManifest(Contract):
    schema_version: Literal["1.0"] = "1.0"
    model_id: UUID
    version: Version
    task: Literal["single_label_classification"] = "single_label_classification"
    taxonomy_version: Version
    dataset_version: Version
    dataset_manifest_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    split_manifest_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    preprocessing_version: Literal["rgb-letterbox224-v1"]
    code_revision: str = Field(min_length=7, max_length=64)
    evaluation_state: Literal["engineering_only", "evaluated_research"]
    evaluation_report: str = Field(pattern=r"^[A-Za-z0-9_.-]+\.json$", max_length=128)
    evaluation_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    onnx_file: str = Field(pattern=r"^[A-Za-z0-9_.-]+\.onnx$", max_length=128)
    onnx_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    classes: list[ClassLabel] = Field(min_length=2, max_length=500)
    temperature: float = Field(gt=0, le=100)
    calibrated: bool
    minimum_score: float | None = Field(default=None, ge=0, le=1)
    minimum_margin: float | None = Field(default=None, ge=0, le=1)
    rights_reference: str = Field(min_length=1, max_length=512)
    approval_reference: str = Field(min_length=1, max_length=512)
    exported_at: AwareDatetime

    @model_validator(mode="after")
    def identities(self) -> "ArtifactManifest":
        if len({c.canonical_id for c in self.classes}) != len(self.classes):
            raise ValueError("Duplicate class mapping")
        return self

    def info(self) -> ModelInfo:
        return ModelInfo(
            model_id=self.model_id,
            version=self.version,
            taxonomy_version=self.taxonomy_version,
            preprocessing_version=self.preprocessing_version,
            dataset_version=self.dataset_version,
            calibration_status="temperature_scaled" if self.calibrated else "uncalibrated",
        )


def read_json(path: Path, maximum: int = 1024 * 1024) -> dict[str, Any]:
    if path.stat().st_size > maximum:
        raise ValueError("Metadata size limit")
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise ValueError("Metadata object required")
    return value


def child_path(root: Path, name: str, maximum: int) -> Path:
    raw = root / name
    if raw.is_symlink():
        raise ValueError("Artifact symlink forbidden")
    path = raw.resolve()
    if (
        not path.is_relative_to(root.resolve())
        or path.is_symlink()
        or not path.is_file()
        or path.stat().st_size > maximum
    ):
        raise ValueError("Artifact path/size invalid")
    return path


def load_artifact(root: Path, serving: bool = True) -> tuple[ArtifactManifest, Path]:
    try:
        manifest = ArtifactManifest.model_validate(
            read_json(child_path(root, "manifest.json", 1024 * 1024))
        )
        if serving and (
            manifest.evaluation_state != "evaluated_research"
            or not manifest.calibrated
            or manifest.minimum_score is None
            or manifest.minimum_margin is None
        ):
            raise ValueError("Artifact not eligible for serving")
        graph = child_path(root, manifest.onnx_file, 100 * 1024 * 1024)
        report_path = child_path(root, manifest.evaluation_report, 1024 * 1024)
        if (
            hashlib.sha256(graph.read_bytes()).hexdigest() != manifest.onnx_sha256
            or hashlib.sha256(report_path.read_bytes()).hexdigest() != manifest.evaluation_sha256
        ):
            raise ValueError("Artifact checksum mismatch")
        report = read_json(report_path)
        if (
            report.get("dataset_manifest_sha256") != manifest.dataset_manifest_sha256
            or report.get("split_manifest_sha256") != manifest.split_manifest_sha256
            or report.get("model_id") != str(manifest.model_id)
            or report.get("class_ids") != [c.canonical_id for c in manifest.classes]
        ):
            raise ValueError("Evaluation/model identity mismatch")
        if serving and (
            report.get("engineering_only") is not False
            or type(report.get("test_samples")) is not int
            or report["test_samples"] <= 0
            or report.get("rights_approved") is not True
        ):
            raise ValueError("No eligible held-out evaluation")
        model = onnx.load_model(graph, load_external_data=False)
        tensors = list(model.graph.initializer)
        for sparse in model.graph.sparse_initializer:
            tensors.extend([sparse.values, sparse.indices])
        for node in model.graph.node:
            for attribute in node.attribute:
                if attribute.type in {onnx.AttributeProto.GRAPH, onnx.AttributeProto.GRAPHS}:
                    raise ValueError("Nested control-flow graphs forbidden")
                if attribute.type == onnx.AttributeProto.TENSOR:
                    tensors.append(attribute.t)
                tensors.extend(attribute.tensors)
                if attribute.type == onnx.AttributeProto.SPARSE_TENSOR:
                    tensors.extend(
                        [attribute.sparse_tensor.values, attribute.sparse_tensor.indices]
                    )
                for sparse in attribute.sparse_tensors:
                    tensors.extend([sparse.values, sparse.indices])
        for initializer in tensors:
            if initializer.data_location == onnx.TensorProto.EXTERNAL or initializer.external_data:
                raise ValueError("External tensor data forbidden")
        if model.functions or any(node.domain not in {"", "ai.onnx"} for node in model.graph.node):
            raise ValueError("Custom graph functions forbidden")
        onnx.checker.check_model(model, full_check=True)
        if len(model.graph.input) != 1 or len(model.graph.output) != 1:
            raise ValueError("Unexpected graph interface")
        dims = [d.dim_value for d in model.graph.input[0].type.tensor_type.shape.dim]
        out = [d.dim_value for d in model.graph.output[0].type.tensor_type.shape.dim]
        if (
            dims != [1, 3, 224, 224]
            or out != [1, len(manifest.classes)]
            or model.graph.input[0].type.tensor_type.elem_type != onnx.TensorProto.FLOAT
            or model.graph.output[0].type.tensor_type.elem_type != onnx.TensorProto.FLOAT
        ):
            raise ValueError("Graph shape/type incompatible")
        return manifest, graph
    except (
        OSError,
        ValueError,
        TypeError,
        RuntimeError,
        DecodeError,
        onnx.checker.ValidationError,
    ):
        raise VisionFault(503, "MODEL_UNAVAILABLE") from None
