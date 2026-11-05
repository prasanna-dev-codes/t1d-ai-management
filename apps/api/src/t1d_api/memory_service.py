"""Authorized Phase 05 orchestration. No client-supplied medical snapshot is trusted."""

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from t1d_memory.contracts import (
    DEFINITION,
    RebuildResult,
    RetrievalRequest,
    RetrievalResult,
)
from t1d_memory.episodes import build_episodes, definition_hash, foods_and_nutrients
from t1d_memory.graph import GraphIndex, GraphUnavailable
from t1d_memory.ranking import EMBEDDING_VERSION, rank

from t1d_api.auth import Principal
from t1d_api.contracts import Role
from t1d_api.data.errors import DataError
from t1d_api.data.service import audit, failure_audit
from t1d_api.db.session import Database, Scope, authorize
from t1d_api.memory_store import (
    canonical_events,
    load_episodes,
    replace_episodes,
    vector_scores,
)


def principal_check(scope: Scope, principal: Principal) -> None:
    if principal.expires_at <= datetime.now(UTC):
        raise DataError(401, "UNAUTHENTICATED")
    if principal.subject_id != scope.actor_id or not principal.roles.intersection(
        {Role.RESEARCHER, Role.CLINICIAN}
    ):
        raise DataError(404, "RESOURCE_UNAVAILABLE")


class MemoryService:
    def __init__(self, database: Database | None, graph: GraphIndex | None = None) -> None:
        self.db = database
        self.graph = graph

    def database(self) -> Database:
        if self.db is None:
            raise DataError(503, "DATABASE_UNAVAILABLE")
        self.db.check()
        return self.db

    def rejection(self, scope: Scope, correlation: UUID, code: str) -> None:
        if self.db is not None:
            failure_audit(
                self.db,
                scope.actor_id,
                "history",
                "RESOURCE_UNAVAILABLE"
                if code == "RESOURCE_UNAVAILABLE"
                else "DATABASE_UNAVAILABLE",
                correlation,
            )

    def rebuild(self, scope: Scope, principal: Principal, correlation: UUID) -> RebuildResult:
        try:
            principal_check(scope, principal)
            db = self.database()
            run_id = uuid4()
            with db.sessions.begin() as session:
                authorize(session, scope, True)
                # Serialize before snapshot selection, not only before insertion.
                session.execute(
                    text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
                    {"key": f"memory:{scope.study_id}:{scope.patient_id}"},
                )
                cutoff = datetime.now(UTC)
                events = canonical_events(session, scope, cutoff)
                episodes, skipped = build_episodes(events, cutoff, scope.study_id, scope.patient_id)
                inserted, retained, tombstoned, watermark = replace_episodes(
                    session, scope, episodes
                )
                audit(
                    session,
                    scope,
                    "memory_rebuild",
                    "memory",
                    run_id,
                    correlation,
                    source_ref=DEFINITION.version,
                )
                principal_check(scope, principal)
                authorize(session, scope, True)
            graph_status: Literal["synchronized", "unavailable", "not_configured"] = (
                "not_configured"
            )
            if self.graph is not None:
                # Reauthorize after canonical commit. A failed remote update never
                # rolls back the authoritative tombstones or becomes a silent fallback.
                with db.sessions.begin() as session:
                    principal_check(scope, principal)
                    authorize(session, scope, True)
                    stored, state = load_episodes(session, scope, datetime.now(UTC))
                    if state != watermark:
                        raise GraphUnavailable()
                    try:
                        self.graph.replace(scope.study_id, scope.patient_id, stored, watermark)
                        graph_status = "synchronized"
                    except GraphUnavailable:
                        graph_status = "unavailable"
                    audit(
                        session,
                        scope,
                        "memory_graph_sync",
                        "memory",
                        run_id,
                        correlation,
                        source_ref=graph_status,
                    )
            return RebuildResult(
                run_id=run_id,
                definition_version=DEFINITION.version,
                inserted=inserted,
                retained=retained,
                tombstoned=tombstoned,
                skipped_meals=skipped,
                graph_status=graph_status,
                index_watermark=watermark,
            )
        except DataError as exc:
            self.rejection(scope, correlation, exc.code)
            raise
        except (SQLAlchemyError, ValueError, ValidationError, GraphUnavailable):
            self.rejection(scope, correlation, "DATABASE_UNAVAILABLE")
            raise DataError(503, "MEMORY_REBUILD_UNAVAILABLE") from None

    def retrieve(
        self, scope: Scope, principal: Principal, query: RetrievalRequest, correlation: UUID
    ) -> RetrievalResult:
        try:
            principal_check(scope, principal)
            if query.input_cutoff > datetime.now(UTC):
                raise DataError(422, "INVALID_TIMESTAMP")
            db = self.database()
            result_id = uuid4()
            with db.sessions.begin() as session:
                authorize(session, scope, False)
                events = canonical_events(session, scope, query.input_cutoff)
                anchor = next(
                    (e for e in events if e.kind == "meal" and e.id == query.anchor_meal_id), None
                )
                if anchor is None:
                    raise DataError(404, "RESOURCE_UNAVAILABLE")
                content = foods_and_nutrients(anchor)
                if content is None:
                    raise DataError(422, "MEMORY_ANCHOR_UNCONFIRMED")
                foods, nutrients = content
                rebuilt, _ = build_episodes(
                    events, query.input_cutoff, scope.study_id, scope.patient_id
                )
                canonical = {e.id: e for e in rebuilt}
                stored, watermark = load_episodes(session, scope, query.input_cutoff)
                pool = [
                    e
                    for e in stored
                    if e.anchor_id != anchor.id
                    and e.id in canonical
                    and e.model_dump(exclude={"available_at"})
                    == canonical[e.id].model_dump(exclude={"available_at"})
                ]
                vectors, graphs = None, None
                if query.retrieval_profile_version != "structured-v1":
                    vectors = vector_scores(session, scope, pool, foods, query.input_cutoff)
                if query.retrieval_profile_version == "hybrid-v1":
                    if self.graph is None or watermark is None:
                        raise DataError(503, "MEMORY_GRAPH_UNAVAILABLE")
                    graphs = self.graph.similarities(
                        scope.study_id,
                        scope.patient_id,
                        [str(e.id) for e in pool],
                        foods,
                        query.input_cutoff,
                        watermark,
                    )
                evidence = rank(
                    pool,
                    foods,
                    nutrients,
                    query.retrieval_profile_version,
                    query.limit,
                    vectors,
                    graphs,
                )
                # Late arrivals/corrections known by cutoff and revocation are checked
                # again after derived search; no cached graph result grants access.
                final_events = canonical_events(session, scope, query.input_cutoff)
                final, _ = build_episodes(
                    final_events, query.input_cutoff, scope.study_id, scope.patient_id
                )
                valid_ids = {e.id for e in final}
                if any(e.episode_id not in valid_ids for e in evidence):
                    raise DataError(503, "MEMORY_SNAPSHOT_CHANGED")
                principal_check(scope, principal)
                authorize(session, scope, False)
                audit(
                    session,
                    scope,
                    "memory_retrieval",
                    "memory",
                    result_id,
                    correlation,
                    source_ref=query.retrieval_profile_version,
                )
                return RetrievalResult(
                    retrieval_id=result_id,
                    status="evidence" if evidence else "abstained",
                    input_cutoff=query.input_cutoff,
                    retrieval_profile_version=query.retrieval_profile_version,
                    definition_version=DEFINITION.version,
                    definition_hash=definition_hash(DEFINITION),
                    embedding_version=None if vectors is None else EMBEDDING_VERSION,
                    index_watermark=watermark
                    if watermark is not None and watermark <= query.input_cutoff
                    else None,
                    episodes=evidence,
                    reason_codes=[] if evidence else ["NO_ELIGIBLE_HISTORY"],
                    warnings=[
                        "RESEARCH_ONLY",
                        "SIMILARITY_IS_NOT_PHYSIOLOGICAL_EQUIVALENCE",
                        "SYNTHETIC_EVALUATION_ONLY",
                    ],
                    audit_reference=correlation,
                )
        except DataError as exc:
            self.rejection(scope, correlation, exc.code)
            raise
        except GraphUnavailable:
            self.rejection(scope, correlation, "DATABASE_UNAVAILABLE")
            raise DataError(503, "MEMORY_GRAPH_UNAVAILABLE") from None
        except (SQLAlchemyError, ValueError, ValidationError):
            self.rejection(scope, correlation, "DATABASE_UNAVAILABLE")
            raise DataError(503, "MEMORY_RETRIEVAL_UNAVAILABLE") from None
