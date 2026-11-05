"""Transport and auth-denial checks; positive real-service tests are integration-only."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from t1d_api.app import create_app
from t1d_api.auth import Principal, get_authenticator
from t1d_api.config import Settings
from t1d_api.contracts import Role


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
