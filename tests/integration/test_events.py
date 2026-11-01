"""Synthetic persistence, temporal, security, migration and API regressions."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from t1d_api.app import create_app
from t1d_api.auth import Principal, get_authenticator
from t1d_api.config import Settings
from t1d_api.data.errors import DataError
from t1d_api.data.schemas import ActivityInput, CGMInput, InsulinInput, Kind, MealInput
from t1d_api.data.service import Payload
from t1d_api.db.models import (
    AccessGrant,
    AuditEvent,
    ConsentRecord,
    EventRevision,
    Meal,
    NutritionRecord,
    OutboxEvent,
)
from t1d_api.db.session import Database, Scope, authorize

from .conftest import Case

pytestmark = pytest.mark.integration


def cgm(ref: str = "reading-1", **changes: object) -> CGMInput:
    value: dict[str, Any] = {
        "source_event_ref": ref,
        "event_time": "2020-01-01T00:00:00+05:30",
        "provenance": {
            "source_type": "synthetic",
            "source_ref": "synthetic:fixture",
            "source_version": "1",
            "recorded_at": "2020-01-02T00:00:00Z",
        },
        "glucose_value": "110.123456789012",
        "glucose_unit": "mg/dL",
        "device_ref": "synthetic-device",
        "sensor_status": "valid",
    }
    value.update(changes)
    return CGMInput.model_validate(value)


def ingest(case: Case, item: CGMInput | None = None, key: str = "idempotency-a") -> dict[str, Any]:
    return case.service.ingest(case.scope, case.principal, "cgm", [item or cgm()], key, uuid4())


def count(case: Case, model: type[EventRevision] | type[AuditEvent] | type[OutboxEvent]) -> int:
    with Session(case.admin) as session:
        return session.scalar(select(func.count()).select_from(model)) or 0


def test_extensions_hypertable_role_and_migration_idempotence(case: Case) -> None:
    assert case.database.check()
    command.upgrade(Config("alembic.ini"), "head")
    with case.admin.connect() as connection:
        assert (
            connection.execute(
                text(
                    "SELECT count(*) FROM timescaledb_information.hypertables WHERE "
                    "hypertable_name='cgm_readings'"
                )
            ).scalar_one()
            == 1
        )
        assert connection.execute(text("SELECT vector_dims('[1,0]'::vector)")).scalar_one() == 2
        assert (
            connection.execute(
                text("SELECT rolbypassrls OR rolsuper FROM pg_roles WHERE rolname='t1d_runtime'")
            ).scalar_one()
            is False
        )
        assert (
            connection.execute(
                text("SELECT count(*) FROM pg_indexes WHERE schemaname='public'")
            ).scalar_one()
            > 15
        )
    unsafe = Database(case.migration_url)
    with pytest.raises(DataError):
        unsafe.check()
    unsafe.close()


def test_exact_cgm_idempotency_conflicts_and_audit(case: Case) -> None:
    first = ingest(case)
    assert first["accepted"] == 1
    assert ingest(case) == first
    duplicate = ingest(case, key="new-key")
    assert duplicate["duplicates"] == 1
    with pytest.raises(DataError) as conflict:
        ingest(case, cgm(glucose_value="111"))
    assert conflict.value.code == "IDEMPOTENCY_CONFLICT"
    with pytest.raises(DataError):
        ingest(case, cgm(glucose_value="111"), key="changed")
    assert count(case, EventRevision) == 1
    assert count(case, OutboxEvent) == 1
    assert count(case, AuditEvent) >= 5
    with case.admin.connect() as connection:
        assert connection.execute(
            text("SELECT glucose_value FROM cgm_readings")
        ).scalar_one() == Decimal("110.123456789012")
        assert connection.execute(
            text("SELECT glucose_mmol_l FROM cgm_readings")
        ).scalar_one() == Decimal("110.123456789012") * Decimal(".0555")
        assert (
            connection.execute(text("SELECT original_offset FROM event_revisions")).scalar_one()
            == "5:30:00"
        )


def test_atomic_rollback_and_durable_rejection(case: Case) -> None:
    with pytest.raises(DataError):
        case.service.ingest(
            case.scope,
            case.principal,
            "cgm",
            [cgm(), cgm("second", event_time=datetime.now(UTC) + timedelta(days=1))],
            "atomic",
            uuid4(),
        )
    assert count(case, EventRevision) == 0
    with case.admin.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM ingestion_batches")).scalar_one() == 0
        assert (
            connection.execute(
                text("SELECT count(*) FROM audit_events WHERE outcome='rejected'")
            ).scalar_one()
            == 1
        )


def test_concurrent_duplicate_ingestion(case: Case) -> None:
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: ingest(case), range(4)))
    assert all(result == results[0] for result in results)
    assert count(case, EventRevision) == 1


def test_temporal_correction_and_delayed_arrival(case: Case) -> None:
    result = ingest(case)
    with case.admin.connect() as connection:
        cutoff = connection.execute(text("SELECT available_at FROM event_revisions")).scalar_one()
    first_id = UUID(result["reading_ids"][0])
    # A correction received later must not alter a previously known revision.
    corrected = cgm(glucose_value="120", revision=2, supersedes_id=first_id)
    ingest(case, corrected, "correction")
    late = cgm("late")
    ingest(case, late, "late")
    historical = case.service.history(case.scope, "cgm", cutoff, 100, None, uuid4())
    assert len(historical["records"]) == 1
    assert historical["records"][0]["revision"] == 1
    current = case.service.history(case.scope, "cgm", datetime.now(UTC), 100, None, uuid4())
    assert len(current["records"]) == 2
    assert sorted(row["revision"] for row in current["records"]) == [1, 2]
    assert not case.service.history(
        case.scope, "cgm", datetime(2019, 1, 1, tzinfo=UTC), 100, None, uuid4()
    )["records"]


def test_revised_event_time_and_separate_quarantined_chain(case: Case) -> None:
    result = ingest(case)
    first_id = UUID(result["reading_ids"][0])
    # A correction changes event time; latest history must retain the new event time.
    second = cgm(
        revision=2,
        supersedes_id=first_id,
        event_time="2021-01-01T00:00:00Z",
        provenance={
            "source_type": "synthetic",
            "source_ref": "synthetic:fixture",
            "source_version": "1",
            "recorded_at": "2021-01-02T00:00:00Z",
        },
    )
    ingest(case, second, "second")
    with case.admin.connect() as connection:
        cutoff = connection.execute(
            text("SELECT max(available_at) FROM event_revisions")
        ).scalar_one()
    assert (
        case.service.history(case.scope, "cgm", cutoff, 100, None, uuid4())["records"][0][
            "revision"
        ]
        == 2
    )
    # A model-derived chain is quarantined and never appears as eligible history.
    model = cgm(
        "model",
        provenance={
            "source_type": "model",
            "source_ref": "synthetic:model",
            "source_version": "1",
            "recorded_at": "2020-01-02T00:00:00Z",
        },
    )
    ingest(case, model, "model")
    assert (
        len(
            case.service.history(case.scope, "cgm", datetime.now(UTC), 100, None, uuid4())[
                "records"
            ]
        )
        == 1
    )


@pytest.mark.parametrize(
    "bad",
    [
        "actor",
        "patient",
        "study",
        "revoked",
        "consent",
        "read_only",
        "expired_grant",
        "expired_consent",
        "suspended",
    ],
)
def test_patient_scope_and_revocation(case: Case, bad: str) -> None:
    scope = case.scope
    if bad == "actor":
        scope = Scope(uuid4(), scope.study_id, scope.patient_id)
    if bad == "patient":
        scope = Scope(scope.actor_id, scope.study_id, case.foreign_patient)
    if bad == "study":
        scope = Scope(scope.actor_id, case.foreign_study, scope.patient_id)
    with Session(case.admin) as session, session.begin():
        if bad == "suspended":
            session.execute(
                text("UPDATE patients SET status='suspended' WHERE id=:id"),
                {"id": scope.patient_id},
            )
        if bad == "expired_consent":
            session.add(
                ConsentRecord(
                    study_id=scope.study_id,
                    patient_id=scope.patient_id,
                    version=2,
                    status="granted",
                    effective_at=datetime(2020, 1, 1, tzinfo=UTC),
                    valid_until=datetime(2021, 1, 1, tzinfo=UTC),
                    actor_id=scope.actor_id,
                    synthetic=True,
                )
            )
        if bad in {"revoked", "read_only", "expired_grant"}:
            grant = session.scalar(select(AccessGrant))
            assert grant
            if bad == "expired_grant":
                grant.valid_until = datetime.now(UTC) - timedelta(days=1)
            elif bad == "revoked":
                grant.revoked = True
            else:
                grant.can_write = False
        if bad == "consent":
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
    with pytest.raises(DataError):
        case.service.ingest(scope, case.principal, "cgm", [cgm()], "denied", uuid4())
    assert count(case, EventRevision) == 0


def test_rls_absent_invalid_scope_and_no_privileged_writes(case: Case) -> None:
    ingest(case)
    for value in ["", "not-a-uuid", str(case.foreign_patient)]:
        with case.database.sessions.begin() as session:
            session.execute(
                text("SELECT set_config('t1d.patient_id',:value,true)"), {"value": value}
            )
            assert session.execute(text("SELECT count(*) FROM event_revisions")).scalar_one() == 0
    with case.database.sessions.begin() as session:
        authorize(session, case.scope, False)
        assert session.execute(text("SELECT count(*) FROM patients")).scalar_one() == 1
        assert session.execute(text("SELECT count(*) FROM event_revisions")).scalar_one() == 1
    for sql in [
        "DELETE FROM event_revisions",
        "UPDATE audit_events SET outcome='altered'",
        "TRUNCATE patients",
        "UPDATE access_grants SET revoked=false",
    ]:
        with pytest.raises(DBAPIError), case.database.sessions.begin() as session:
            authorize(session, case.scope, True)
            session.execute(text(sql))


def test_constraints_cross_patient_fk_and_immutable_admin(case: Case) -> None:
    ingest(case)
    with pytest.raises(DBAPIError), case.admin.begin() as connection:
        connection.execute(text("UPDATE event_revisions SET revision=7"))
    with pytest.raises(DBAPIError), case.admin.begin() as connection:
        connection.execute(text("UPDATE cgm_readings SET glucose_value=-1"))
    with pytest.raises(DBAPIError), case.admin.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO "
                "access_grants(id,study_id,patient_id,actor_id,can_read,can_write,revoked,valid_until,approved_by)"
                " VALUES (:id,:study,:patient,:actor,true,true,false,now()+interval '1 "
                "hour',:actor)"
            ),
            {
                "id": uuid4(),
                "study": case.scope.study_id,
                "patient": case.foreign_patient,
                "actor": uuid4(),
            },
        )


def test_all_event_payloads_and_confirmed_nutrition(case: Case) -> None:
    base = cgm().model_dump(include={"source_event_ref", "event_time", "provenance"})
    nutrition = {
        "carbohydrate_g": "12",
        "protein_g": "3",
        "fat_g": "2",
        "energy_kcal": "78",
        "reference_ref": "synthetic-food",
        "method_version": "1",
        "uncertainty_status": "unknown",
    }
    meal = MealInput.model_validate(
        {
            **base,
            "source_event_ref": "meal",
            "status": "confirmed",
            "nutrition": nutrition,
            "components": [
                {
                    "food_label": "synthetic-food",
                    "portion_value": "80",
                    "portion_unit": "g",
                    "status": "confirmed",
                    "nutrition": nutrition,
                }
            ],
        }
    )
    insulin = InsulinInput.model_validate(
        {
            **base,
            "source_event_ref": "insulin",
            "event_kind": "planned",
            "amount_value": "1.5",
            "amount_unit": "U",
            "insulin_type_ref": "synthetic-marker",
        }
    )
    activity = ActivityInput.model_validate(
        {
            **base,
            "source_event_ref": "activity",
            "activity_type": "synthetic-motion",
            "start_at": base["event_time"],
            "end_at": "2020-01-01T00:01:00+05:30",
            "intensity_status": "unknown",
        }
    )
    cases: list[tuple[Kind, Payload]] = [
        ("meal", meal),
        ("insulin", insulin),
        ("activity", activity),
    ]
    for kind, item in cases:
        result = case.service.ingest(case.scope, case.principal, kind, [item], kind, uuid4())
        assert result["accepted"] == 1
        assert (
            len(
                case.service.history(case.scope, kind, datetime.now(UTC), 100, None, uuid4())[
                    "records"
                ]
            )
            == 1
        )
    with Session(case.admin) as session:
        assert session.scalar(select(func.count()).select_from(NutritionRecord)) == 2
        assert session.scalar(select(Meal.confirmed_by)) == case.scope.actor_id


def test_pagination_and_missing_reading(case: Case) -> None:
    items = [cgm(str(i), glucose_value=None, sensor_status="missing") for i in range(3)]
    case.service.ingest(case.scope, case.principal, "cgm", items, "missing", uuid4())
    cutoff = datetime.now(UTC)
    first = case.service.history(case.scope, "cgm", cutoff, 2, None, uuid4())
    second = case.service.history(case.scope, "cgm", cutoff, 2, first["next_cursor"], uuid4())
    assert len(first["records"]) + len(second["records"]) == 3
    assert {r["id"] for r in first["records"]}.isdisjoint({r["id"] for r in second["records"]})
    assert first["records"][0]["data"]["glucose_value"] is None
    with pytest.raises(DataError):
        case.service.history(case.scope, "cgm", cutoff, 10, "invalid cursor", uuid4())


def test_api_auth_headers_decimal_payload_and_safe_failures(case: Case) -> None:
    app = create_app(Settings(environment="test"), database=case.database)
    path = f"/api/v1/patients/{case.scope.patient_id}/cgm-readings"
    headers = {"X-Study-ID": str(case.scope.study_id), "Idempotency-Key": "api"}
    with TestClient(app) as client:
        assert client.get("/api/v1/health/ready").status_code == 200
        assert (
            client.post(
                path, json={"readings": [cgm().model_dump(mode="json")]}, headers=headers
            ).status_code
            == 401
        )

        class Auth:
            async def authenticate(self, request: object) -> Principal:
                return case.principal

        app.dependency_overrides[get_authenticator] = Auth
        data = (
            '{"readings":['
            + cgm().model_dump_json().replace('"110.123456789012"', "110.123456789012")
            + "]}"
        )
        result = client.post(
            path, content=data, headers={**headers, "Content-Type": "application/json"}
        )
        assert result.status_code == 201, result.text
        invalid = cgm().model_dump(mode="json")
        invalid["glucose_unit"] = "unsupported-private-value"
        result = client.post(path, json={"readings": [invalid]}, headers=headers)
        assert result.status_code == 422 and "private-value" not in result.text
        assert result.json()["error"]["code"] == "INVALID_UNIT"
        too_large = client.post(path, content=b"x" * 1_048_577, headers=headers)
        assert too_large.status_code == 413


def test_downgrade_refuses_populated_database(case: Case) -> None:
    with pytest.raises(RuntimeError, match="patient records"):
        command.downgrade(Config("alembic.ini"), "base")


def test_empty_disposable_migration_roundtrip_and_failure_guard(
    case: Case, monkeypatch: pytest.MonkeyPatch
) -> None:
    import os

    import psycopg
    from psycopg import sql
    from sqlalchemy.engine import make_url

    raw = os.environ["T1D_TEST_ADMIN_URL"]
    name = "t1d_test_" + uuid4().hex
    url = make_url(raw).set(drivername="postgresql+psycopg", database=name)
    with psycopg.connect(raw, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    try:
        monkeypatch.setenv("T1D_MIGRATION_DATABASE_URL", url.render_as_string(hide_password=False))
        command.upgrade(Config("alembic.ini"), "head")
        command.downgrade(Config("alembic.ini"), "base")
        command.upgrade(Config("alembic.ini"), "head")
        monkeypatch.setenv(
            "T1D_MIGRATION_DATABASE_URL",
            url.set(database="t1d_research_local").render_as_string(hide_password=False),
        )
        with pytest.raises(RuntimeError, match="restricted"):
            command.upgrade(Config("alembic.ini"), "head")
    finally:
        with psycopg.connect(raw, autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name))
            )


def test_known_quarantined_correction_hides_old_revision(case: Case) -> None:
    from t1d_api.db.models import DataSource

    result = ingest(case)
    with Session(case.admin) as session, session.begin():
        session.add(
            DataSource(
                study_id=case.scope.study_id,
                source_ref="synthetic:fixture",
                source_version="2",
                source_type="model",
                approved=True,
                license_reference="synthetic-marker-only",
            )
        )
    corrected = cgm(
        revision=2,
        supersedes_id=UUID(result["reading_ids"][0]),
        provenance={
            "source_type": "model",
            "source_ref": "synthetic:fixture",
            "source_version": "2",
            "recorded_at": "2020-01-02T00:00:00Z",
        },
    )
    ingest(case, corrected, "quarantined-correction")
    assert not case.service.history(case.scope, "cgm", datetime.now(UTC), 100, None, uuid4())[
        "records"
    ]


def test_concurrent_different_keys_share_source_deduplication(case: Case) -> None:
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda i: ingest(case, key=f"distinct-{i}"), range(4)))
    assert sum(result["accepted"] for result in results) == 1
    assert sum(result["duplicates"] for result in results) == 3
    assert count(case, EventRevision) == 1


def test_api_history_audit_and_exact_decimal_wire_value(case: Case) -> None:
    from t1d_api.auth import Principal

    class Auth:
        async def authenticate(self, request: object) -> Principal:
            return case.principal

    ingest(case)
    app = create_app(Settings(environment="test"), database=case.database)
    app.dependency_overrides[get_authenticator] = Auth
    headers = {"X-Study-ID": str(case.scope.study_id)}
    base = f"/api/v1/patients/{case.scope.patient_id}"
    with TestClient(app) as client:
        result = client.get(
            base + "/cgm-readings",
            params={"cutoff": datetime.now(UTC).isoformat()},
            headers=headers,
        )
        assert result.status_code == 200, result.text
        assert result.json()["records"][0]["data"]["glucose_value"] == "110.123456789012"
        assert client.get(base + "/audit-events", headers=headers).status_code == 200
        foreign = client.get(
            f"/api/v1/patients/{case.foreign_patient}/audit-events", headers=headers
        )
        assert foreign.status_code == 404
        naive = client.get(
            base + "/cgm-readings", params={"cutoff": "2020-01-01T00:00:00"}, headers=headers
        )
        assert naive.status_code == 422
        assert naive.json()["error"]["code"] == "INVALID_TIMESTAMP"
        numeric = client.get(
            base + "/cgm-readings", params={"cutoff": "1577836800"}, headers=headers
        )
        assert numeric.status_code == 422
        invalid = client.post(
            base + "/cgm-readings",
            content=b"{bad",
            headers={**headers, "Content-Type": "application/json"},
        )
        assert invalid.status_code == 422
        assert (
            client.get(
                base + "/cgm-readings", params={"cutoff": datetime.now(UTC).isoformat()}
            ).status_code
            == 422
        )
        invalid_parameters: list[dict[str, str | int]] = [
            {"limit": 201},
            {"cursor": "malformed' OR 1=1"},
        ]
        for extra in invalid_parameters:
            assert (
                client.get(
                    base + "/cgm-readings",
                    params={"cutoff": datetime.now(UTC).isoformat(), **extra},
                    headers=headers,
                ).status_code
                == 422
            )


def test_runtime_query_timeout_rolls_back_without_patient_mutation(case: Case) -> None:
    with pytest.raises(DBAPIError), case.database.sessions.begin() as session:
        authorize(session, case.scope, False)
        session.execute(text("SET LOCAL statement_timeout=20"))
        session.execute(text("SELECT pg_sleep(0.1)"))
    assert count(case, EventRevision) == 0


def test_synthetic_batch_timing_and_query_plan(case: Case) -> None:
    import json
    from pathlib import Path
    from time import perf_counter

    items = [cgm(f"benchmark-{i}") for i in range(20)]
    begin = perf_counter()
    case.service.ingest(case.scope, case.principal, "cgm", items, "benchmark", uuid4())
    ingested = perf_counter()
    rows = case.service.history(case.scope, "cgm", datetime.now(UTC), 100, None, uuid4())["records"]
    ended = perf_counter()
    assert len(rows) == 20
    with case.database.sessions.begin() as session:
        authorize(session, case.scope, False)
        plan = session.execute(
            text(
                "EXPLAIN (FORMAT JSON) SELECT id FROM event_revisions "
                "WHERE study_id=:study AND patient_id=:patient ORDER BY event_time,id LIMIT 20"
            ),
            {"study": case.scope.study_id, "patient": case.scope.patient_id},
        ).scalar_one()

    def nodes(node: dict[str, Any]) -> list[str]:
        return [str(node["Node Type"])] + [
            value for child in node.get("Plans", []) for value in nodes(child)
        ]

    Path("/tmp/t1d-phase02-benchmark.json").write_text(
        json.dumps(
            {
                "synthetic": True,
                "records": 20,
                "ingestion_ms": round((ingested - begin) * 1000, 3),
                "history_ms": round((ended - ingested) * 1000, 3),
                "plan_nodes": nodes(plan[0]["Plan"]),
                "scope": "single local run; no production performance claim",
            }
        )
        + "\n"
    )


def test_database_checks_and_payload_kind_foreign_key_without_immutable_updates(case: Case) -> None:
    from t1d_api.db.models import CGMReading, Meal

    ingest(case)
    with pytest.raises(DBAPIError) as failure, Session(case.admin) as session, session.begin():
        prior = session.scalar(select(EventRevision))
        assert prior
        values = {c.name: getattr(prior, c.name) for c in EventRevision.__table__.columns}
        values.update(id=uuid4(), revision=2, supersedes_id=prior.id)
        revision = EventRevision(**values)
        session.add(revision)
        session.flush()
        session.add(
            CGMReading(
                id=revision.id,
                event_time=revision.event_time,
                study_id=case.scope.study_id,
                patient_id=case.scope.patient_id,
                glucose_value=-1,
                glucose_unit="mg/dL",
                glucose_mmol_l=1,
                conversion_version="niddk-0.0555-v1",
                device_ref="synthetic-device",
                sensor_status="valid",
            )
        )
        session.flush()
    from psycopg.errors import CheckViolation, ForeignKeyViolation

    assert isinstance(failure.value.orig, CheckViolation)
    with pytest.raises(DBAPIError) as failure, Session(case.admin) as session, session.begin():
        prior = session.scalar(select(EventRevision))
        assert prior
        session.add(
            Meal(
                id=prior.id,
                study_id=case.scope.study_id,
                patient_id=case.scope.patient_id,
                status="draft",
                meal_revision=prior.revision,
            )
        )
        session.flush()
    assert isinstance(failure.value.orig, ForeignKeyViolation)
    assert count(case, EventRevision) == 1


def test_direct_timescale_chunk_access_cannot_bypass_scope(case: Case) -> None:
    from psycopg.errors import InsufficientPrivilege

    ingest(case)
    with case.admin.connect() as connection:
        schema, name = connection.execute(
            text(
                "SELECT chunk_schema,chunk_name FROM timescaledb_information.chunks "
                "WHERE hypertable_name='cgm_readings'"
            )
        ).one()
    quote = case.admin.dialect.identifier_preparer.quote
    try:
        with case.database.sessions.begin() as session:
            observed = session.execute(
                text(f"SELECT count(*) FROM {quote(schema)}.{quote(name)}")
            ).scalar_one()
            assert observed == 0
    except DBAPIError as error:
        assert isinstance(error.orig, InsufficientPrivilege)

    with pytest.raises(DBAPIError) as failure, case.database.sessions.begin() as session:
        session.execute(text(f"INSERT INTO {quote(schema)}.{quote(name)} DEFAULT VALUES"))
    assert isinstance(failure.value.orig, InsufficientPrivilege)
