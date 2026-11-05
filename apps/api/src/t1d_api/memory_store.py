"""Phase 02 canonical adapter and bounded, RLS-protected episode/vector store."""

import json
from datetime import datetime
from typing import Literal, cast

from sqlalchemy import select, text
from sqlalchemy.orm import Session
from t1d_memory.contracts import DEFINITION, Episode, Event
from t1d_memory.ranking import embed

from t1d_api.data.errors import DataError
from t1d_api.data.schemas import Kind
from t1d_api.db.models import (
    ActivityEvent,
    CGMReading,
    DataSource,
    InsulinEvent,
    Meal,
    MealComponent,
    NutritionRecord,
)
from t1d_api.db.repository import EventRepository
from t1d_api.db.session import Scope, authorize

MAX_EVENTS_PER_KIND = 5000
MAX_EPISODES = 1000


def canonical_events(session: Session, scope: Scope, cutoff: datetime) -> list[Event]:
    output = []
    kinds: list[Kind] = ["meal", "cgm", "insulin", "activity"]
    for kind in kinds:
        rows = EventRepository(session, scope).history(kind, cutoff, MAX_EVENTS_PER_KIND, None)
        if len(rows) > MAX_EVENTS_PER_KIND:
            raise DataError(503, "MEMORY_HISTORY_LIMIT")
        for row in rows:
            source_approved = session.scalar(
                select(DataSource.approved).where(
                    DataSource.study_id == scope.study_id,
                    DataSource.source_ref == row.source_ref,
                    DataSource.source_version == row.source_version,
                )
            )
            if source_approved is not True:
                continue
            model = {
                "meal": Meal,
                "cgm": CGMReading,
                "insulin": InsulinEvent,
                "activity": ActivityEvent,
            }[kind]
            payload = session.get(
                model, {"id": row.id, "event_time": row.event_time} if kind == "cgm" else row.id
            )
            if payload is None:
                raise DataError(503, "MEMORY_SOURCE_UNAVAILABLE")
            data = {
                column.name: getattr(payload, column.name) for column in model.__table__.columns
            }
            available = row.available_at
            if kind == "meal":
                components = list(
                    session.scalars(select(MealComponent).where(MealComponent.meal_id == row.id))
                )
                nutrition = list(
                    session.scalars(
                        select(NutritionRecord).where(NutritionRecord.meal_id == row.id)
                    )
                )
                if any(n.available_at > cutoff for n in nutrition):
                    continue
                data["components"] = [
                    {c.name: getattr(e, c.name) for c in MealComponent.__table__.columns}
                    for e in components
                ]
                data["nutrition_records"] = [
                    {c.name: getattr(e, c.name) for c in NutritionRecord.__table__.columns}
                    for e in nutrition
                ]
                confirmed = data.get("confirmed_at")
                if isinstance(confirmed, datetime):
                    available = max(available, confirmed)
                available = max([available, *(n.available_at for n in nutrition)])
            if available > cutoff:
                continue
            output.append(
                Event(
                    id=row.id,
                    study_id=scope.study_id,
                    patient_id=scope.patient_id,
                    kind=kind,
                    event_time=row.event_time,
                    available_at=available,
                    quality=cast(Literal["accepted", "warning", "quarantined"], row.quality_state),
                    revision=row.revision,
                    source_chain=json.dumps([row.source_ref, row.stream_ref, row.source_event_ref]),
                    data=data,
                )
            )
    return output


def params(scope: Scope) -> dict[str, object]:
    return {"study": scope.study_id, "patient": scope.patient_id, "definition": DEFINITION.version}


def replace_episodes(
    session: Session, scope: Scope, episodes: list[Episode]
) -> tuple[int, int, int, datetime]:
    if len(episodes) > MAX_EPISODES:
        raise DataError(503, "MEMORY_EPISODE_LIMIT")
    authorize(session, scope, True)
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
        {"key": f"memory:{scope.study_id}:{scope.patient_id}"},
    )
    inserted, retained = 0, 0
    ids = [e.id for e in episodes]
    old = list(
        session.execute(
            text(
                "SELECT id,tombstoned FROM memory_episodes WHERE "
                "study_id=:study AND patient_id=:patient AND definition_version=:definition"
            ),
            params(scope),
        ).mappings()
    )
    existing = {row["id"]: row["tombstoned"] for row in old}
    tombstoned = sum(not row["tombstoned"] and row["id"] not in ids for row in old)
    session.execute(
        text(
            "UPDATE memory_episodes SET tombstoned=true WHERE "
            "study_id=:study AND patient_id=:patient AND definition_version=:definition "
            "AND NOT(id=ANY(CAST(:ids AS uuid[])))"
        ),
        {**params(scope), "ids": ids},
    )
    for episode in episodes:
        if episode.id in existing:
            # A tombstone is not resurrected by replay. A new definition/source
            # revision creates a new identity; withdrawal cannot be undone here.
            if not existing[episode.id]:
                retained += 1
            continue
        session.execute(
            text(
                "INSERT INTO memory_episodes "
                "(id,study_id,patient_id,anchor_id,definition_version,definition_hash,content_hash,"
                "start_at,end_at,manifest,embedding,embedding_version) VALUES "
                "(:id,:study,:patient,:anchor,:definition,:definition_hash,:content_hash,:start,:end,"
                "CAST(:manifest AS jsonb),CAST(:embedding AS vector),:embedding_version)"
            ),
            {
                **params(scope),
                "id": episode.id,
                "anchor": episode.anchor_id,
                "definition_hash": episode.definition_hash,
                "content_hash": episode.content_hash,
                "start": episode.start_at,
                "end": episode.end_at,
                "manifest": episode.model_dump_json(),
                "embedding": json.dumps(embed(episode.foods)),
                "embedding_version": episode.embedding_version,
            },
        )
        inserted += 1
    watermark = session.execute(
        text(
            "INSERT INTO memory_index_state "
            "(study_id,patient_id,definition_version) VALUES (:study,:patient,:definition) "
            "ON CONFLICT(study_id,patient_id,definition_version) "
            "DO UPDATE SET watermark=clock_timestamp() "
            "RETURNING watermark"
        ),
        params(scope),
    ).scalar_one()
    return inserted, retained, tombstoned, watermark


def load_episodes(
    session: Session, scope: Scope, cutoff: datetime
) -> tuple[list[Episode], datetime | None]:
    authorize(session, scope, False)
    watermark = session.execute(
        text(
            "SELECT watermark FROM memory_index_state WHERE "
            "study_id=:study AND patient_id=:patient AND definition_version=:definition"
        ),
        params(scope),
    ).scalar_one_or_none()
    rows = list(
        session.execute(
            text(
                "SELECT manifest FROM memory_episodes WHERE "
                "study_id=:study AND patient_id=:patient AND definition_version=:definition "
                "AND NOT tombstoned AND available_at<=:cutoff AND end_at<=:cutoff "
                "ORDER BY id LIMIT :maximum"
            ),
            {**params(scope), "cutoff": cutoff, "maximum": MAX_EPISODES + 1},
        ).scalars()
    )
    if len(rows) > MAX_EPISODES:
        raise DataError(503, "MEMORY_EPISODE_LIMIT")
    return [Episode.model_validate(row) for row in rows], watermark


def vector_scores(
    session: Session,
    scope: Scope,
    episodes: list[Episode],
    foods: tuple[str, ...],
    cutoff: datetime,
) -> dict[str, float]:
    if not episodes:
        return {}
    # IDs have already survived canonical revalidation. Exact scoped pgvector
    # computation avoids approximate global-index tenant starvation/leakage.
    rows = session.execute(
        text(
            "SELECT id,1-(embedding <=> CAST(:vector AS vector)) AS similarity "
            "FROM memory_episodes WHERE study_id=:study AND patient_id=:patient "
            "AND definition_version=:definition AND embedding_version='food-hash64-v1' "
            "AND NOT tombstoned AND available_at<=:cutoff AND id=ANY(CAST(:ids AS uuid[]))"
        ),
        {
            **params(scope),
            "vector": json.dumps(embed(foods)),
            "cutoff": cutoff,
            "ids": [e.id for e in episodes],
        },
    ).mappings()
    return {str(row["id"]): max(0.0, min(1.0, float(row["similarity"]))) for row in rows}
