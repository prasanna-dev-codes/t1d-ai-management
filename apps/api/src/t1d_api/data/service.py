"""Atomic research ingestion and point-in-time access. No inference or dosing logic."""

import base64
import hashlib
import json
import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal, Inexact, localcontext
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select, text, tuple_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from t1d_api.auth import Principal
from t1d_api.contracts import Role
from t1d_api.data.errors import DataError
from t1d_api.data.schemas import (
    ActivityInput,
    CGMInput,
    InsulinInput,
    Kind,
    MealInput,
    NutritionInput,
    glucose,
)
from t1d_api.db.models import (
    ActivityEvent,
    AuditEvent,
    CGMReading,
    DataSource,
    EventRevision,
    IngestionBatch,
    InsulinEvent,
    Meal,
    MealComponent,
    NutritionRecord,
    OutboxEvent,
)
from t1d_api.db.repository import EventRepository
from t1d_api.db.session import Database, Scope, authorize, set_actor

Payload = CGMInput | MealInput | InsulinInput | ActivityInput


def digest(value: Any) -> str:
    def clean(item: Any) -> Any:
        if isinstance(item, dict):
            return {key: clean(v) for key, v in item.items()}
        if isinstance(item, list):
            return [clean(v) for v in item]
        if isinstance(item, Decimal):
            # Input significant digits <=28; normalization here never rounds them.
            with localcontext() as ctx:
                ctx.prec = 64
                return str(item.normalize())
        if isinstance(item, datetime):
            return item.astimezone(UTC).isoformat()
        if isinstance(item, UUID):
            return str(item)
        return item

    return hashlib.sha256(
        json.dumps(clean(value), sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def failure_audit(
    db: Database, actor: UUID | None, operation: str, code: str, correlation: UUID
) -> None:
    """Independent rejection transaction; no clinical payload or untrusted scope persisted."""
    try:
        with db.sessions.begin() as session:
            set_actor(session, str(actor) if actor else "unauthenticated")
            session.execute(
                text("SELECT public.t1d_record_failure(:code,:op,:cid)"),
                {"code": code, "op": operation, "cid": correlation},
            )
    except SQLAlchemyError:
        logging.getLogger("t1d_api.requests").warning("audit_unavailable")


def audit(
    session: Session,
    scope: Scope,
    action: str,
    resource: str,
    identity: UUID | None,
    correlation: UUID,
    revision: int | None = None,
    source_ref: str | None = None,
) -> None:
    session.add(
        AuditEvent(
            study_id=scope.study_id,
            patient_id=scope.patient_id,
            actor_ref=str(scope.actor_id),
            action=action,
            resource_type=resource,
            resource_id=identity,
            resource_revision=revision,
            source_ref=source_ref,
            outcome="recorded",
            correlation_id=correlation,
        )
    )


def stream(item: Payload) -> str:
    return item.device_ref if isinstance(item, CGMInput) else ""


def identity(item: Payload, kind: Kind) -> tuple[str, str, str, str]:
    return kind, item.provenance.source_ref, stream(item), item.source_event_ref


def valid_times(item: Payload, now: datetime) -> None:
    times = [item.event_time, item.provenance.recorded_at]
    if isinstance(item, ActivityInput):
        times.extend([item.start_at, item.end_at])
    if isinstance(item, InsulinInput):
        times.extend(t for t in [item.delivery_start, item.delivery_end] if t is not None)
    if any(t > now for t in times) or item.provenance.recorded_at < item.event_time:
        raise DataError(422, "INVALID_TIMESTAMP")


def add_nutrition(
    session: Session,
    item: NutritionInput,
    scope: Scope,
    meal: UUID,
    revision: int,
    component: UUID | None,
    available: datetime,
) -> None:
    session.add(
        NutritionRecord(
            study_id=scope.study_id,
            patient_id=scope.patient_id,
            meal_id=meal,
            meal_revision=revision,
            component_id=component,
            scope="component" if component else "meal_total",
            carbohydrate_g=item.carbohydrate_g,
            protein_g=item.protein_g,
            fat_g=item.fat_g,
            energy_kcal=item.energy_kcal,
            reference_manifest={"reference_ref": item.reference_ref},
            method_version=item.method_version,
            uncertainty={"status": item.uncertainty_status},
            available_at=available,
        )
    )


def store_payload(
    session: Session, item: Payload, revision: EventRevision, principal: Principal
) -> None:
    common = {"id": revision.id, "study_id": revision.study_id, "patient_id": revision.patient_id}
    if isinstance(item, CGMInput):
        converted = (
            glucose(item.glucose_value, item.glucose_unit, "mmol/L")
            if item.glucose_value is not None
            else None
        )
        session.add(
            CGMReading(
                **common,
                event_time=revision.event_time,
                glucose_value=item.glucose_value,
                glucose_unit=item.glucose_unit,
                glucose_mmol_l=converted.value if converted else None,
                conversion_version="niddk-0.0555-v1",
                device_ref=item.device_ref,
                sensor_status=item.sensor_status,
            )
        )
    elif isinstance(item, InsulinInput):
        session.add(
            InsulinEvent(
                **common,
                **item.model_dump(
                    include={
                        "event_kind",
                        "amount_value",
                        "amount_unit",
                        "insulin_type_ref",
                        "delivery_start",
                        "delivery_end",
                    }
                ),
            )
        )
    elif isinstance(item, ActivityInput):
        delta = item.end_at - item.start_at
        micros = (delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds
        with localcontext() as ctx:
            ctx.prec = 64
            duration = Decimal(micros) / Decimal(60_000_000)
        session.add(
            ActivityEvent(
                **common,
                **item.model_dump(
                    include={
                        "activity_type",
                        "start_at",
                        "end_at",
                        "intensity_status",
                        "intensity_value",
                        "intensity_unit",
                    }
                ),
                duration_minutes=duration,
            )
        )
    else:
        confirmed = item.status == "confirmed"
        if confirmed and not principal.roles.intersection({Role.RESEARCHER, Role.CLINICIAN}):
            raise DataError(404, "RESOURCE_UNAVAILABLE")
        session.add(
            Meal(
                **common,
                status=item.status,
                meal_revision=item.revision,
                confirmed_by=principal.subject_id if confirmed else None,
                confirmed_at=revision.ingested_at if confirmed else None,
            )
        )
        session.flush()
        scope = Scope(principal.subject_id, revision.study_id, revision.patient_id)
        for component in item.components:
            cid = uuid4()
            session.add(
                MealComponent(
                    id=cid,
                    study_id=scope.study_id,
                    patient_id=scope.patient_id,
                    meal_id=revision.id,
                    meal_revision=item.revision,
                    **component.model_dump(exclude={"nutrition"}),
                )
            )
            session.flush()
            if component.nutrition:
                add_nutrition(
                    session,
                    component.nutrition,
                    scope,
                    revision.id,
                    item.revision,
                    cid,
                    revision.available_at,
                )
        if item.nutrition:
            add_nutrition(
                session,
                item.nutrition,
                scope,
                revision.id,
                item.revision,
                None,
                revision.available_at,
            )


class DataService:
    def __init__(self, database: Database) -> None:
        self.db = database

    def ingest(
        self,
        scope: Scope,
        principal: Principal,
        kind: Kind,
        items: Sequence[Payload],
        key: str,
        correlation: UUID,
    ) -> dict[str, Any]:
        try:
            self.db.check()
            if not principal.roles.intersection({Role.RESEARCHER, Role.CLINICIAN}):
                raise DataError(404, "RESOURCE_UNAVAILABLE")
            if (
                not (1 <= len(items) <= 100)
                or not 1 <= len(key) <= 128
                or not key.isascii()
                or not key.isprintable()
            ):
                raise DataError(422, "INVALID_INPUT")
            expected = {
                "cgm": CGMInput,
                "meal": MealInput,
                "insulin": InsulinInput,
                "activity": ActivityInput,
            }[kind]
            if any(not isinstance(item, expected) for item in items):
                raise DataError(422, "INVALID_INPUT")
            request_hash = digest([item.model_dump() for item in items])
            key_hash = hashlib.sha256(key.encode()).hexdigest()
            lock_key = f"{scope.actor_id}:{scope.study_id}:{scope.patient_id}:{kind}:{key_hash}"
            now = datetime.now(UTC)
            with self.db.sessions.begin() as session:
                authorize(session, scope, True)
                session.execute(
                    text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
                    {"key": lock_key},
                )
                prior = session.scalar(
                    select(IngestionBatch).where(
                        IngestionBatch.study_id == scope.study_id,
                        IngestionBatch.patient_id == scope.patient_id,
                        IngestionBatch.actor_id == scope.actor_id,
                        IngestionBatch.operation == kind,
                        IngestionBatch.key_digest == key_hash,
                    )
                )
                if prior:
                    if prior.request_digest != request_hash:
                        raise DataError(409, "IDEMPOTENCY_CONFLICT")
                    audit(session, scope, "idempotent_replay", kind, prior.id, correlation)
                    return prior.response
                for source_key in sorted({identity(i, kind) for i in items}):
                    session.execute(
                        text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
                        {"key": f"{scope.study_id}:{scope.patient_id}:{source_key}"},
                    )
                ids: list[UUID | None] = [None] * len(items)
                duplicates = 0
                flags: set[str] = set()
                for index, item in sorted(
                    enumerate(items), key=lambda x: (identity(x[1], kind), x[1].revision)
                ):
                    valid_times(item, now)
                    source = session.scalar(
                        select(DataSource).where(
                            DataSource.study_id == scope.study_id,
                            DataSource.source_ref == item.provenance.source_ref,
                            DataSource.source_version == item.provenance.source_version,
                            DataSource.approved.is_(True),
                            DataSource.source_type == item.provenance.source_type,
                        )
                    )
                    if source is None:
                        raise DataError(422, "SOURCE_UNAVAILABLE")
                    chain = select(EventRevision).where(
                        EventRevision.study_id == scope.study_id,
                        EventRevision.patient_id == scope.patient_id,
                        EventRevision.kind == kind,
                        EventRevision.source_ref == item.provenance.source_ref,
                        EventRevision.stream_ref == stream(item),
                        EventRevision.source_event_ref == item.source_event_ref,
                    )
                    existing = session.scalar(chain.where(EventRevision.revision == item.revision))
                    content_hash = digest(item.model_dump())
                    if existing:
                        if existing.content_digest != content_hash:
                            raise DataError(409, "EVENT_CONFLICT")
                        ids[index] = existing.id
                        duplicates += 1
                        continue
                    latest = session.scalar(chain.order_by(EventRevision.revision.desc()).limit(1))
                    if (latest is None and item.revision != 1) or (
                        latest is not None
                        and (
                            item.revision != latest.revision + 1 or item.supersedes_id != latest.id
                        )
                    ):
                        raise DataError(409, "EVENT_CONFLICT")
                    warnings = []
                    if item.event_time < item.provenance.recorded_at:
                        warnings.append("SOURCE_RECORDED_AFTER_EVENT")
                    if item.provenance.recorded_at < now:
                        warnings.append("INGESTED_AFTER_SOURCE_RECORDING")
                    if isinstance(item, ActivityInput):
                        delta = item.end_at - item.start_at
                        micros = (
                            delta.days * 86400 + delta.seconds
                        ) * 1_000_000 + delta.microseconds
                        with localcontext() as context:
                            context.prec = 64
                            _ = Decimal(micros) / Decimal(60_000_000)
                            if context.flags[Inexact]:
                                warnings.append("DURATION_MINUTES_APPROXIMATE")
                    quarantined = item.provenance.source_type in {"model", "derived"}
                    if quarantined:
                        warnings.append("UNREVIEWED_DERIVED_INPUT")
                    if isinstance(item, CGMInput) and item.sensor_status != "valid":
                        warnings.append("READING_" + item.sensor_status.upper())
                    revision = EventRevision(
                        id=uuid4(),
                        study_id=scope.study_id,
                        patient_id=scope.patient_id,
                        kind=kind,
                        source_ref=item.provenance.source_ref,
                        source_version=item.provenance.source_version,
                        stream_ref=stream(item),
                        source_event_ref=item.source_event_ref,
                        revision=item.revision,
                        supersedes_id=item.supersedes_id,
                        event_time=item.event_time.astimezone(UTC),
                        recorded_at=item.provenance.recorded_at.astimezone(UTC),
                        original_offset=str(item.event_time.utcoffset()),
                        provenance=item.provenance.model_dump(mode="json"),
                        content_digest=content_hash,
                        quality_state="quarantined"
                        if quarantined
                        else "warning"
                        if warnings
                        else "accepted",
                        quality_flags=warnings,
                    )
                    session.add(revision)
                    session.flush()
                    store_payload(session, item, revision, principal)
                    session.add(
                        OutboxEvent(
                            study_id=scope.study_id,
                            patient_id=scope.patient_id,
                            event_revision_id=revision.id,
                            operation="revision_recorded",
                        )
                    )
                    audit(
                        session,
                        scope,
                        "correction" if item.revision > 1 else "ingestion",
                        kind,
                        revision.id,
                        correlation,
                        item.revision,
                        item.provenance.source_ref,
                    )
                    session.flush()
                    flags.update(warnings)
                    ids[index] = revision.id
                field = (
                    "reading_ids"
                    if kind == "cgm"
                    else "meal_ids"
                    if kind == "meal"
                    else "event_ids"
                )
                response = {
                    "accepted": len(items) - duplicates,
                    "duplicates": duplicates,
                    field: [str(i) for i in ids],
                    "received_at": now.isoformat(),
                    "warnings": sorted(flags),
                }
                session.add(
                    IngestionBatch(
                        study_id=scope.study_id,
                        patient_id=scope.patient_id,
                        actor_id=scope.actor_id,
                        operation=kind,
                        key_digest=key_hash,
                        request_digest=request_hash,
                        response=response,
                    )
                )
                return response
        except DataError as exc:
            failure_audit(self.db, scope.actor_id, kind, exc.code, correlation)
            raise
        except IntegrityError as exc:
            failure_audit(self.db, scope.actor_id, kind, "EVENT_CONFLICT", correlation)
            raise DataError(409, "EVENT_CONFLICT") from exc
        except SQLAlchemyError as exc:
            failure_audit(self.db, scope.actor_id, kind, "DATABASE_UNAVAILABLE", correlation)
            raise DataError(503, "DATABASE_UNAVAILABLE") from exc

    def history(
        self,
        scope: Scope,
        kind: Kind,
        cutoff: datetime,
        limit: int,
        cursor: str | None,
        correlation: UUID,
    ) -> dict[str, Any]:
        try:
            self.db.check()
            if cutoff.tzinfo is None or cutoff > datetime.now(UTC) or not 1 <= limit <= 200:
                raise DataError(422, "INVALID_TIMESTAMP")
            with self.db.sessions.begin() as session:
                rows = EventRepository(session, scope).history(kind, cutoff, limit, cursor)
                result = []
                for row in rows[:limit]:
                    model = {
                        "cgm": CGMReading,
                        "meal": Meal,
                        "insulin": InsulinEvent,
                        "activity": ActivityEvent,
                    }[kind]
                    payload = session.get(
                        model,
                        {"id": row.id, "event_time": row.event_time} if kind == "cgm" else row.id,
                    )
                    if payload is None:
                        raise DataError(503, "DATABASE_UNAVAILABLE")
                    content = {
                        column.name: getattr(payload, column.name)
                        for column in model.__table__.columns
                    }
                    if kind == "meal":
                        content["components"] = [
                            {
                                c.name: getattr(component, c.name)
                                for c in MealComponent.__table__.columns
                            }
                            for component in session.scalars(
                                select(MealComponent).where(MealComponent.meal_id == row.id)
                            )
                        ]
                        content["nutrition_records"] = [
                            {
                                c.name: getattr(nutrition, c.name)
                                for c in NutritionRecord.__table__.columns
                            }
                            for nutrition in session.scalars(
                                select(NutritionRecord).where(NutritionRecord.meal_id == row.id)
                            )
                        ]
                    result.append(
                        {
                            "id": row.id,
                            "kind": kind,
                            "event_time": row.event_time,
                            "recorded_at": row.recorded_at,
                            "ingested_at": row.ingested_at,
                            "available_at": row.available_at,
                            "revision": row.revision,
                            "supersedes_id": row.supersedes_id,
                            "provenance": row.provenance,
                            "quality_state": row.quality_state,
                            "quality_flags": row.quality_flags,
                            "data": json.loads(json.dumps(content, default=str)),
                        }
                    )
                next_cursor = None
                if len(rows) > limit:
                    last = rows[limit - 1]
                    next_cursor = base64.urlsafe_b64encode(
                        json.dumps(
                            {"time": last.event_time.isoformat(), "id": str(last.id)}
                        ).encode()
                    ).decode()
                audit(session, scope, "data_access", kind, None, correlation)
                return {"records": result, "next_cursor": next_cursor, "input_cutoff": cutoff}
        except DataError as exc:
            failure_audit(self.db, scope.actor_id, "history", exc.code, correlation)
            raise
        except SQLAlchemyError as exc:
            failure_audit(self.db, scope.actor_id, "history", "DATABASE_UNAVAILABLE", correlation)
            raise DataError(503, "DATABASE_UNAVAILABLE") from exc

    def audit_history(
        self, scope: Scope, principal: Principal, limit: int, cursor: str | None, correlation: UUID
    ) -> dict[str, Any]:
        try:
            self.db.check()
            if (
                not principal.roles.intersection({Role.RESEARCHER, Role.CLINICIAN})
                or not 1 <= limit <= 200
            ):
                raise DataError(404, "RESOURCE_UNAVAILABLE")
            with self.db.sessions.begin() as session:
                authorize(session, scope, False)
                query = select(AuditEvent).where(
                    AuditEvent.study_id == scope.study_id, AuditEvent.patient_id == scope.patient_id
                )
                if cursor:
                    try:
                        if len(cursor) > 512:
                            raise ValueError()
                        value = json.loads(base64.urlsafe_b64decode(cursor))
                        when = datetime.fromisoformat(value["time"])
                        if when.tzinfo is None:
                            raise ValueError()
                        query = query.where(
                            tuple_(AuditEvent.created_at, AuditEvent.id) > (when, UUID(value["id"]))
                        )
                    except (ValueError, KeyError, TypeError) as exc:
                        raise DataError(422, "INVALID_INPUT") from exc
                rows = list(
                    session.scalars(
                        query.order_by(AuditEvent.created_at, AuditEvent.id).limit(limit + 1)
                    )
                )
                following = None
                if len(rows) > limit:
                    last = rows[limit - 1]
                    following = base64.urlsafe_b64encode(
                        json.dumps(
                            {"time": last.created_at.isoformat(), "id": str(last.id)}
                        ).encode()
                    ).decode()
                result = [
                    {
                        "id": row.id,
                        "action": row.action,
                        "resource_type": row.resource_type,
                        "resource_id": row.resource_id,
                        "resource_revision": row.resource_revision,
                        "source_ref": row.source_ref,
                        "occurred_at": row.created_at,
                        "outcome": row.outcome,
                        "correlation_id": row.correlation_id,
                    }
                    for row in rows[:limit]
                ]
                audit(session, scope, "audit_access", "audit", None, correlation)
                return {"events": result, "next_cursor": following}
        except DataError as exc:
            failure_audit(self.db, scope.actor_id, "history", exc.code, correlation)
            raise
        except SQLAlchemyError as exc:
            failure_audit(self.db, scope.actor_id, "history", "DATABASE_UNAVAILABLE", correlation)
            raise DataError(503, "DATABASE_UNAVAILABLE") from exc
