"""Exact-decimal input contracts. No clinical thresholds or inferred treatment values."""

from datetime import datetime
from decimal import Decimal, Inexact, localcontext
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    JsonValue,
    model_validator,
)


def explicit_time(value: object) -> str | datetime:
    if not isinstance(value, (str, datetime)) or (
        isinstance(value, str) and "t" not in value.lower()
    ):
        raise ValueError("Explicit timezone-aware RFC3339 timestamp required")
    return value


ExplicitTime = Annotated[AwareDatetime, BeforeValidator(explicit_time)]

Opaque = Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.:/-]+$")]
Number = Annotated[Decimal, Field(allow_inf_nan=False, max_digits=28, decimal_places=12)]
Nonnegative = Annotated[Number, Field(ge=0)]
Positive = Annotated[Number, Field(gt=0)]
Kind = Literal["cgm", "meal", "insulin", "activity"]
SourceType = Literal["synthetic", "device", "manual", "dataset", "model", "derived"]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class Provenance(Input):
    source_type: SourceType
    source_ref: Opaque
    source_version: Opaque
    recorded_at: ExplicitTime
    transformation_version: Opaque | None = None


class EventInput(Input):
    source_event_ref: Opaque
    event_time: ExplicitTime
    provenance: Provenance
    revision: int = Field(default=1, ge=1, le=1_000_000)
    supersedes_id: UUID | None = None

    @model_validator(mode="after")
    def revision_pair(self) -> "EventInput":
        if (self.revision == 1) != (self.supersedes_id is None):
            raise ValueError("Revision and predecessor must be consistent")
        return self


class CGMInput(EventInput):
    glucose_value: Positive | None
    glucose_unit: Literal["mg/dL", "mmol/L"]
    device_ref: Opaque
    sensor_status: Literal["valid", "missing", "unverified"]

    @model_validator(mode="after")
    def missingness(self) -> "CGMInput":
        if (self.glucose_value is None) != (self.sensor_status == "missing"):
            raise ValueError("Missing readings require explicit missing sensor status")
        return self


class NutritionInput(Input):
    carbohydrate_g: Nonnegative
    protein_g: Nonnegative
    fat_g: Nonnegative
    energy_kcal: Nonnegative
    reference_ref: Opaque
    method_version: Opaque
    uncertainty_status: Literal["unknown", "source_reported"]


class ComponentInput(Input):
    food_label: Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[^\x00-\x1f\x7f]+$")]
    portion_value: Positive | None = None
    portion_unit: Literal["g"] | None = None
    status: Literal["proposed", "corrected", "confirmed"] = "proposed"
    food_reference_id: Opaque | None = None
    nutrition: NutritionInput | None = None

    @model_validator(mode="after")
    def portion_pair(self) -> "ComponentInput":
        if (self.portion_value is None) != (self.portion_unit is None):
            raise ValueError("Portion value and unit must be supplied together")
        if self.status == "confirmed" and (self.portion_value is None or self.nutrition is None):
            raise ValueError("Confirmation requires portion and nutrition")
        return self


class MealInput(EventInput):
    status: Literal["draft", "confirmed"] = "draft"
    components: list[ComponentInput] = Field(min_length=1, max_length=50)
    nutrition: NutritionInput | None = None

    @model_validator(mode="after")
    def confirmation(self) -> "MealInput":
        if self.status == "confirmed" and (
            self.provenance.source_type == "model"
            or self.nutrition is None
            or any(c.status != "confirmed" for c in self.components)
        ):
            raise ValueError("Model estimates cannot self-confirm; complete human review required")
        if self.status == "confirmed" and self.nutrition is not None:
            with localcontext() as context:
                context.prec = 64
                for field in ["carbohydrate_g", "protein_g", "fat_g", "energy_kcal"]:
                    total = sum(
                        (getattr(c.nutrition, field) for c in self.components if c.nutrition),
                        Decimal(0),
                    )
                    if total != getattr(self.nutrition, field):
                        raise ValueError(
                            "Confirmed aggregate does not match component observations"
                        )
        return self


class InsulinInput(EventInput):
    event_kind: Literal["reported_delivery", "planned", "cancelled", "corrected"]
    amount_value: Nonnegative
    amount_unit: Literal["U"]
    insulin_type_ref: Opaque
    delivery_start: ExplicitTime | None = None
    delivery_end: ExplicitTime | None = None

    @model_validator(mode="after")
    def delivery_order(self) -> "InsulinInput":
        if self.delivery_start is not None and self.delivery_end is not None:
            if self.delivery_end < self.delivery_start:
                raise ValueError("Delivery time order invalid")
        return self


class ActivityInput(EventInput):
    activity_type: Opaque
    start_at: ExplicitTime
    end_at: ExplicitTime
    intensity_status: Literal["known", "unknown"]
    intensity_value: Nonnegative | None = None
    intensity_unit: Opaque | None = None

    @model_validator(mode="after")
    def interval(self) -> "ActivityInput":
        if self.start_at != self.event_time or self.end_at < self.start_at:
            raise ValueError("Activity time interval invalid")
        if self.intensity_status == "known":
            if self.intensity_value is None or self.intensity_unit is None:
                raise ValueError("Known intensity requires explicit value and unit")
        elif self.intensity_value is not None or self.intensity_unit is not None:
            raise ValueError("Unknown intensity cannot contain fabricated metrics")
        return self


class CGMBatch(Input):
    readings: list[CGMInput] = Field(min_length=1, max_length=100)


class MealBatch(Input):
    meals: list[MealInput] = Field(min_length=1, max_length=100)


class InsulinBatch(Input):
    events: list[InsulinInput] = Field(min_length=1, max_length=100)


class ActivityBatch(Input):
    events: list[ActivityInput] = Field(min_length=1, max_length=100)


class Receipt(Input):
    accepted: int
    duplicates: int
    received_at: datetime
    warnings: list[str]


class CGMReceipt(Receipt):
    reading_ids: list[UUID]


class MealReceipt(Receipt):
    meal_ids: list[UUID]


class EventReceipt(Receipt):
    event_ids: list[UUID]


class Conversion(Input):
    value: Decimal
    unit: Literal["mg/dL", "mmol/L"]
    version: Literal["niddk-0.0555-v1"] = "niddk-0.0555-v1"
    rounded: bool
    precision_digits: int = 64


def glucose(value: Decimal, source: str, target: Literal["mg/dL", "mmol/L"]) -> Conversion:
    """Versioned approximate physical-unit convention; originals are always preserved."""
    if not value.is_finite() or value <= 0 or source not in {"mg/dL", "mmol/L"}:
        raise ValueError("Invalid glucose measurement or unit")
    with localcontext() as ctx:
        ctx.prec = 64
        ctx.clear_flags()
        result = (
            value
            if source == target
            else (value * Decimal("0.0555") if target == "mmol/L" else value / Decimal("0.0555"))
        )
        return Conversion(value=result, unit=target, rounded=ctx.flags[Inexact])


class HistoryRecord(Input):
    id: UUID
    kind: Kind
    event_time: ExplicitTime
    recorded_at: ExplicitTime
    ingested_at: ExplicitTime
    available_at: ExplicitTime
    revision: int
    supersedes_id: UUID | None
    provenance: Provenance
    quality_state: Literal["accepted", "warning", "quarantined"]
    quality_flags: list[str]
    data: dict[str, JsonValue]


class HistoryPage(Input):
    records: list[HistoryRecord]
    next_cursor: str | None
    input_cutoff: ExplicitTime


class AuditRecord(Input):
    id: UUID
    action: str
    resource_type: str
    resource_id: UUID | None
    resource_revision: int | None
    source_ref: str | None
    occurred_at: ExplicitTime
    outcome: str
    correlation_id: UUID


class AuditPage(Input):
    events: list[AuditRecord]
    next_cursor: str | None
