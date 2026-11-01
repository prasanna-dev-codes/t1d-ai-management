"""Migration-only connection. No implicit runtime or Phase 01 database fallback."""

import os

from alembic import context
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from t1d_api.db.models import Base

raw = os.environ.get("T1D_MIGRATION_DATABASE_URL")
if not raw:
    raise RuntimeError("Explicit migration database configuration required")
url = make_url(raw)
if url.database != "t1d_phase02" and not (url.database or "").startswith("t1d_test_"):
    raise RuntimeError("Migrations are restricted to Phase 02 or disposable test databases")
if context.is_offline_mode():
    raise RuntimeError("Offline migration execution is unsupported; verify extensions online")
engine = create_engine(url, hide_parameters=True, connect_args={"connect_timeout": 5})
with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()
engine.dispose()
