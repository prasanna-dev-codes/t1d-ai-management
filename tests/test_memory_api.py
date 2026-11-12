"""Transport and auth-denial checks; positive real-service tests are integration-only."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from t1d_api import memory_service
from t1d_api.app import create_app
from t1d_api.auth import Principal, get_authenticator
from t1d_api.config import Settings
from t1d_api.contracts import Role
from t1d_api.data.errors import DataError
from t1d_api.db.session import Scope
from t1d_memory.contracts import RetrievalRequest
from t1d_memory.episodes import build_episodes
from t1d_memory.synthetic import PATIENT, STUDY, cohort, meal


def test_memory_default_authentication_stays_closed() -> None:
    with TestClient(create_app(Settings(environment="test"))) as client:
        for path, body in (
            ("memory/rebuild", {}),
            (
                "historical-retrievals",
                {"input_cutoff": datetime.now(UTC).isoformat(), "anchor_meal_id": str(uuid4())},
            ),
        ):
            response = client.post(
                f"/api/v1/patients/{uuid4()}/{path}",
                headers={"X-Study-ID": str(uuid4())},
                json=body,
            )
            assert response.status_code == 401


def test_memory_authenticated_missing_database_is_unavailable() -> None:
    class Auth:
        async def authenticate(self, request: object) -> Principal:
            return Principal(
                subject_id=uuid4(),
                roles=frozenset({Role.RESEARCHER}),
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )

    app = create_app(Settings(environment="test"))
    app.dependency_overrides[get_authenticator] = Auth
    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/patients/{uuid4()}/memory/rebuild",
            headers={"X-Study-ID": str(uuid4())},
            json={},
        )
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "DATABASE_UNAVAILABLE"


@pytest.mark.parametrize(
    "uri",
    [
        "bolt://external.example:7687",
        "http://localhost:7474",
        "bolt://user:password@localhost:7687",
        "bolt://localhost:7687/path",
    ],
)
def test_memory_graph_configuration_stays_local(uri: str) -> None:
    with pytest.raises(ValidationError):
        Settings(memory_neo4j_uri=uri, memory_neo4j_user="test", memory_neo4j_password="test")  # type: ignore[arg-type]


@pytest.mark.parametrize("changed", [False, True])
def test_retrieval_rereads_canonical_history_and_rebuilds_on_change(
    monkeypatch: pytest.MonkeyPatch, changed: bool
) -> None:
    anchor = meal(4)
    events = [*cohort(4), anchor]
    stored, _ = build_episodes(events, anchor.event_time, STUDY, PATIENT)
    final = [anchor] if changed else [event.model_copy(deep=True) for event in events]
    reads = MagicMock(side_effect=[events, final])
    builds = MagicMock(wraps=build_episodes)
    auth = MagicMock()
    monkeypatch.setattr(memory_service, "canonical_events", reads)
    monkeypatch.setattr(memory_service, "build_episodes", builds)
    monkeypatch.setattr(memory_service, "authorize", auth)
    monkeypatch.setattr(memory_service, "load_episodes", MagicMock(return_value=(stored, None)))
    monkeypatch.setattr(memory_service, "audit", MagicMock())
    monkeypatch.setattr(memory_service, "failure_audit", MagicMock())
    actor = uuid4()
    principal = Principal(
        subject_id=actor,
        roles=frozenset({Role.RESEARCHER}),
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    service = memory_service.MemoryService(MagicMock())
    scope = Scope(actor, STUDY, PATIENT)
    query = RetrievalRequest(input_cutoff=anchor.event_time, anchor_meal_id=anchor.id)
    if changed:
        with pytest.raises(DataError) as exc:
            service.retrieve(scope, principal, query, uuid4())
        assert exc.value.code == "MEMORY_SNAPSHOT_CHANGED"
    else:
        assert service.retrieve(scope, principal, query, uuid4()).status == "evidence"
        assert auth.call_count == 2
    assert reads.call_count == 2
    assert builds.call_count == (2 if changed else 1)
