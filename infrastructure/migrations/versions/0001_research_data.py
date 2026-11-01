"""Immutable Phase 02 schema with extensions, scope policies and append-only records."""

from pathlib import Path

from alembic import op
from sqlalchemy import text

revision = "0001_research_data"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    connection.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS timescaledb")
    connection.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
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
    if versions != {"timescaledb": "2.29.0", "vector": "0.8.1"}:
        raise RuntimeError("Database extension versions do not match the verified baseline")
    for name in ["0001-tables.sql", "0001-security.sql"]:
        connection.exec_driver_sql(
            (Path(__file__).parent / name).read_text(), execution_options={"no_parameters": True}
        )


def downgrade() -> None:
    connection = op.get_bind()
    # A guard, not a reset command. Never remove records, even in the Phase 02 dev DB.
    count = connection.execute(text("SELECT count(*) FROM patients")).scalar_one()
    if count:
        raise RuntimeError(
            "Downgrade refused: patient records exist; use a reviewed forward migration"
        )
    if connection.execute(text("SELECT current_database()")).scalar_one().startswith("t1d_test_"):
        connection.exec_driver_sql(
            (Path(__file__).parent / "0001-drop.sql").read_text(),
            execution_options={"no_parameters": True},
        )
    else:
        raise RuntimeError("Downgrade is supported only in empty disposable test databases")
