"""Strict frozen forecast, observation and portable model contracts."""

from datetime import datetime
from typing import Annotated, Final, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, BeforeValidator, ConfigDict, Field, model_validator


def explicit_time(value: object) -> str | datetime:
    if not isinstance(value, (str, datetime)) or (
        isinstance(value, str) and "t" not in value.lower()
    ):
        raise ValueError("Explicit zoned timestamp required")
    return value


Time = Annotated[AwareDatetime, BeforeValidator(explicit_time)]
Finite = Annotated[float, Field(allow_inf_nan=False)]
Horizon = Literal[30, 60, 90, 120]
Profile = Literal["persistence-v1", "linear-v1", "ridge-v1"]
HORIZONS: tuple[Horizon, ...] = (30, 60, 90, 120)
FEATURE_VERSION: Final = "cgm12-five-minute-age-aware-v1"
POLICY_VERSION: Final = "synthetic-research-grid5-fresh5-v2"


class ForecastContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class Reading(ForecastContract):
    id: UUID
    event_time: Time
    available_at: Time
    value: Annotated[float, Field(gt=0, allow_inf_nan=False)] | None
    unit: Literal["mg/dL", "mmol/L"]
    quality: Literal["accepted", "warning", "quarantined"]
    valid_sensor: bool
    quality_flags: tuple[str, ...] = ()


class ForecastRequest(ForecastContract):
    input_cutoff: Time
    horizons_minutes: tuple[Horizon, ...] = HORIZONS
    model_profile: Profile = "persistence-v1"

    @model_validator(mode="after")
    def horizons(self) -> "ForecastRequest":
        if not self.horizons_minutes or len(set(self.horizons_minutes)) != len(
            self.horizons_minutes
        ):
            raise ValueError("Nonempty unique supported horizons required")
        return self


class ForecastPoint(ForecastContract):
    horizon_minutes: Horizon
    target_time: Time
    glucose_mg_dl: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    lower_mg_dl: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    upper_mg_dl: Annotated[float, Field(gt=0, allow_inf_nan=False)]

    @model_validator(mode="after")
    def ordered(self) -> "ForecastPoint":
        if not self.lower_mg_dl <= self.glucose_mg_dl <= self.upper_mg_dl:
            raise ValueError("Ordered interval required")
        return self


class ForecastData(ForecastContract):
    prediction_id: UUID
    model_version_id: UUID
    artifact_sha256: str
    input_snapshot_ref: str
    source_revision_refs: list[UUID]
    points: list[ForecastPoint]
    evidence_refs: list[UUID] = []
    uncertainty_method: Literal["synthetic-patient-max-split-residual-v1"] = (
        "synthetic-patient-max-split-residual-v1"
    )
    nominal_coverage: Annotated[float, Field(ge=0.9, le=0.9, allow_inf_nan=False)] = 0.9


class ForecastResult(ForecastContract):
    status: Literal["eligible", "abstained"]
    experimental: Literal[True] = True
    review_required: Literal[True] = True
    input_cutoff: Time
    safety_evaluation_id: UUID
    policy_version: Literal["synthetic-research-grid5-fresh5-v2"] = POLICY_VERSION
    model_profile: Profile
    feature_version: Literal["cgm12-five-minute-age-aware-v1"] = FEATURE_VERSION
    reason_codes: list[str]
    assumptions: list[str]
    missing_data: list[str]
    warnings: list[str]
    data: ForecastData | None

    @model_validator(mode="after")
    def abstention(self) -> "ForecastResult":
        if (self.status == "eligible") != (self.data is not None):
            raise ValueError("Abstention must not contain predictions")
        return self


class HorizonModel(ForecastContract):
    horizon: Horizon
    weights: tuple[Finite, ...] = Field(min_length=6, max_length=6)
    radius: Annotated[float, Field(ge=0, allow_inf_nan=False)]


class ForecastModel(ForecastContract):
    profile: Profile
    horizons: tuple[HorizonModel, ...] = Field(min_length=4, max_length=4)

    @model_validator(mode="after")
    def complete(self) -> "ForecastModel":
        if tuple(h.horizon for h in self.horizons) != HORIZONS:
            raise ValueError("All horizons in canonical order required")
        return self


class ModelBundle(ForecastContract):
    format_version: Literal["synthetic-forecast-bundle-v1"] = "synthetic-forecast-bundle-v1"
    feature_version: Literal["cgm12-five-minute-age-aware-v1"] = FEATURE_VERSION
    policy_version: Literal["synthetic-research-grid5-fresh5-v2"] = POLICY_VERSION
    data_kind: Literal["authored-synthetic-only"] = "authored-synthetic-only"
    training_manifest_sha256: str
    calibration_patients: int = Field(ge=9)
    models: tuple[ForecastModel, ...] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def profiles(self) -> "ModelBundle":
        if {m.profile for m in self.models} != {"persistence-v1", "linear-v1", "ridge-v1"}:
            raise ValueError("Exactly three distinct profiles required")
        return self
