-- Only executed for a fresh Phase 02 volume. Values arrive via ignored environment.
\getenv runtime_password T1D_RUNTIME_PASSWORD
CREATE ROLE t1d_runtime LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS PASSWORD :'runtime_password';
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT CONNECT ON DATABASE t1d_phase02 TO t1d_runtime;
