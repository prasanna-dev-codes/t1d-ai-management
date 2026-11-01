"""Canonical Phase 02 persistence. No treatment or model inference implementation."""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Entity:
    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid4, server_default=func.gen_random_uuid()
    )
    schema_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )


class ResearchStudy(Entity, Base):
    __tablename__ = "research_studies"
    reference: Mapped[str] = mapped_column(String(128), unique=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    synthetic: Mapped[bool] = mapped_column(Boolean, default=True)


class Patient(Entity, Base):
    __tablename__ = "patients"
    study_id: Mapped[UUID] = mapped_column(ForeignKey("research_studies.id"))
    research_subject_ref: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(16), default="active")
    provenance: Mapped[dict[str, Any]] = mapped_column(JSONB)
    __table_args__ = (
        UniqueConstraint("id", "study_id"),
        UniqueConstraint("study_id", "research_subject_ref"),
        CheckConstraint("status IN ('active','withdrawn','suspended')"),
    )


class ConsentRecord(Entity, Base):
    __tablename__ = "consent_records"
    patient_id: Mapped[UUID] = mapped_column()
    study_id: Mapped[UUID] = mapped_column()
    version: Mapped[int] = mapped_column()
    status: Mapped[str] = mapped_column(String(16))
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    actor_id: Mapped[UUID] = mapped_column()
    synthetic: Mapped[bool] = mapped_column(Boolean)
    __table_args__ = (
        ForeignKeyConstraint(["patient_id", "study_id"], ["patients.id", "patients.study_id"]),
        UniqueConstraint("study_id", "patient_id", "version"),
        CheckConstraint("status IN ('granted','revoked') AND version > 0"),
        CheckConstraint("valid_until IS NULL OR valid_until > effective_at"),
    )


class AccessGrant(Entity, Base):
    __tablename__ = "access_grants"
    patient_id: Mapped[UUID] = mapped_column()
    study_id: Mapped[UUID] = mapped_column()
    actor_id: Mapped[UUID] = mapped_column(index=True)
    can_read: Mapped[bool] = mapped_column(Boolean)
    can_write: Mapped[bool] = mapped_column(Boolean)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[UUID] = mapped_column()
    __table_args__ = (
        ForeignKeyConstraint(["patient_id", "study_id"], ["patients.id", "patients.study_id"]),
        UniqueConstraint("study_id", "patient_id", "actor_id"),
        CheckConstraint("NOT can_write OR can_read"),
    )


class DataSource(Entity, Base):
    __tablename__ = "data_sources"
    study_id: Mapped[UUID] = mapped_column(ForeignKey("research_studies.id"))
    source_ref: Mapped[str] = mapped_column(String(128))
    source_version: Mapped[str] = mapped_column(String(128))
    source_type: Mapped[str] = mapped_column(String(16))
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    license_reference: Mapped[str] = mapped_column(String(256))
    __table_args__ = (UniqueConstraint("study_id", "source_ref", "source_version"),)


class EventRevision(Entity, Base):
    __tablename__ = "event_revisions"
    study_id: Mapped[UUID] = mapped_column()
    patient_id: Mapped[UUID] = mapped_column()
    kind: Mapped[str] = mapped_column(String(16))
    source_ref: Mapped[str] = mapped_column(String(128))
    source_version: Mapped[str] = mapped_column(String(128))
    source_event_ref: Mapped[str] = mapped_column(String(128))
    stream_ref: Mapped[str] = mapped_column(String(128))
    revision: Mapped[int] = mapped_column()
    supersedes_id: Mapped[UUID | None] = mapped_column(unique=True)
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )
    original_offset: Mapped[str] = mapped_column(String(32))
    provenance: Mapped[dict[str, Any]] = mapped_column(JSONB)
    content_digest: Mapped[str] = mapped_column(String(64))
    quality_state: Mapped[str] = mapped_column(String(16))
    quality_flags: Mapped[list[str]] = mapped_column(JSONB)
    __table_args__ = (
        ForeignKeyConstraint(["patient_id", "study_id"], ["patients.id", "patients.study_id"]),
        ForeignKeyConstraint(
            ["study_id", "source_ref", "source_version"],
            ["data_sources.study_id", "data_sources.source_ref", "data_sources.source_version"],
        ),
        UniqueConstraint("id", "study_id", "patient_id"),
        UniqueConstraint("id", "study_id", "patient_id", "kind"),
        UniqueConstraint("id", "event_time", "study_id", "patient_id", "kind"),
        UniqueConstraint("id", "event_time", "study_id", "patient_id"),
        ForeignKeyConstraint(
            ["supersedes_id", "study_id", "patient_id"],
            ["event_revisions.id", "event_revisions.study_id", "event_revisions.patient_id"],
        ),
        UniqueConstraint(
            "study_id",
            "patient_id",
            "kind",
            "source_ref",
            "stream_ref",
            "source_event_ref",
            "revision",
        ),
        CheckConstraint("kind IN ('cgm','meal','insulin','activity')"),
        CheckConstraint(
            "revision > 0 AND ((revision = 1 AND supersedes_id IS NULL) OR (revision > "
            "1 AND supersedes_id IS NOT NULL))"
        ),
        CheckConstraint(
            "isfinite(event_time) AND isfinite(recorded_at) AND event_time <= "
            "ingested_at AND recorded_at <= ingested_at AND available_at >= ingested_at"
            " AND available_at >= recorded_at"
        ),
        CheckConstraint("quality_state IN ('accepted','warning','quarantined')"),
        Index(
            "ix_events_scope_time",
            "study_id",
            "patient_id",
            "kind",
            "event_time",
            "available_at",
            "id",
        ),
    )


class ScopedPayload:
    id: Mapped[UUID] = mapped_column(primary_key=True)
    study_id: Mapped[UUID] = mapped_column()
    patient_id: Mapped[UUID] = mapped_column()


def scope_fk() -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        ["id", "study_id", "patient_id", "kind"],
        [
            "event_revisions.id",
            "event_revisions.study_id",
            "event_revisions.patient_id",
            "event_revisions.kind",
        ],
    )


class CGMReading(ScopedPayload, Base):
    __tablename__ = "cgm_readings"
    kind: Mapped[str] = mapped_column(String(16), server_default=text("'cgm'"))
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    glucose_value: Mapped[Decimal | None] = mapped_column(Numeric())
    glucose_unit: Mapped[str] = mapped_column(String(8))
    glucose_mmol_l: Mapped[Decimal | None] = mapped_column(Numeric())
    conversion_version: Mapped[str] = mapped_column(String(32))
    device_ref: Mapped[str] = mapped_column(String(128))
    sensor_status: Mapped[str] = mapped_column(String(16))
    __table_args__ = (
        CheckConstraint("kind='cgm'"),
        ForeignKeyConstraint(
            ["id", "event_time", "study_id", "patient_id", "kind"],
            [
                "event_revisions.id",
                "event_revisions.event_time",
                "event_revisions.study_id",
                "event_revisions.patient_id",
                "event_revisions.kind",
            ],
        ),
        CheckConstraint("glucose_unit IN ('mg/dL','mmol/L')"),
        CheckConstraint(
            "(glucose_value IS NULL AND glucose_mmol_l IS NULL AND "
            "sensor_status='missing') OR (glucose_value IS NOT NULL AND glucose_mmol_l "
            "IS NOT NULL AND glucose_value>0 AND glucose_value<'Infinity'::numeric AND "
            "glucose_mmol_l>0 AND glucose_mmol_l<'Infinity'::numeric AND sensor_status "
            "IN ('valid','unverified'))"
        ),
        Index("ix_cgm_scope_time", "study_id", "patient_id", "event_time"),
    )


class Meal(ScopedPayload, Base):
    __tablename__ = "meals"
    kind: Mapped[str] = mapped_column(String(16), server_default=text("'meal'"))
    status: Mapped[str] = mapped_column(String(16))
    meal_revision: Mapped[int] = mapped_column()
    confirmed_by: Mapped[UUID | None] = mapped_column()
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint("kind='meal'"),
        scope_fk(),
        UniqueConstraint("id", "study_id", "patient_id"),
        CheckConstraint(
            "(status='draft' AND confirmed_by IS NULL AND confirmed_at IS NULL) OR "
            "(status='confirmed' AND confirmed_by IS NOT NULL AND confirmed_at IS NOT "
            "NULL)"
        ),
    )


class MealComponent(Entity, Base):
    __tablename__ = "meal_components"
    study_id: Mapped[UUID] = mapped_column()
    patient_id: Mapped[UUID] = mapped_column()
    meal_id: Mapped[UUID] = mapped_column()
    meal_revision: Mapped[int] = mapped_column()
    food_label: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(16))
    portion_value: Mapped[Decimal | None] = mapped_column(Numeric())
    portion_unit: Mapped[str | None] = mapped_column(String(8))
    food_reference_id: Mapped[str | None] = mapped_column(String(128))
    __table_args__ = (
        ForeignKeyConstraint(
            ["meal_id", "study_id", "patient_id"],
            ["meals.id", "meals.study_id", "meals.patient_id"],
        ),
        UniqueConstraint("id", "meal_id", "study_id", "patient_id"),
        CheckConstraint(
            "(portion_value IS NULL AND portion_unit IS NULL) OR (portion_value IS NOT "
            "NULL AND portion_value>0 AND portion_value<'Infinity'::numeric AND "
            "portion_unit='g')"
        ),
        CheckConstraint("status IN ('proposed','corrected','confirmed')"),
    )


class NutritionRecord(Entity, Base):
    __tablename__ = "nutrition_records"
    study_id: Mapped[UUID] = mapped_column()
    patient_id: Mapped[UUID] = mapped_column()
    meal_id: Mapped[UUID] = mapped_column()
    meal_revision: Mapped[int] = mapped_column()
    component_id: Mapped[UUID | None] = mapped_column()
    scope: Mapped[str] = mapped_column(String(16))
    carbohydrate_g: Mapped[Decimal] = mapped_column(Numeric())
    protein_g: Mapped[Decimal] = mapped_column(Numeric())
    fat_g: Mapped[Decimal] = mapped_column(Numeric())
    energy_kcal: Mapped[Decimal] = mapped_column(Numeric())
    reference_manifest: Mapped[dict[str, Any]] = mapped_column(JSONB)
    method_version: Mapped[str] = mapped_column(String(128))
    uncertainty: Mapped[dict[str, Any]] = mapped_column(JSONB)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )
    __table_args__ = (
        ForeignKeyConstraint(
            ["meal_id", "study_id", "patient_id"],
            ["meals.id", "meals.study_id", "meals.patient_id"],
        ),
        ForeignKeyConstraint(
            ["component_id", "meal_id", "study_id", "patient_id"],
            [
                "meal_components.id",
                "meal_components.meal_id",
                "meal_components.study_id",
                "meal_components.patient_id",
            ],
        ),
        CheckConstraint(
            "(scope='meal_total' AND component_id IS NULL) OR (scope='component' AND "
            "component_id IS NOT NULL)"
        ),
        *(
            CheckConstraint(f"{f}>=0 AND {f}<'Infinity'::numeric")
            for f in ["carbohydrate_g", "protein_g", "fat_g", "energy_kcal"]
        ),
        Index(
            "uq_nutrition_total",
            "meal_id",
            unique=True,
            postgresql_where=text("scope='meal_total'"),
        ),
        UniqueConstraint("component_id"),
    )


class InsulinEvent(ScopedPayload, Base):
    __tablename__ = "insulin_events"
    kind: Mapped[str] = mapped_column(String(16), server_default=text("'insulin'"))
    event_kind: Mapped[str] = mapped_column(String(32))
    amount_value: Mapped[Decimal] = mapped_column(Numeric())
    amount_unit: Mapped[str] = mapped_column(String(8))
    insulin_type_ref: Mapped[str] = mapped_column(String(128))
    delivery_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivery_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint("kind='insulin'"),
        scope_fk(),
        CheckConstraint("event_kind IN ('reported_delivery','planned','cancelled','corrected')"),
        CheckConstraint("amount_value>=0 AND amount_value<'Infinity'::numeric AND amount_unit='U'"),
        CheckConstraint(
            "delivery_start IS NULL OR delivery_end IS NULL OR delivery_end>=delivery_start"
        ),
    )


class ActivityEvent(ScopedPayload, Base):
    __tablename__ = "activity_events"
    kind: Mapped[str] = mapped_column(String(16), server_default=text("'activity'"))
    activity_type: Mapped[str] = mapped_column(String(128))
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    duration_minutes: Mapped[Decimal] = mapped_column(Numeric())
    intensity_status: Mapped[str] = mapped_column(String(16))
    intensity_value: Mapped[Decimal | None] = mapped_column(Numeric())
    intensity_unit: Mapped[str | None] = mapped_column(String(128))
    __table_args__ = (
        CheckConstraint("kind='activity'"),
        scope_fk(),
        CheckConstraint("end_at>=start_at AND duration_minutes>=0"),
        CheckConstraint(
            "(intensity_status='unknown' AND intensity_value IS NULL AND intensity_unit"
            " IS NULL) OR (intensity_status='known' AND intensity_value IS NOT NULL AND"
            " intensity_value>=0 AND intensity_value<'Infinity'::numeric AND "
            "intensity_unit IS NOT NULL)"
        ),
    )


class IngestionBatch(Entity, Base):
    __tablename__ = "ingestion_batches"
    study_id: Mapped[UUID] = mapped_column()
    patient_id: Mapped[UUID] = mapped_column()
    actor_id: Mapped[UUID] = mapped_column()
    operation: Mapped[str] = mapped_column(String(16))
    key_digest: Mapped[str] = mapped_column(String(64))
    request_digest: Mapped[str] = mapped_column(String(64))
    response: Mapped[dict[str, Any]] = mapped_column(JSONB)
    __table_args__ = (
        ForeignKeyConstraint(["patient_id", "study_id"], ["patients.id", "patients.study_id"]),
        UniqueConstraint("study_id", "patient_id", "actor_id", "operation", "key_digest"),
    )


class AuditEvent(Entity, Base):
    __tablename__ = "audit_events"
    study_id: Mapped[UUID | None] = mapped_column(ForeignKey("research_studies.id"))
    patient_id: Mapped[UUID | None] = mapped_column()
    actor_ref: Mapped[str] = mapped_column(String(128))
    action: Mapped[str] = mapped_column(String(64))
    resource_type: Mapped[str] = mapped_column(String(32))
    resource_id: Mapped[UUID | None] = mapped_column()
    resource_revision: Mapped[int | None] = mapped_column()
    source_ref: Mapped[str | None] = mapped_column(String(128))
    outcome: Mapped[str] = mapped_column(String(32))
    reason_code: Mapped[str | None] = mapped_column(String(64))
    correlation_id: Mapped[UUID] = mapped_column()
    __table_args__ = (Index("ix_audit_scope_time", "study_id", "patient_id", "created_at", "id"),)


class OutboxEvent(Entity, Base):
    __tablename__ = "outbox_events"
    study_id: Mapped[UUID] = mapped_column()
    patient_id: Mapped[UUID] = mapped_column()
    event_revision_id: Mapped[UUID] = mapped_column()
    operation: Mapped[str] = mapped_column(String(32))
    __table_args__ = (
        ForeignKeyConstraint(
            ["event_revision_id", "study_id", "patient_id"],
            ["event_revisions.id", "event_revisions.study_id", "event_revisions.patient_id"],
        ),
    )


class ModelVersion(Entity, Base):
    __tablename__ = "model_versions"
    model_name: Mapped[str] = mapped_column(String(128))
    version: Mapped[str] = mapped_column(String(128))
    artifact_object_ref: Mapped[str] = mapped_column(String(256))
    artifact_digest: Mapped[str] = mapped_column(String(128))
    code_revision: Mapped[str] = mapped_column(String(128))
    data_manifest_ref: Mapped[str] = mapped_column(String(256))
    feature_schema_version: Mapped[str] = mapped_column(String(128))
    preprocessing_version: Mapped[str] = mapped_column(String(128))
    evaluation_report_ref: Mapped[str] = mapped_column(String(256))
    uncertainty_method: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), default="candidate")
    applicability: Mapped[dict[str, Any]] = mapped_column(JSONB)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSONB)
    __table_args__ = (
        UniqueConstraint("model_name", "version"),
        CheckConstraint("status='candidate'"),
    )
