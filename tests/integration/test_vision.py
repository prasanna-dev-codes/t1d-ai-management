"""Synthetic scoped API checks. Positive predictions are test-only provider fixtures."""

import threading
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session
from t1d_api.app import create_app
from t1d_api.auth import Principal, get_authenticator
from t1d_api.config import Settings
from t1d_api.contracts import Role
from t1d_api.db.models import AccessGrant, AuditEvent, ConsentRecord, Meal
from t1d_vision.contracts import (
    Candidate,
    ImageQuality,
    ModelInfo,
    Task,
    VisionAvailability,
    VisionResult,
)
from t1d_vision.images import MAX_BYTES

from .conftest import Case


class TestOnlyProvider:
    __test__ = False

    def __init__(self, callback: Callable[[], None] | None = None) -> None:
        self.calls = 0
        self.callback = callback
        self.model = ModelInfo(
            model_id=uuid4(),
            version="test-only",
            taxonomy_version="test",
            preprocessing_version="rgb-letterbox224-v1",
            dataset_version="authored-synthetic",
            calibration_status="temperature_scaled",
        )

    def status(self) -> VisionAvailability:
        return VisionAvailability(
            available=True,
            supported_tasks=["single_label_classification"],
            model=self.model,
            reason_code="MODEL_READY",
        )

    def analyze(
        self, data: bytes, mime: str, task: Task, cancel: threading.Event | None = None
    ) -> VisionResult:
        self.calls += 1
        if self.callback:
            self.callback()
        return VisionResult(
            prediction_id=uuid4(),
            status="review_required",
            task="single_label_classification",
            model=self.model,
            image_quality=ImageQuality(status="accepted", width=64, height=64, warnings=[]),
            candidates=[Candidate(canonical_id="food.test_only", label="Test fixture", score=0.9)],
            reason_codes=["HUMAN_REVIEW_REQUIRED"],
            processing_ms=1,
            completed_at=datetime.now(UTC),
        )


def app_for(case: Case, provider: TestOnlyProvider | None = None) -> FastAPI:
    class Auth:
        async def authenticate(self, request: object) -> Principal:
            return case.principal

    app = create_app(Settings(environment="test"), database=case.database, vision_provider=provider)
    app.dependency_overrides[get_authenticator] = Auth
    return app


def headers(case: Case) -> dict[str, str]:
    return {"X-Study-ID": str(case.scope.study_id), "Content-Type": "image/png"}


def base(case: Case) -> str:
    return f"/api/v1/patients/{case.scope.patient_id}/vision"


def test_vision_default_no_artifact_and_no_clinical_persistence(case: Case) -> None:
    with TestClient(app_for(case)) as client:
        response = client.get(base(case) + "/model", headers=headers(case))
        assert response.status_code == 200 and response.json()["available"] is False
        failed = client.post(
            base(case) + "/analyses", headers=headers(case), content=b"authored-test-only"
        )
        assert failed.status_code == 503 and failed.json()["error"]["code"] == "MODEL_UNAVAILABLE"
    with Session(case.admin) as session:
        assert session.scalar(select(func.count()).select_from(Meal)) == 0
        audits = list(
            session.scalars(select(AuditEvent).where(AuditEvent.resource_type == "vision"))
        )
        assert {a.action for a in audits} == {"vision_model_status", "vision_rejected"}
        assert all("authored-test-only" not in str(a.reason_code) for a in audits)


def test_vision_test_only_authenticated_success_and_safe_audit(case: Case) -> None:
    provider = TestOnlyProvider()
    with TestClient(app_for(case, provider)) as client:
        response = client.post(
            base(case) + "/analyses",
            headers=headers(case),
            content=b"synthetic-private-image-marker",
        )
        assert response.status_code == 200 and response.json()["review_required"] is True
        assert provider.calls == 1
    with Session(case.admin) as session:
        audit = session.scalar(select(AuditEvent).where(AuditEvent.action == "vision_analysis"))
        assert audit is not None and audit.resource_id is not None
        assert audit.reason_code == "HUMAN_REVIEW_REQUIRED" and audit.source_ref == str(
            provider.model.model_id
        )
        assert session.scalar(select(func.count()).select_from(Meal)) == 0


@pytest.mark.parametrize(
    "denial", ["foreign_patient", "foreign_study", "grant", "consent", "read_only", "role"]
)
def test_vision_scope_denial_precedes_inference(case: Case, denial: str) -> None:
    provider = TestOnlyProvider()
    url = base(case) + "/analyses"
    head = headers(case)
    if denial == "foreign_patient":
        url = f"/api/v1/patients/{case.foreign_patient}/vision/analyses"
    elif denial == "foreign_study":
        head["X-Study-ID"] = str(case.foreign_study)
    elif denial == "role":
        case.principal = case.principal.model_copy(update={"roles": frozenset({Role.PARTICIPANT})})
    else:
        with Session(case.admin) as session, session.begin():
            if denial == "grant":
                session.execute(update(AccessGrant).values(revoked=True))
            elif denial == "read_only":
                session.execute(update(AccessGrant).values(can_write=False))
            else:
                session.add(
                    ConsentRecord(
                        patient_id=case.scope.patient_id,
                        study_id=case.scope.study_id,
                        version=2,
                        status="revoked",
                        effective_at=datetime.now(UTC),
                        actor_id=case.scope.actor_id,
                        synthetic=True,
                    )
                )
    with TestClient(app_for(case, provider)) as client:
        assert client.post(url, headers=head, content=b"test").status_code == 404
    assert provider.calls == 0


def test_vision_revocation_during_processing_discards_result(case: Case) -> None:
    def revoke() -> None:
        with Session(case.admin) as session, session.begin():
            session.execute(update(AccessGrant).values(revoked=True))

    provider = TestOnlyProvider(revoke)
    with TestClient(app_for(case, provider)) as client:
        response = client.post(base(case) + "/analyses", headers=headers(case), content=b"test")
        assert response.status_code == 404 and "Test fixture" not in response.text
    with Session(case.admin) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.action == "vision_analysis")
            )
            == 0
        )


def test_vision_upload_and_busy_limits_precede_provider(case: Case) -> None:
    provider = TestOnlyProvider()
    app = app_for(case, provider)
    with TestClient(app) as client:
        assert (
            client.post(
                base(case) + "/analyses",
                headers={**headers(case), "Content-Length": str(MAX_BYTES + 1)},
                content=b"test",
            ).status_code
            == 413
        )
        assert (
            client.post(
                base(case) + "/analyses",
                headers={**headers(case), "Content-Type": "text/plain"},
                content=b"test",
            ).status_code
            == 415
        )
        assert (
            client.post(base(case) + "/analyses", headers=headers(case), content=b"").status_code
            == 422
        )
        oversized = client.post(
            base(case) + "/analyses",
            headers=headers(case),
            content=(b"x" * 1024**2 for _ in range(9)),
        )
        assert oversized.status_code == 413
        assert app.state.vision_admission.acquire(blocking=False)
        try:
            assert (
                client.post(
                    base(case) + "/analyses", headers=headers(case), content=b"test"
                ).status_code
                == 503
            )
        finally:
            app.state.vision_admission.release()
    assert provider.calls == 0


def test_vision_default_auth_remains_deny_all(case: Case) -> None:
    provider = TestOnlyProvider()
    app = create_app(Settings(environment="test"), database=case.database, vision_provider=provider)
    with TestClient(app) as client:
        assert client.get(base(case) + "/model", headers=headers(case)).status_code == 401
        assert (
            client.post(
                base(case) + "/analyses",
                headers={**headers(case), "Authorization": "Bearer synthetic-invalid"},
                content=b"test",
            ).status_code
            == 401
        )
    assert provider.calls == 0
