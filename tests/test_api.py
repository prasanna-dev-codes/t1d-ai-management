"""Synthetic engineering fixtures only; no patient data or clinical behavior."""

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from io import StringIO
from uuid import UUID

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel, ValidationError
from t1d_api.app import create_app
from t1d_api.auth import Principal, get_authenticator
from t1d_api.config import Settings
from t1d_api.contracts import ErrorResponse, Role
from t1d_api.observability import SafeJsonFormatter
from t1d_api.readiness import Runtime

REQUEST_ID = "00000000-0000-4000-8000-000000000001"


def test_lifecycle_and_public_contracts() -> None:
    state = Runtime()
    app = create_app(Settings(environment="test"), state)
    assert not state.started
    with TestClient(app) as client:
        assert state.started
        assert client.get("/api/v1/health/live").json() == {"status": "alive"}
        assert client.get("/api/v1/health/ready").json() == {"status": "ready"}
        assert client.get("/health/live").status_code == 404
    assert not state.started
    with TestClient(app) as client:
        assert client.get("/api/v1/health/ready").status_code == 200


@pytest.mark.parametrize("mode", ["false", "error", "timeout"])
def test_dependency_failure_is_redacted_and_does_not_break_liveness(mode: str) -> None:
    async def probe() -> bool:
        if mode == "error":
            raise RuntimeError("synthetic-private-dependency-password")
        if mode == "timeout":
            await asyncio.sleep(0.1)
        return False

    settings = Settings(environment="test", readiness_timeout_seconds=0.01)
    with TestClient(create_app(settings, Runtime(probes=(probe,)))) as client:
        result = client.get("/api/v1/health/ready")
        assert result.status_code == 503
        body = ErrorResponse.model_validate(result.json())
        assert body.error.code == "NOT_READY"
        assert "password" not in result.text
        assert "dependency" not in result.text
        assert client.get("/api/v1/health/live").status_code == 200


def test_successful_probe_and_unstarted_readiness() -> None:
    async def probe() -> bool:
        return True

    runtime = Runtime(probes=(probe,))
    assert not asyncio.run(runtime.is_ready(1))
    with TestClient(create_app(Settings(environment="test"), runtime)) as client:
        assert client.get("/api/v1/health/ready").status_code == 200


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer synthetic-untrusted-token"}])
def test_authentication_fails_closed(headers: dict[str, str]) -> None:
    with TestClient(create_app(Settings(environment="test"))) as client:
        result = client.get("/api/v1/auth/session", headers=headers)
        assert result.status_code == 401
        assert result.headers["WWW-Authenticate"] == "Bearer"
        assert result.json()["error"]["code"] == "UNAUTHENTICATED"
        assert "synthetic-untrusted-token" not in result.text


def test_authenticator_interface_is_replaceable_only_in_tests() -> None:
    class SyntheticAuthenticator:
        async def authenticate(self, request: object) -> Principal:
            return Principal(
                subject_id=UUID(REQUEST_ID),
                roles=frozenset({Role.RESEARCHER}),
                expires_at=datetime.now(UTC) + timedelta(minutes=5),
            )

    app = create_app(Settings(environment="test"))
    app.dependency_overrides[get_authenticator] = SyntheticAuthenticator
    with TestClient(app) as client:
        result = client.get("/api/v1/auth/session")
        assert result.status_code == 200
        assert result.json()["roles"] == ["researcher"]
    assert "SyntheticAuthenticator" not in str(app.openapi())
    assert "synthetic-untrusted-token" not in str(app.openapi())


def test_expired_principal_is_rejected() -> None:
    class ExpiredAuthenticator:
        async def authenticate(self, request: object) -> Principal:
            return Principal(
                subject_id=UUID(REQUEST_ID),
                roles=frozenset(),
                expires_at=datetime(2000, 1, 1, tzinfo=UTC),
            )

    app = create_app(Settings(environment="test"))
    app.dependency_overrides[get_authenticator] = ExpiredAuthenticator
    with TestClient(app) as client:
        assert client.get("/api/v1/auth/session").status_code == 401


@pytest.mark.parametrize("incoming", [REQUEST_ID, "malformed-private-input", "x" * 1000])
def test_request_id_on_success_and_errors(incoming: str) -> None:
    with TestClient(create_app(Settings(environment="test"))) as client:
        for path in ["/api/v1/health/live", "/api/v1/auth/session", "/missing"]:
            result = client.get(path, headers={"X-Request-ID": incoming})
            value = result.headers["X-Request-ID"]
            assert UUID(value).version == 4
            if incoming == REQUEST_ID:
                assert value == incoming
            if result.status_code >= 400:
                assert result.json()["error"]["correlation_id"] == value
            assert result.headers["Cache-Control"] == "no-store"


def test_cors_exact_origins_and_preflight() -> None:
    with TestClient(create_app(Settings(environment="test"))) as client:
        for origin, allowed in [
            ("http://localhost:3000", True),
            ("https://untrusted.example", False),
            ("http://localhost:3000.evil.example", False),
        ]:
            result = client.get("/api/v1/health/live", headers={"Origin": origin})
            assert (result.headers.get("Access-Control-Allow-Origin") == origin) is allowed
            preflight = client.options(
                "/api/v1/health/live",
                headers={
                    "Origin": origin,
                    "Access-Control-Request-Method": "GET",
                    "Access-Control-Request-Headers": "X-Request-ID",
                },
            )
            assert preflight.status_code == (200 if allowed else 400)
        assert (
            client.options(
                "/api/v1/health/live",
                headers={
                    "Origin": "http://localhost:3000",
                    "Access-Control-Request-Method": "DELETE",
                },
            ).status_code
            == 400
        )


def test_exception_and_validation_errors_never_echo_inputs() -> None:
    app = create_app(Settings(environment="test"))

    @app.get("/test-crash")
    async def crash() -> None:
        raise RuntimeError("synthetic-private-value")

    @app.get("/test-http")
    async def http_failure() -> None:
        raise HTTPException(status_code=403, detail="synthetic-private-value")

    class TestPayload(BaseModel):
        count: int

    @app.post("/test-validation")
    async def validate(payload: TestPayload) -> None:
        return None

    with TestClient(app, raise_server_exceptions=False) as client:
        for method, path, code in [
            ("GET", "/test-crash", 500),
            ("GET", "/test-http", 403),
            ("POST", "/test-validation", 422),
        ]:
            result = client.request(
                method,
                path,
                json={"count": "synthetic-private-value"},
                headers={"Origin": "http://localhost:3000"},
            )
            assert result.status_code == code
            assert "synthetic-private-value" not in result.text
            ErrorResponse.model_validate(result.json())
            assert result.headers["X-Request-ID"]
            assert result.headers["Access-Control-Allow-Origin"] == "http://localhost:3000"


@pytest.mark.parametrize(
    "values",
    [
        {"api_port": 0},
        {"api_port": 65536},
        {"api_host": "0.0.0.0"},
        {"readiness_timeout_seconds": 0},
        {"environment": "production"},
        {"cors_origins": ["*"]},
        {"cors_origins": ["http://localhost:3000/path"]},
        {"cors_origins": ["http://user:password@localhost:3000"]},
        {"cors_origins": ["https://public.example"]},
        {"unknown_setting": True},
    ],
)
def test_invalid_configuration(values: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Settings(**values)  # type: ignore[arg-type]


def test_configuration_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("T1D_API_PORT", "8002")
    monkeypatch.setenv("T1D_CORS_ORIGINS", '["http://127.0.0.1:3001"]')
    assert Settings().api_port == 8002
    assert Settings().cors_origins == ["http://127.0.0.1:3001"]
    monkeypatch.setenv("T1D_API_PORT", "invalid")
    with pytest.raises(ValidationError):
        Settings()


def test_log_formatter_is_allowlisted() -> None:
    record = logging.LogRecord("test", logging.ERROR, "", 1, "synthetic-private-token", (), None)
    record.correlation_id = REQUEST_ID
    record.status_code = 500
    record.secret = "synthetic-private-password"
    output = SafeJsonFormatter().format(record)
    assert "private" not in output
    assert "secret" not in output
    assert json.loads(output)["correlation_id"] == REQUEST_ID


def test_no_future_phase_routes_or_test_bypass() -> None:
    app = create_app()
    assert set(app.openapi()["paths"]) == {
        "/api/v1/patients/{patient_id}/memory/rebuild",
        "/api/v1/patients/{patient_id}/historical-retrievals",
        "/api/v1/patients/{patient_id}/forecasts",
        "/api/v1/health/live",
        "/api/v1/health/ready",
        "/api/v1/auth/session",
        "/api/v1/patients/{patient_id}/cgm-readings",
        "/api/v1/patients/{patient_id}/meals",
        "/api/v1/patients/{patient_id}/insulin-events",
        "/api/v1/patients/{patient_id}/activity-events",
        "/api/v1/patients/{patient_id}/audit-events",
        "/api/v1/patients/{patient_id}/vision/model",
        "/api/v1/patients/{patient_id}/vision/analyses",
    }
    with TestClient(create_app(Settings(environment="test"))) as client:
        assert client.get("/docs").status_code == 404
        assert client.get("/openapi.json").status_code == 404


def test_operational_logs_omit_path_query_headers_and_body(monkeypatch: pytest.MonkeyPatch) -> None:
    import t1d_api.app as app_module

    sink = StringIO()
    logger = logging.Logger("synthetic-log-test")
    handler = logging.StreamHandler(sink)
    handler.setFormatter(SafeJsonFormatter())
    logger.addHandler(handler)
    monkeypatch.setattr(app_module, "request_logger", lambda: logger)
    with TestClient(create_app(Settings(environment="test"))) as client:
        result = client.post(
            "/synthetic-private-path?token=synthetic-private-query",
            headers={"Authorization": "Bearer synthetic-private-token"},
            json={"value": "synthetic-private-body"},
        )
        assert result.status_code == 404
    assert "synthetic-private" not in sink.getvalue()
    event = json.loads(sink.getvalue())
    assert event["status_code"] == 404
    assert event["event"] == "request_completed"


def test_rejected_cors_uses_standard_error_envelope() -> None:
    with TestClient(create_app(Settings(environment="test"))) as client:
        result = client.options(
            "/api/v1/health/live",
            headers={
                "Origin": "https://untrusted.example",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert result.status_code == 400
        assert ErrorResponse.model_validate(result.json()).error.code == "CORS_REJECTED"
        assert "Access-Control-Allow-Origin" not in result.headers
