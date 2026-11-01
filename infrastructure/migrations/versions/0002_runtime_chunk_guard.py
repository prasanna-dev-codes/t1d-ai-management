"""Remove direct chunk ACLs while preserving protected parent-table access."""

from alembic import op
from sqlalchemy import text

revision = "0002_runtime_chunk_guard"
down_revision = "0001_research_data"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    connection.exec_driver_sql(
        """
CREATE FUNCTION public.t1d_secure_chunk() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
BEGIN
 IF has_table_privilege('t1d_runtime',TG_RELID,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE') THEN
  EXECUTE format('REVOKE ALL PRIVILEGES ON TABLE %I.%I FROM PUBLIC,t1d_runtime',
   TG_TABLE_SCHEMA,TG_TABLE_NAME);
 END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION public.t1d_secure_chunk() FROM PUBLIC;
CREATE TRIGGER secure_chunk AFTER INSERT ON public.cgm_readings
FOR EACH ROW EXECUTE FUNCTION public.t1d_secure_chunk();
DO $$ DECLARE chunk record; BEGIN
 FOR chunk IN SELECT chunk_schema,chunk_name FROM timescaledb_information.chunks
 WHERE hypertable_schema='public' AND hypertable_name='cgm_readings' LOOP
  EXECUTE format('REVOKE ALL PRIVILEGES ON TABLE %I.%I FROM PUBLIC,t1d_runtime',
   chunk.chunk_schema,chunk.chunk_name);
 END LOOP;
END $$;
""",
        execution_options={"no_parameters": True},
    )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.execute(text("SELECT count(*) FROM patients")).scalar_one():
        raise RuntimeError("Downgrade refused: patient records exist")
    if (
        not connection.execute(text("SELECT current_database()"))
        .scalar_one()
        .startswith("t1d_test_")
    ):
        raise RuntimeError("Downgrade is supported only in empty disposable test databases")
    op.execute("DROP TRIGGER secure_chunk ON public.cgm_readings")
    op.execute("DROP FUNCTION public.t1d_secure_chunk()")
    connection.exec_driver_sql(
        """
DO $$ DECLARE chunk record; BEGIN
 FOR chunk IN SELECT chunk_schema,chunk_name FROM timescaledb_information.chunks
 WHERE hypertable_schema='public' AND hypertable_name='cgm_readings' LOOP
  EXECUTE format('GRANT SELECT,INSERT ON TABLE %I.%I TO t1d_runtime',
   chunk.chunk_schema,chunk.chunk_name);
 END LOOP;
END $$;
""",
        execution_options={"no_parameters": True},
    )
