"""Additive Phase 05 canonical episode manifests and derived local feature vectors."""

from pathlib import Path

from alembic import op
from sqlalchemy import text

revision = "0003_memory"
down_revision = "0002_runtime_chunk_guard"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().exec_driver_sql(
        (Path(__file__).parent / "0003-memory.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade() -> None:
    connection = op.get_bind()
    if (
        connection.execute(text("SELECT count(*) FROM patients")).scalar_one()
        or connection.execute(text("SELECT count(*) FROM memory_episodes")).scalar_one()
    ):
        raise RuntimeError("Downgrade refused: patient records exist")
    if (
        not connection.execute(text("SELECT current_database()"))
        .scalar_one()
        .startswith("t1d_test_")
    ):
        raise RuntimeError("Downgrade restricted to empty disposable test databases")
    op.execute("DROP TABLE memory_index_state")
    op.execute("DROP TABLE memory_episodes")
    op.execute("DROP FUNCTION public.t1d_stamp_memory()")
    op.execute("DROP FUNCTION public.t1d_memory_tombstone()")
