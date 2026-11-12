"""One synthetic workflow through the production HTTP routes with fixture-backed stores."""

from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import cast
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from research_demo import AuditEntry, Fixture, fixture, run
from t1d_api import forecast_service, memory_service
from t1d_api.app import create_app
from t1d_api.auth import Principal, get_authenticator
from t1d_api.config import Settings
from t1d_api.contracts import Role
from t1d_api.data.schemas import MealInput
from t1d_api.data.service import DataService
from t1d_api.db.session import Database, Scope
from t1d_forecasting.contracts import ForecastResult
from t1d_memory.contracts import Event, RetrievalResult
from t1d_memory.episodes import build_episodes, known_events
from t1d_memory.synthetic import STUDY


def test_meal_confirmation_memory_and_forecast_routes_feed_phase07(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = fixture("warm")
    scope = Scope(UUID(int=901), STUDY, data.patient)
    principal = Principal(
        subject_id=scope.actor_id,
        roles=frozenset({Role.RESEARCHER}),
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    events = [event for event in data.events if event.id != data.meal.id]
    draft = next(event for event in events if event.source_chain == data.meal.source_chain)
    episodes, _ = build_episodes(events, data.cutoff, STUDY, data.patient)

    class Authenticator:
        async def authenticate(self, request: object) -> Principal:
            return principal

    def check(session: object, request_scope: Scope, write: bool) -> None:
        assert request_scope == scope and not write

    def ingest(
        self: DataService,
        request_scope: Scope,
        actor: Principal,
        kind: str,
        items: list[MealInput],
        key: str,
        correlation: UUID,
    ) -> dict[str, object]:
        assert request_scope == scope and actor == principal and kind == "meal"
        assert key == "fixture:confirmation"
        assert len(items) == 1 and items[0].status == "confirmed"
        assert items[0].revision == 2 and items[0].supersedes_id == draft.id
        events.append(data.meal)
        return {
            "accepted": 1,
            "duplicates": 0,
            "received_at": data.cutoff,
            "warnings": [],
            "meal_ids": [data.meal.id],
        }

    monkeypatch.setattr(DataService, "ingest", ingest)
    monkeypatch.setattr(memory_service, "authorize", check)
    monkeypatch.setattr(forecast_service, "authorize", check)
    monkeypatch.setattr(
        memory_service,
        "canonical_events",
        lambda session, scope, at: known_events(events, at, scope.study_id, scope.patient_id),
    )
    monkeypatch.setattr(memory_service, "load_episodes", lambda session, scope, at: (episodes, at))
    monkeypatch.setattr(memory_service.MemoryService, "rejection", lambda *args: None)
    monkeypatch.setattr(
        forecast_service, "canonical_cgm", lambda *args: (list(data.readings), True)
    )
    monkeypatch.setattr(memory_service, "audit", lambda *args, **kwargs: None)
    monkeypatch.setattr(forecast_service, "audit", lambda *args, **kwargs: None)
    db = cast(
        Database,
        SimpleNamespace(
            sessions=SimpleNamespace(begin=lambda: nullcontext(object())),
            check=lambda: True,
            close=lambda: None,
        ),
    )
    app = create_app(Settings(environment="test"), database=db)
    app.dependency_overrides[get_authenticator] = Authenticator

    with TestClient(app) as client:
        root = f"/api/v1/patients/{scope.patient_id}"
        headers = {"X-Study-ID": str(STUDY)}
        cutoff = data.cutoff.isoformat()
        before = client.post(
            root + "/historical-retrievals",
            headers=headers,
            json={"input_cutoff": cutoff, "anchor_meal_id": str(draft.id)},
        )
        assert before.status_code == 422
        assert before.json()["error"]["code"] == "MEMORY_ANCHOR_UNCONFIRMED"
        nutrition = cast(list[dict[str, object]], data.meal.data["nutrition_records"])
        totals = {key: value for key, value in nutrition[0].items() if key != "scope"}
        receipt = client.post(
            root + "/meals",
            headers=headers | {"Idempotency-Key": "fixture:confirmation"},
            json={
                "meals": [
                    {
                        "source_event_ref": data.meal.source_chain,
                        "event_time": cutoff,
                        "revision": 2,
                        "supersedes_id": str(draft.id),
                        "status": "confirmed",
                        "components": data.meal.data["components"],
                        "nutrition": totals,
                        "provenance": {
                            "source_type": "synthetic",
                            "source_ref": "fixture:meal-review",
                            "source_version": "1",
                            "recorded_at": cutoff,
                        },
                    }
                ]
            },
        )
        assert receipt.status_code == 201, receipt.json()
        anchor_id = receipt.json()["meal_ids"][0]

        def memory(fixture_data: Fixture, anchor: Event) -> RetrievalResult:
            assert fixture_data.cutoff == data.cutoff and str(anchor.id) == anchor_id
            response = client.post(
                root + "/historical-retrievals",
                headers=headers,
                json={"input_cutoff": cutoff, "anchor_meal_id": anchor_id},
            )
            assert response.status_code == 200
            return RetrievalResult.model_validate(response.json())

        base = client.post(
            root + "/forecasts",
            headers=headers,
            json={"input_cutoff": cutoff, "model_profile": "ridge-v1"},
        )
        assert base.status_code == 200
        forecast = ForecastResult.model_validate(base.json())
        assert forecast.data is not None
        trail: list[AuditEntry] = []
        demo = run(data, memory, trail.append)
        assert demo.audit.outcome == "eligible" and trail == [demo.audit]
        assert demo.forecasts["phase06"] == forecast.data.points
        assert len(demo.evidence_refs) == 5 and len(demo.forecasts["phase07_with_memory"]) == 4
