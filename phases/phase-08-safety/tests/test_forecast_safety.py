"""Exercise the protected API and final forecast gate using controlled store fixtures."""

from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import cast
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from research_demo import fixture
from sqlalchemy.exc import SQLAlchemyError
from t1d_api import forecast_service
from t1d_api.app import create_app
from t1d_api.auth import Principal, get_authenticator
from t1d_api.config import Settings
from t1d_api.contracts import Role
from t1d_api.data.errors import DataError
from t1d_api.db.session import Database, Scope
from t1d_forecasting.contracts import HORIZONS, ForecastModel, ForecastPoint, Horizon
from t1d_forecasting.engine import Abstain, Snapshot, predict
from t1d_forecasting.safety import validate_forecast_points
from t1d_memory.synthetic import STUDY


@pytest.mark.parametrize("change", ("count", "horizon", "target_time", "infinite", "unordered"))
def test_final_gate_rechecks_untrusted_point_objects(change: str) -> None:
    cutoff = datetime(2020, 1, 1, tzinfo=UTC)
    points = [
        ForecastPoint(
            horizon_minutes=horizon,
            target_time=cutoff + timedelta(minutes=horizon),
            glucose_mg_dl=120.0,
            lower_mg_dl=100.0,
            upper_mg_dl=150.0,
        )
        for horizon in HORIZONS
    ]
    assert validate_forecast_points(points, cutoff, HORIZONS) == points
    if change == "count":
        points.pop()
    elif change == "horizon":
        points[0] = points[0].model_copy(update={"horizon_minutes": 60})
    elif change == "target_time":
        points[0] = points[0].model_copy(update={"target_time": cutoff})
    elif change == "infinite":
        points[0] = points[0].model_copy(update={"upper_mg_dl": float("inf")})
    else:
        points[0] = points[0].model_copy(update={"lower_mg_dl": 130.0})
    with pytest.raises(Abstain, match="INVALID_FORECAST_OUTPUT"):
        validate_forecast_points(points, cutoff, HORIZONS)


@pytest.mark.parametrize("failure", ("invalid-model", "changed-input", "audit", "revoked"))
def test_direct_api_and_retry_fail_closed(failure: str, monkeypatch: pytest.MonkeyPatch) -> None:
    data = fixture("cold")
    scope = Scope(UUID(int=888), STUDY, data.patient)
    principal = Principal(
        subject_id=scope.actor_id,
        roles=frozenset({Role.RESEARCHER}),
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )

    class Authenticator:
        async def authenticate(self, incoming: object) -> Principal:
            return principal

    app = create_app(
        Settings(environment="test"),
        database=cast(
            Database,
            SimpleNamespace(
                sessions=SimpleNamespace(begin=lambda: nullcontext(object())),
                check=lambda: True,
                close=lambda: None,
            ),
        ),
    )
    app.dependency_overrides[get_authenticator] = Authenticator
    state = {"failure": False, "reads": 0}

    def authorize(session: object, requested: Scope, write: bool) -> None:
        assert requested == scope and not write
        if state["failure"] and failure == "revoked":
            raise DataError(404, "RESOURCE_UNAVAILABLE")

    def canonical(session: object, requested: Scope, cutoff: datetime) -> object:
        assert requested == scope and cutoff == data.cutoff
        state["reads"] += 1
        readings = list(data.readings)
        if state["failure"] and failure == "changed-input" and state["reads"] == 2:
            readings[-1] = readings[-1].model_copy(update={"value": 999.0})
        return readings, True

    def audit(*args: object, **kwargs: object) -> None:
        if state["failure"] and failure == "audit":
            raise SQLAlchemyError("private-measurement-never-echo")

    monkeypatch.setattr(forecast_service, "authorize", authorize)
    monkeypatch.setattr(forecast_service, "canonical_cgm", canonical)
    monkeypatch.setattr(forecast_service, "audit", audit)
    monkeypatch.setattr(forecast_service, "failure_audit", lambda *args: None)
    if failure == "invalid-model":

        def invalid(
            snapshot: Snapshot, model: ForecastModel, horizons: tuple[Horizon, ...]
        ) -> list[ForecastPoint]:
            points = predict(snapshot, model, horizons)
            if state["failure"]:
                points[0] = points[0].model_copy(update={"target_time": data.cutoff})
            return points

        monkeypatch.setattr(forecast_service, "predict", invalid)

    with TestClient(app) as client:
        path = f"/api/v1/patients/{scope.patient_id}/forecasts"
        headers = {"X-Study-ID": str(scope.study_id)}
        query = {"input_cutoff": data.cutoff.isoformat()}
        prior = client.post(path, headers=headers, json=query)
        assert prior.status_code == 200 and prior.json()["status"] == "eligible"
        assert prior.headers["Cache-Control"] == "no-store"
        state.update(failure=True, reads=0)
        response = client.post(path, headers=headers, json=query)
        assert response.headers["Cache-Control"] == "no-store"
        assert "glucose_mg_dl" not in response.text
        assert "private-measurement-never-echo" not in response.text
        if failure == "invalid-model":
            assert response.status_code == 200
            assert response.json()["data"] is None
            assert response.json()["reason_codes"] == ["INVALID_FORECAST_OUTPUT"]
        elif failure == "revoked":
            assert response.status_code == 404
            assert state["reads"] == 0
        else:
            assert response.status_code == 503
        disabled = client.post(f"/api/v1/research/studies/{scope.study_id}/simulations", json={})
        assert disabled.status_code == 404
