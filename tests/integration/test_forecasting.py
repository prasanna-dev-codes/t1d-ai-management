"""Real PostgreSQL authorization, revisions, availability and forecast API checks."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from t1d_api.app import create_app
from t1d_api.auth import Principal, get_authenticator
from t1d_api.config import Settings
from t1d_api.contracts import Role
from t1d_api.data.errors import DataError
from t1d_api.data.schemas import CGMInput
from t1d_api.db.models import AccessGrant, AuditEvent, DataSource
from t1d_api.forecast_service import ForecastService
from t1d_forecasting.contracts import ForecastRequest

from .conftest import Case

pytestmark = pytest.mark.integration


def seed(case: Case) -> tuple[list[CGMInput], list[UUID]]:
    latest = datetime.now(UTC) - timedelta(seconds=10)
    rows = [
        CGMInput.model_validate(
            {
                "source_event_ref": f"forecast-{i}",
                "event_time": latest - timedelta(minutes=5 * (11 - i)),
                "provenance": {
                    "source_type": "synthetic",
                    "source_ref": "synthetic:fixture",
                    "source_version": "1",
                    "recorded_at": latest,
                },
                "glucose_value": str(140 + i),
                "glucose_unit": "mg/dL",
                "sensor_status": "valid",
                "device_ref": "fictional-device",
            }
        )
        for i in range(12)
    ]
    receipt = case.service.ingest(case.scope, case.principal, "cgm", rows, "forecast-seed", uuid4())
    return rows, [UUID(i) for i in receipt["reading_ids"]]


def request() -> ForecastRequest:
    return ForecastRequest(input_cutoff=datetime.now(UTC))


def test_forecast_models_positive_api_and_audit(case: Case) -> None:
    seed(case)
    service = ForecastService(case.database)
    for profile in ("persistence-v1", "linear-v1", "ridge-v1"):
        query = ForecastRequest.model_validate(
            {"input_cutoff": datetime.now(UTC), "model_profile": profile}
        )
        result = service.forecast(case.scope, case.principal, query, uuid4())
        assert result.status == "eligible" and result.data is not None, result.reason_codes
        assert "SOURCE_RECORDING_WARNINGS_PRESERVED" in result.warnings
        assert len(result.data.points) == 4 and len(result.data.source_revision_refs) == 12
        assert len(result.data.input_snapshot_ref) == 64
        assert result.data.evidence_refs == []
    with Session(case.admin) as session:
        assert (
            len(
                list(
                    session.scalars(
                        select(AuditEvent).where(AuditEvent.resource_type == "forecast")
                    )
                )
            )
            == 3
        )

    class Auth:
        async def authenticate(self, incoming: object) -> Principal:
            return case.principal

    app = create_app(Settings(environment="test"), database=case.database)
    app.dependency_overrides[get_authenticator] = Auth
    with TestClient(app) as client:
        path = f"/api/v1/patients/{case.scope.patient_id}/forecasts"
        headers = {"X-Study-ID": str(case.scope.study_id)}
        response = client.post(path, headers=headers, json=request().model_dump(mode="json"))
        assert response.status_code == 200 and response.json()["status"] == "eligible"
        assert response.json()["review_required"] is True
        assert "dose" not in response.text.lower()
        invalid = client.post(
            path,
            headers=headers,
            json={
                **request().model_dump(mode="json"),
                "patient_secret": "never-echo-this",
            },
        )
        assert invalid.status_code == 422 and "never-echo-this" not in invalid.text


def test_forecast_cutoff_missing_and_stale_abstention(case: Case) -> None:
    service = ForecastService(case.database)
    assert service.forecast(case.scope, case.principal, request(), uuid4()).reason_codes == [
        "NO_CGM_HISTORY"
    ]
    before = datetime.now(UTC)
    rows, _ = seed(case)
    historical = service.forecast(
        case.scope, case.principal, ForecastRequest(input_cutoff=before), uuid4()
    )
    assert historical.data is None and historical.status == "abstained"
    # Last observation cannot be used as if it was measured at this later cutoff.
    query = ForecastRequest(input_cutoff=datetime.now(UTC))
    with pytest.raises(DataError) as future:
        service.forecast(
            case.scope,
            case.principal,
            query.model_copy(update={"input_cutoff": datetime.now(UTC) + timedelta(minutes=1)}),
            uuid4(),
        )
    assert future.value.status == 422
    assert rows[-1].glucose_value is not None


def test_forecast_correction_with_missing_sensor_never_resurrects(case: Case) -> None:
    rows, ids = seed(case)
    correction = rows[-1].model_copy(
        update={
            "revision": 2,
            "supersedes_id": ids[-1],
            "glucose_value": None,
            "sensor_status": "missing",
        }
    )
    case.service.ingest(
        case.scope, case.principal, "cgm", [correction], "missing-correction", uuid4()
    )
    result = ForecastService(case.database).forecast(case.scope, case.principal, request(), uuid4())
    assert result.status == "abstained" and result.data is None
    assert result.reason_codes[0] in {"CGM_QUALITY_UNRESOLVED", "MISSING_CGM_VALUE"}


@pytest.mark.parametrize("change", ["withdraw", "nonsynthetic"])
def test_forecast_source_governance(case: Case, change: str) -> None:
    seed(case)
    with Session(case.admin) as session, session.begin():
        session.execute(
            update(DataSource)
            .where(DataSource.source_ref == "synthetic:fixture")
            .values(**({"approved": False} if change == "withdraw" else {"source_type": "device"}))
        )
    result = ForecastService(case.database).forecast(case.scope, case.principal, request(), uuid4())
    assert result.status == "abstained" and result.data is None
    assert result.reason_codes == (
        ["SOURCE_APPROVAL_WITHDRAWN"]
        if change == "withdraw"
        else ["MODEL_NOT_QUALIFIED_FOR_NONSYNTHETIC_DATA"]
    )


@pytest.mark.parametrize("denial", ["role", "foreign", "grant", "expired"])
def test_forecast_access_denial(case: Case, denial: str) -> None:
    seed(case)
    scope, principal = case.scope, case.principal
    if denial == "role":
        principal = principal.model_copy(update={"roles": frozenset({Role.PARTICIPANT})})
    elif denial == "foreign":
        scope = type(scope)(scope.actor_id, case.foreign_study, case.foreign_patient)
    elif denial == "expired":
        principal = principal.model_copy(
            update={"expires_at": datetime.now(UTC) - timedelta(seconds=1)}
        )
    else:
        with Session(case.admin) as session, session.begin():
            session.execute(update(AccessGrant).values(revoked=True))
    with pytest.raises(DataError) as error:
        ForecastService(case.database).forecast(scope, principal, request(), uuid4())
    assert error.value.status == (401 if denial == "expired" else 404)
