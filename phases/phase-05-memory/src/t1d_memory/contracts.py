"""Versioned research contracts. No treatment parameters or dose fields."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, BeforeValidator, ConfigDict, Field, model_validator


def explicit_time(value: object) -> str | datetime:
    if not isinstance(value, (str, datetime)) or (
        isinstance(value, str) and "t" not in value.lower()
    ):
        raise ValueError("Explicit timezone-aware timestamp required")
    return value


ExplicitTime = Annotated[AwareDatetime, BeforeValidator(explicit_time)]

Version = Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_.:-]+$")]
Nonnegative = Annotated[Decimal, Field(ge=0, allow_inf_nan=False, max_digits=28, decimal_places=12)]
ProfileName = Literal["structured-v1", "vector-v1", "hybrid-v1"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class Nutrients(Contract):
    carbohydrate_g: Nonnegative
    protein_g: Nonnegative
    fat_g: Nonnegative
    energy_kcal: Nonnegative


class Event(Contract):
    """Internal canonical-adapter input, never accepted from an HTTP caller."""

    id: UUID
    study_id: UUID
    patient_id: UUID
    kind: Literal["meal", "cgm", "insulin", "activity"]
    event_time: ExplicitTime
    available_at: ExplicitTime
    quality: Literal["accepted", "warning", "quarantined"]
    revision: int = Field(ge=1)
    source_chain: str = Field(min_length=1, max_length=512)
    data: dict[str, object]


class Source(Contract):
    id: UUID
    kind: Literal["meal", "cgm", "insulin", "activity"]
    event_time: ExplicitTime
    available_at: ExplicitTime
    revision: int = Field(ge=1)
    source_chain: str


class EpisodeDefinition(Contract):
    version: Version
    response_minutes: int = Field(ge=15, le=240)
    context_minutes: int = Field(ge=0, le=1440)
    min_cgm_samples: int = Field(ge=2, le=100)
    max_gap_minutes: int = Field(ge=1, le=240)
    min_span_fraction: float = Field(ge=0, le=1, allow_inf_nan=False)


DEFINITION = EpisodeDefinition(
    version="research-response120-context120-v1",
    response_minutes=120,
    context_minutes=120,
    min_cgm_samples=2,
    max_gap_minutes=30,
    min_span_fraction=0.5,
)


class GlucoseResponse(Contract):
    unit: Literal["mg/dL"] = "mg/dL"
    minimum: float = Field(gt=0, allow_inf_nan=False)
    maximum: float = Field(gt=0, allow_inf_nan=False)
    first: float = Field(gt=0, allow_inf_nan=False)
    last: float = Field(gt=0, allow_inf_nan=False)
    samples: int = Field(ge=2)
    observed_span_fraction: float = Field(ge=0, le=1, allow_inf_nan=False)
    maximum_gap_minutes: float = Field(ge=0, allow_inf_nan=False)


class Episode(Contract):
    schema_version: Literal["1.0"] = "1.0"
    id: UUID
    study_id: UUID
    patient_id: UUID
    anchor_id: UUID
    start_at: ExplicitTime
    end_at: ExplicitTime
    available_at: ExplicitTime
    definition_version: Version
    definition_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    sources: tuple[Source, ...] = Field(min_length=1, max_length=5000)
    foods: tuple[str, ...] = Field(min_length=1, max_length=50)
    nutrients: Nutrients
    response: GlucoseResponse
    warnings: tuple[str, ...]
    summary_version: Literal["structured-summary-v1"] = "structured-summary-v1"
    embedding_version: Literal["food-hash64-v1"] = "food-hash64-v1"

    @model_validator(mode="after")
    def temporal_lineage(self) -> "Episode":
        ids = [s.id for s in self.sources]
        if len(ids) != len(set(ids)) or self.anchor_id not in ids:
            raise ValueError("Unique complete anchor lineage required")
        if self.end_at <= self.start_at or self.available_at < self.end_at:
            raise ValueError("Episode chronology invalid")
        if any(
            s.available_at > self.available_at or s.event_time > self.end_at for s in self.sources
        ):
            raise ValueError("Source not yet available")
        return self


class RetrievalRequest(Contract):
    input_cutoff: ExplicitTime
    anchor_meal_id: UUID
    limit: int = Field(default=5, ge=1, le=20)
    retrieval_profile_version: ProfileName = "structured-v1"


class RebuildRequest(Contract):
    definition_version: Literal["research-response120-context120-v1"] = (
        "research-response120-context120-v1"
    )


class Evidence(Contract):
    episode_id: UUID
    anchor_meal_id: UUID
    source_revision_refs: list[UUID]
    event_time: ExplicitTime
    available_at: ExplicitTime
    score: float = Field(ge=0, le=1, allow_inf_nan=False)
    nutrient_similarity: float = Field(ge=0, le=1, allow_inf_nan=False)
    vector_similarity: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    graph_similarity: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    evidence_reasons: list[str]
    warnings: list[str]
    response: GlucoseResponse


class RetrievalResult(Contract):
    schema_version: Literal["1.0"] = "1.0"
    retrieval_id: UUID
    status: Literal["evidence", "abstained"]
    experimental: Literal[True] = True
    review_required: Literal[True] = True
    input_cutoff: ExplicitTime
    retrieval_profile_version: ProfileName
    definition_version: str
    definition_hash: str
    ranking_version: Literal["nutrient-food-weights-v1"] = "nutrient-food-weights-v1"
    embedding_version: str | None
    index_watermark: ExplicitTime | None
    episodes: list[Evidence]
    reason_codes: list[str]
    warnings: list[str]
    audit_reference: UUID
    # A profile never silently falls back to another profile.
    degraded_mode: None = None


class RebuildResult(Contract):
    run_id: UUID
    definition_version: str
    inserted: int = Field(ge=0)
    retained: int = Field(ge=0)
    tombstoned: int = Field(ge=0)
    skipped_meals: int = Field(ge=0)
    graph_status: Literal["synchronized", "unavailable", "not_configured"]
    index_watermark: datetime
    experimental: Literal[True] = True
