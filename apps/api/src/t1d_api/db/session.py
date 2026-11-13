"""Bounded pools, trusted actor context and runtime-role verification."""

import json
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from t1d_api.data.errors import DataError


@dataclass(frozen=True)
class Scope:
    actor_id: UUID
    study_id: UUID
    patient_id: UUID


def engine_for(url: str) -> Engine:
    return create_engine(
        url,
        pool_size=5,
        max_overflow=5,
        pool_timeout=5,
        pool_pre_ping=True,
        hide_parameters=True,
        json_serializer=lambda value: json.dumps(value, default=str),
        connect_args={
            "connect_timeout": 5,
            "options": "-c timezone=UTC -c statement_timeout=5000 -c lock_timeout=2000 -c "
            "idle_in_transaction_session_timeout=15000",
        },
    )


class Database:
    def __init__(self, url: str) -> None:
        if make_url(url).drivername != "postgresql+psycopg":
            raise ValueError("Explicit PostgreSQL Psycopg URL required")
        self.engine = engine_for(url)
        self.sessions = sessionmaker(self.engine, expire_on_commit=False)

    def check(self) -> bool:
        with self.engine.connect() as connection:
            role = connection.execute(
                text(
                    "SELECT r.rolsuper OR r.rolbypassrls OR r.rolcreaterole OR r.rolcreatedb OR "
                    "EXISTS (SELECT 1 FROM timescaledb_information.chunks WHERE "
                    "hypertable_schema='public' AND hypertable_name='cgm_readings' AND "
                    "has_table_privilege(current_user,format('%I.%I',chunk_schema,chunk_name),"
                    "'SELECT,INSERT,UPDATE,DELETE,TRUNCATE')) OR "
                    "EXISTS (SELECT 1 FROM pg_tables WHERE schemaname='public' AND "
                    "tableowner=current_user) "
                    "FROM pg_roles r WHERE rolname=current_user"
                )
            ).scalar_one()
            versions = dict(
                connection.execute(
                    text(
                        "SELECT extname,extversion FROM pg_extension WHERE extname IN "
                        "('timescaledb','vector')"
                    )
                )
                .tuples()
                .all()
            )
            migration = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            if (
                role
                or versions != {"timescaledb": "2.29.0", "vector": "0.8.1"}
                or migration not in {"0002_runtime_chunk_guard", "0003_memory"}
            ):
                raise DataError(503, "DATABASE_CONFIGURATION")
        return True

    def close(self) -> None:
        self.engine.dispose()


def set_actor(session: Session, actor: str) -> None:
    session.execute(text("SELECT set_config('t1d.actor_id', :actor, true)"), {"actor": actor})


def authorize(session: Session, scope: Scope, write: bool) -> None:
    for key, value in [
        ("actor_id", scope.actor_id),
        ("study_id", scope.study_id),
        ("patient_id", scope.patient_id),
    ]:
        session.execute(
            text("SELECT set_config(:key,:value,true)"), {"key": "t1d." + key, "value": str(value)}
        )
    valid = session.execute(
        text("SELECT public.t1d_authorize_and_lock(:study,:patient,:write)"),
        {"study": scope.study_id, "patient": scope.patient_id, "write": write},
    ).scalar_one()
    if not valid:
        raise DataError(404, "RESOURCE_UNAVAILABLE")
