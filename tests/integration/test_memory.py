"""Actual PostgreSQL/pgvector/API tests plus optional actual Neo4j, synthetic only."""

import os
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from t1d_api.app import create_app
from t1d_api.auth import Principal, get_authenticator
from t1d_api.config import Settings
from t1d_api.contracts import Role
from t1d_api.data.errors import DataError
from t1d_api.data.schemas import CGMInput, MealInput
from t1d_api.db.models import AccessGrant, AuditEvent, ConsentRecord, DataSource
from t1d_api.db.session import authorize
from t1d_api.memory_service import MemoryService
from t1d_api.memory_store import canonical_events
from t1d_memory.contracts import RetrievalRequest
from t1d_memory.graph import GraphUnavailable, Neo4jIndex

from .conftest import Case

pytestmark = pytest.mark.integration
WHEN = datetime(2020, 1, 1, tzinfo=UTC)


def seed(case: Case, count: int = 3) -> list[UUID]:
    identities = []
    for n in range(count):
        when = WHEN + timedelta(hours=4 * n)
        nutrition = {
            "carbohydrate_g": "30",
            "protein_g": "5",
            "fat_g": "2",
            "energy_kcal": "158",
            "reference_ref": "synthetic-food",
            "method_version": "1",
            "uncertainty_status": "unknown",
        }
        meal = MealInput.model_validate(
            {
                "source_event_ref": f"memory-meal-{n}",
                "event_time": when,
                "provenance": {
                    "source_type": "synthetic",
                    "source_ref": "synthetic:fixture",
                    "source_version": "1",
                    "recorded_at": when,
                },
                "status": "confirmed",
                "nutrition": nutrition,
                "components": [
                    {
                        "food_label": "idli",
                        "food_reference_id": "food.idli",
                        "portion_value": "100",
                        "portion_unit": "g",
                        "status": "confirmed",
                        "nutrition": nutrition,
                    }
                ],
            }
        )
        receipt = case.service.ingest(
            case.scope, case.principal, "meal", [meal], f"memory-{n}", uuid4()
        )
        identities.append(UUID(receipt["meal_ids"][0]))
        readings = [
            CGMInput.model_validate(
                {
                    "source_event_ref": f"memory-cgm-{n}-{i}",
                    "event_time": when + timedelta(minutes=i * 5),
                    "provenance": {
                        "source_type": "synthetic",
                        "source_ref": "synthetic:fixture",
                        "source_version": "1",
                        "recorded_at": when + timedelta(minutes=i * 5),
                    },
                    "glucose_value": str(100 + i),
                    "glucose_unit": "mg/dL",
                    "sensor_status": "valid",
                    "device_ref": "synthetic-device",
                }
            )
            for i in range(25)
        ]
        case.service.ingest(case.scope, case.principal, "cgm", readings, f"memory-cgm-{n}", uuid4())
    return identities


@pytest.mark.parametrize("meals,expected_queries", [(1, 26), (24, 28)])
def test_memory_canonical_reads_are_batched(case: Case, meals: int, expected_queries: int) -> None:
    seed(case, meals)
    statements: list[str] = []

    def capture(
        connection: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        statements.append(statement)

    event.listen(case.database.engine, "before_cursor_execute", capture)
    try:
        with case.database.sessions.begin() as session:
            rows = canonical_events(session, case.scope, datetime.now(UTC))
        assert len(rows) == 26 * meals
        assert len(statements) == expected_queries
        assert sum(row.kind == "meal" for row in rows) == meals
        assert sum(row.kind == "cgm" for row in rows) == 25 * meals
        assert all(row.data["components"] for row in rows if row.kind == "meal")
    finally:
        event.remove(case.database.engine, "before_cursor_execute", capture)


def query(
    anchor: UUID, profile: str = "structured-v1", cutoff: datetime | None = None
) -> RetrievalRequest:
    return RetrievalRequest.model_validate(
        {
            "anchor_meal_id": anchor,
            "input_cutoff": cutoff or datetime.now(UTC),
            "retrieval_profile_version": profile,
            "limit": 5,
        }
    )


def test_memory_real_pgvector_ranking_and_idempotent_rebuild(case: Case) -> None:
    anchors = seed(case)
    service = MemoryService(case.database)
    first = service.rebuild(case.scope, case.principal, uuid4())
    assert first.inserted == 3 and first.graph_status == "not_configured"
    second = service.rebuild(case.scope, case.principal, uuid4())
    assert second.inserted == 0 and second.retained == 3
    results = [
        service.retrieve(case.scope, case.principal, query(anchors[-1], p), uuid4())
        for p in ("structured-v1", "vector-v1")
    ]
    assert all(len(r.episodes) == 2 for r in results)
    assert all(e.vector_similarity == pytest.approx(1) for e in results[1].episodes)
    assert all(e.anchor_meal_id != anchors[-1] for e in results[0].episodes)
    with Session(case.admin) as session:
        assert (
            len(
                list(
                    session.scalars(
                        select(AuditEvent).where(AuditEvent.action == "memory_retrieval")
                    )
                )
            )
            == 2
        )
    with pytest.raises(DataError) as unavailable:
        service.retrieve(case.scope, case.principal, query(anchors[-1], "hybrid-v1"), uuid4())
    assert unavailable.value.code == "MEMORY_GRAPH_UNAVAILABLE"


def test_memory_late_materialization_does_not_backdate(case: Case) -> None:
    anchors = seed(case)
    before = datetime.now(UTC)
    service = MemoryService(case.database)
    service.rebuild(case.scope, case.principal, uuid4())
    result = service.retrieve(
        case.scope, case.principal, query(anchors[-1], cutoff=before), uuid4()
    )
    assert result.status == "abstained" and result.episodes == []


def test_memory_correction_invalidates_stale_projection_before_rebuild(case: Case) -> None:
    anchors = seed(case)
    service = MemoryService(case.database)
    service.rebuild(case.scope, case.principal, uuid4())
    # Revise the first anchor into a draft: old snapshot must disappear immediately.
    draft = MealInput.model_validate(
        {
            "source_event_ref": "memory-meal-0",
            "event_time": WHEN,
            "provenance": {
                "source_type": "synthetic",
                "source_ref": "synthetic:fixture",
                "source_version": "1",
                "recorded_at": WHEN,
            },
            "revision": 2,
            "supersedes_id": anchors[0],
            "status": "draft",
            "components": [{"food_label": "idli"}],
        }
    )
    case.service.ingest(case.scope, case.principal, "meal", [draft], "memory-correction", uuid4())
    result = service.retrieve(case.scope, case.principal, query(anchors[-1]), uuid4())
    assert [e.anchor_meal_id for e in result.episodes] == [anchors[1]]
    assert service.rebuild(case.scope, case.principal, uuid4()).tombstoned == 1
    with pytest.raises(DBAPIError), case.database.sessions.begin() as session:
        authorize(session, case.scope, True)
        session.execute(text("UPDATE memory_episodes SET tombstoned=false WHERE tombstoned"))


def test_memory_source_withdrawal_invalidates_index(case: Case) -> None:
    anchors = seed(case)
    service = MemoryService(case.database)
    service.rebuild(case.scope, case.principal, uuid4())
    with Session(case.admin) as session, session.begin():
        session.execute(update(DataSource).values(approved=False))
    with pytest.raises(DataError) as unavailable:
        service.retrieve(case.scope, case.principal, query(anchors[-1]), uuid4())
    assert unavailable.value.status == 404


def test_memory_read_only_can_retrieve_but_not_rebuild(case: Case) -> None:
    anchors = seed(case)
    service = MemoryService(case.database)
    service.rebuild(case.scope, case.principal, uuid4())
    with Session(case.admin) as session, session.begin():
        session.execute(update(AccessGrant).values(can_write=False))
    assert (
        len(service.retrieve(case.scope, case.principal, query(anchors[-1]), uuid4()).episodes) == 2
    )
    with pytest.raises(DataError) as denied:
        service.rebuild(case.scope, case.principal, uuid4())
    assert denied.value.status == 404


def test_memory_future_cutoff_and_expired_principal(case: Case) -> None:
    service = MemoryService(case.database)
    with pytest.raises(DataError) as invalid:
        service.retrieve(
            case.scope,
            case.principal,
            query(uuid4(), cutoff=datetime.now(UTC) + timedelta(days=1)),
            uuid4(),
        )
    assert invalid.value.status == 422
    expired = case.principal.model_copy(update={"expires_at": WHEN})
    with pytest.raises(DataError) as denied:
        service.rebuild(case.scope, expired, uuid4())
    assert denied.value.status == 401


def test_memory_concurrent_rebuild_preserves_single_identity_set(case: Case) -> None:
    from concurrent.futures import ThreadPoolExecutor

    seed(case)
    service = MemoryService(case.database)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda _: service.rebuild(case.scope, case.principal, uuid4()), range(2))
        )
    assert sum(r.inserted for r in results) == 3
    with case.admin.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM memory_episodes")).scalar_one() == 3


@pytest.mark.parametrize("denial", ["grant", "consent", "role", "foreign"])
def test_memory_denial_and_no_foreign_scope_disclosure(case: Case, denial: str) -> None:
    anchors = seed(case)
    service = MemoryService(case.database)
    service.rebuild(case.scope, case.principal, uuid4())
    scope = case.scope
    if denial == "role":
        case.principal = case.principal.model_copy(update={"roles": frozenset({Role.PARTICIPANT})})
    elif denial == "foreign":
        scope = type(scope)(scope.actor_id, case.foreign_study, case.foreign_patient)
    else:
        with Session(case.admin) as session, session.begin():
            if denial == "grant":
                session.execute(update(AccessGrant).values(revoked=True))
            else:
                session.add(
                    ConsentRecord(
                        study_id=scope.study_id,
                        patient_id=scope.patient_id,
                        version=2,
                        status="revoked",
                        effective_at=datetime.now(UTC),
                        actor_id=scope.actor_id,
                        synthetic=True,
                    )
                )
    with pytest.raises(DataError) as denied:
        service.retrieve(scope, case.principal, query(anchors[-1]), uuid4())
    assert denied.value.status == 404


def test_memory_rls_and_immutable_manifest(case: Case) -> None:
    seed(case)
    MemoryService(case.database).rebuild(case.scope, case.principal, uuid4())
    with case.database.sessions.begin() as session:
        # No scoped session context: direct query cannot enumerate any patient.
        assert session.execute(text("SELECT count(*) FROM memory_episodes")).scalar_one() == 0
    with pytest.raises(DBAPIError), case.database.sessions.begin() as session:
        authorize(session, case.scope, True)
        session.execute(text("UPDATE memory_episodes SET manifest='{}'::jsonb"))


def test_memory_actual_api_scoped_and_redacted(case: Case) -> None:
    anchors = seed(case)

    class Auth:
        async def authenticate(self, request: object) -> Principal:
            return case.principal

    app = create_app(Settings(environment="test"), database=case.database)
    app.dependency_overrides[get_authenticator] = Auth
    base = f"/api/v1/patients/{case.scope.patient_id}"
    head = {"X-Study-ID": str(case.scope.study_id)}
    with TestClient(app) as client:
        assert client.post(base + "/memory/rebuild", headers=head, json={}).status_code == 200
        response = client.post(
            base + "/historical-retrievals",
            headers=head,
            json=query(anchors[-1], "vector-v1").model_dump(mode="json"),
        )
        assert response.status_code == 200 and len(response.json()["episodes"]) == 2
        assert response.json()["experimental"] is True
        invalid = client.post(
            base + "/historical-retrievals",
            headers=head,
            json={
                **query(anchors[-1]).model_dump(mode="json"),
                "limit": 10000,
                "private_marker": "do-not-echo-this",
            },
        )
        assert invalid.status_code == 422 and "do-not-echo-this" not in invalid.text


def test_memory_real_neo4j_projection_replay_isolation_and_outage(case: Case) -> None:
    uri = os.environ.get("T1D_TEST_NEO4J_URI")
    if not uri:
        pytest.skip("Run scripts/run_memory_tests.py for actual Neo4j qualification")
    graph = Neo4jIndex(uri, "neo4j", os.environ["T1D_TEST_NEO4J_PASSWORD"])
    try:
        anchors = seed(case)
        service = MemoryService(case.database, graph)
        assert service.rebuild(case.scope, case.principal, uuid4()).graph_status == "synchronized"
        assert service.rebuild(case.scope, case.principal, uuid4()).graph_status == "synchronized"
        result = service.retrieve(
            case.scope, case.principal, query(anchors[-1], "hybrid-v1"), uuid4()
        )
        assert len(result.episodes) == 2
        assert all(e.graph_similarity == pytest.approx(1) for e in result.episodes)
        with pytest.raises(GraphUnavailable):
            graph.similarities(
                case.foreign_study,
                case.foreign_patient,
                [str(result.episodes[0].episode_id)],
                ("food.idli",),
                datetime.now(UTC),
                service.rebuild(case.scope, case.principal, uuid4()).index_watermark,
            )
        graph.close()
        with pytest.raises(DataError) as outage:
            service.retrieve(case.scope, case.principal, query(anchors[-1], "hybrid-v1"), uuid4())
        assert outage.value.code == "MEMORY_GRAPH_UNAVAILABLE"
    finally:
        graph.close()
