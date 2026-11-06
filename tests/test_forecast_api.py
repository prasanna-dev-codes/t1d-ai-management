"""Default deny-all identity and unavailable database remain explicit."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
from t1d_api.app import create_app
from t1d_api.auth import Principal, get_authenticator
from t1d_api.config import Settings
from t1d_api.contracts import Role


def test_forecast_default_identity_denied() -> None:
    with TestClient(create_app(Settings(environment="test"))) as client:
        response = client.post(
            f"/api/v1/patients/{uuid4()}/forecasts",
            headers={"X-Study-ID": str(uuid4())},
            json={"input_cutoff": datetime.now(UTC).isoformat()},
        )
        assert response.status_code == 401


def test_forecast_missing_database_unavailable() -> None:
    class Auth:
        async def authenticate(self, incoming: object) -> Principal:
            return Principal(
                subject_id=uuid4(),
                roles=frozenset({Role.RESEARCHER}),
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )

    app = create_app(Settings(environment="test"))
    app.dependency_overrides[get_authenticator] = Auth
    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/patients/{uuid4()}/forecasts",
            headers={"X-Study-ID": str(uuid4())},
            json={"input_cutoff": datetime.now(UTC).isoformat()},
        )
        assert response.status_code == 503
