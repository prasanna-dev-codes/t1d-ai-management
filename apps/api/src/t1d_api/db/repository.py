"""Patient-scoped SQL repository; current access is checked at its boundary."""

import base64
import json
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select, tuple_
from sqlalchemy.orm import Session

from t1d_api.data.errors import DataError
from t1d_api.data.schemas import Kind
from t1d_api.db.models import EventRevision
from t1d_api.db.session import Scope, authorize


class EventRepository:
    def __init__(self, session: Session, scope: Scope) -> None:
        self.session = session
        self.scope = scope

    def history(
        self, kind: Kind, cutoff: datetime, limit: int, cursor: str | None
    ) -> list[EventRevision]:
        session, scope = self.session, self.scope
        authorize(session, scope, False)
        # Rank known revisions BEFORE excluding moved/quarantined future events.
        ranked = (
            select(
                EventRevision.id,
                func.row_number()
                .over(
                    partition_by=(
                        EventRevision.source_ref,
                        EventRevision.stream_ref,
                        EventRevision.source_event_ref,
                    ),
                    order_by=EventRevision.revision.desc(),
                )
                .label("rank"),
            )
            .where(
                EventRevision.study_id == scope.study_id,
                EventRevision.patient_id == scope.patient_id,
                EventRevision.kind == kind,
                EventRevision.available_at <= cutoff,
            )
            .subquery()
        )
        query = (
            select(EventRevision)
            .join(ranked, ranked.c.id == EventRevision.id)
            .where(
                ranked.c.rank == 1,
                EventRevision.event_time <= cutoff,
                EventRevision.quality_state != "quarantined",
            )
        )
        if cursor:
            try:
                if len(cursor) > 512:
                    raise ValueError()
                value = json.loads(base64.urlsafe_b64decode(cursor.encode()))
                when = datetime.fromisoformat(value["time"])
                if when.tzinfo is None:
                    raise ValueError()
                query = query.where(
                    tuple_(EventRevision.event_time, EventRevision.id) > (when, UUID(value["id"]))
                )
            except (ValueError, KeyError, TypeError) as exc:
                raise DataError(422, "INVALID_INPUT") from exc
        rows = list(
            session.scalars(
                query.order_by(EventRevision.event_time, EventRevision.id).limit(limit + 1)
            )
        )
        return rows
