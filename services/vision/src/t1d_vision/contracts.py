"""Versioned vision-only contracts; no nutrition, dose or forecast fields."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

Task = Literal[
    "single_label_classification",
    "multi_label_classification",
    "detection",
    "semantic_segmentation",
    "instance_segmentation",
]
Probability = Annotated[float, Field(ge=0, le=1)]
Version = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")]
Reason = Literal[
    "LOW_CONFIDENCE", "AMBIGUOUS_CLASS", "HUMAN_REVIEW_REQUIRED", "UNSUPPORTED_CAPABILITY"
]
Label = Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[^/\\\x00-\x1f\x7f]+$")]


class Contract(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, hide_input_in_errors=True, allow_inf_nan=False
    )


class VisionFault(Exception):
    def __init__(self, status: int, code: str) -> None:
        self.status, self.code = status, code
        super().__init__(code)


class ModelInfo(Contract):
    model_id: UUID
    version: Version
    taxonomy_version: Version
    preprocessing_version: Literal["rgb-letterbox224-v1"]
    dataset_version: Version
    calibration_status: Literal["temperature_scaled", "uncalibrated"]


class VisionAvailability(Contract):
    experimental: Literal[True] = True
    available: bool
    supported_tasks: list[Task]
    model: ModelInfo | None
    reason_code: Literal["MODEL_UNAVAILABLE", "MODEL_READY"]

    @model_validator(mode="after")
    def consistent(self) -> "VisionAvailability":
        if self.available:
            if (
                self.model is None
                or self.supported_tasks != ["single_label_classification"]
                or self.reason_code != "MODEL_READY"
            ):
                raise ValueError("Inconsistent availability")
        elif (
            self.model is not None
            or self.supported_tasks
            or self.reason_code != "MODEL_UNAVAILABLE"
        ):
            raise ValueError("Inconsistent unavailability")
        return self


class Candidate(Contract):
    canonical_id: str = Field(pattern=r"^food\.[a-z][a-z0-9_]*$", max_length=128)
    label: Label
    score: Probability


class ImageQuality(Contract):
    status: Literal["accepted", "warning"]
    width: int = Field(ge=1)
    height: int = Field(ge=1)
    warnings: list[Literal["COLOR_PROFILE_NOT_APPLIED", "RGB_CONVERTED", "ALPHA_COMPOSITED_WHITE"]]


class VisionResult(Contract):
    prediction_id: UUID
    status: Literal["review_required", "abstained"]
    experimental: Literal[True] = True
    task: Task
    model: ModelInfo
    image_quality: ImageQuality
    candidates: list[Candidate] = Field(max_length=5)
    review_required: Literal[True] = True
    reason_codes: list[Reason] = Field(min_length=1, max_length=8)
    processing_ms: float = Field(ge=0)
    completed_at: AwareDatetime

    @model_validator(mode="after")
    def coherent(self) -> "VisionResult":
        if self.task != "single_label_classification":
            if (
                self.status != "abstained"
                or self.candidates
                or self.reason_codes != ["UNSUPPORTED_CAPABILITY"]
            ):
                raise ValueError("Unsupported task cannot return predictions")
        elif not self.candidates:
            raise ValueError("Classification candidates missing")
        scores = [c.score for c in self.candidates]
        if (
            scores != sorted(scores, reverse=True)
            or sum(scores) > 1.000001
            or len({c.canonical_id for c in self.candidates}) != len(self.candidates)
        ):
            raise ValueError("Invalid ranked candidates")
        if self.status == "review_required" and self.reason_codes != ["HUMAN_REVIEW_REQUIRED"]:
            raise ValueError("Review state inconsistent")
        return self


class ClassLabel(Contract):
    canonical_id: str = Field(pattern=r"^food\.[a-z][a-z0-9_]*$", max_length=128)
    label: Label
