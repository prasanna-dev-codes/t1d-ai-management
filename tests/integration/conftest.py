"""Every test gets a newly named disposable database, migrated from scratch."""

import os
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from psycopg import sql
from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from t1d_api.auth import Principal
from t1d_api.contracts import Role
from t1d_api.data.service import DataService
from t1d_api.db.models import AccessGrant, ConsentRecord, DataSource, Patient, ResearchStudy
from t1d_api.db.session import Database, Scope


@dataclass
class Case:
    database: Database
    admin: Engine
    scope: Scope
    foreign_patient: UUID
    foreign_study: UUID
    principal: Principal
    migration_url: str = field(repr=False)

    @property
    def service(self) -> DataService:
        return DataService(self.database)


@pytest.fixture
def case(monkeypatch: pytest.MonkeyPatch) -> Iterator[Case]:
    raw = os.environ.get("T1D_TEST_ADMIN_URL")
    if not raw:
        pytest.skip("Run scripts/run_database_tests.py for isolated PostgreSQL integration tests")
    base = make_url(raw)
    assert base.database == "t1d_tests", "Integration tests require the dedicated disposable runner"
    name = "t1d_test_" + uuid4().hex
    with psycopg.connect(raw, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    url = base.set(drivername="postgresql+psycopg", database=name)
    admin = create_engine(url, hide_parameters=True)
    migration_url = url.render_as_string(hide_password=False)
    monkeypatch.setenv("T1D_MIGRATION_DATABASE_URL", migration_url)
    command.upgrade(Config("alembic.ini"), "head")
    runtime = url.set(username="t1d_runtime", password=os.environ["T1D_TEST_RUNTIME_PASSWORD"])
    db = Database(runtime.render_as_string(hide_password=False))
    actor, study, patient, other, other_study = [uuid4() for _ in range(5)]
    with Session(admin) as session, session.begin():
        session.add_all(
            [
                ResearchStudy(id=study, reference="synthetic-primary", synthetic=True),
                ResearchStudy(id=other_study, reference="synthetic-foreign", synthetic=True),
            ]
        )
        session.flush()
        session.add_all(
            [
                Patient(
                    id=patient,
                    study_id=study,
                    research_subject_ref="synthetic-a",
                    status="active",
                    provenance={"source_type": "synthetic"},
                ),
                Patient(
                    id=other,
                    study_id=other_study,
                    research_subject_ref="synthetic-b",
                    status="active",
                    provenance={"source_type": "synthetic"},
                ),
            ]
        )
        session.flush()
        session.add(
            ConsentRecord(
                patient_id=patient,
                study_id=study,
                version=1,
                status="granted",
                effective_at=datetime(2000, 1, 1, tzinfo=UTC),
                actor_id=actor,
                synthetic=True,
            )
        )
        session.add(
            AccessGrant(
                patient_id=patient,
                study_id=study,
                actor_id=actor,
                can_read=True,
                can_write=True,
                valid_until=datetime.now(UTC) + timedelta(days=1),
                approved_by=actor,
                revoked=False,
            )
        )
        session.add(
            DataSource(
                study_id=study,
                source_ref="synthetic:fixture",
                source_version="1",
                source_type="synthetic",
                approved=True,
                license_reference="authored-synthetic-no-third-party-data",
            )
        )
        session.add(
            DataSource(
                study_id=study,
                source_ref="synthetic:model",
                source_version="1",
                source_type="model",
                approved=True,
                license_reference="synthetic-model-marker-no-inference",
            )
        )
    principal = Principal(
        subject_id=actor,
        roles=frozenset({Role.RESEARCHER}),
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    try:
        yield Case(
            db, admin, Scope(actor, study, patient), other, other_study, principal, migration_url
        )
    finally:
        db.close()
        admin.dispose()
        assert name.startswith("t1d_test_") and len(name) == 41
        with psycopg.connect(raw, autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name))
            )
