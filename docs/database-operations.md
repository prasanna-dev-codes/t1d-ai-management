# Phase 02 local database operations

Research-only local infrastructure. Phase 01 remains a separate project on 5433; its database/volume and Neo4j are not migration targets. Never run `down -v`, prune volumes, restore over a populated database or use a clinical dataset for tests.

## Chosen combination and credentials

Pinned image: `timescale/timescaledb:2.29.0-pg17-oss@sha256:1a34ea7d1472a57a8d6384a492ffece6d20e4079e81b765833675077cf98b207`. Verified ARM64 runtime: PostgreSQL 17.10, TimescaleDB 2.29.0, pgvector 0.8.1, Apache Timescale mode. Both extensions coexist and SQL hypertable/vector capability probes pass. The multi-platform publisher manifest includes AMD64; hosted execution of this change is NOT RUN. PostgreSQL is one patch older than Phase 01, explicitly disclosed and approved for this isolated project. Reassess updates/security before later use.

`phase02.compose.yml` uses project `t1d-ai-phase02`, volume `t1d-ai-phase02_phase02_data`, binding only `127.0.0.1:5434`. Administrator `t1d_migrator` and non-owner `t1d_runtime` have distinct credentials. Health authenticates the runtime user over the Docker network; application readiness additionally verifies privileges, migration and extension versions. Local data is not automatically encrypted or backed up.

From repository root, after Python setup:

```sh
uv run --frozen --no-sync python scripts/setup_phase02_env.py
# If configuration already exists, this refuses to overwrite it; preserve existing credentials.
docker compose --env-file infrastructure/docker/.env.phase02 -f infrastructure/docker/phase02.compose.yml config --quiet
docker compose --env-file infrastructure/docker/.env.phase02 -f infrastructure/docker/phase02.compose.yml up -d --wait
```

The generated `.env.phase02` is ignored and mode 0600. The blank `.env.phase02.example` is the tracked template. Do not display env files, expanded Compose configuration, container environment, connection strings or credentials. Do not change bootstrap passwords without a deliberate role/credential rotation: entrypoint SQL only runs on a fresh cluster.

## Migration and runtime separation

The trusted, locally generated env file contains separate migration/runtime URLs. With shell tracing disabled, load it without printing values:

```sh
set -a
source infrastructure/docker/.env.phase02
set +a
uv run --frozen --no-sync alembic upgrade head
uv run --frozen --no-sync alembic current
unset T1D_MIGRATION_DATABASE_URL PHASE02_ADMIN_PASSWORD PHASE02_RUNTIME_PASSWORD
uv run --frozen --no-sync python -m t1d_api
```

`T1D_DATABASE_URL` remains the restricted runtime URL; never start the API with the migration URL. No database URL is required for Phase 01-only connectivity mode. With one configured, readiness fails if PostgreSQL is unavailable, unsafe, unmigrated or has mismatched extensions. Liveness remains process-only. The default authenticator always denies patient routes; no test principal adapter is selectable by environment.

Migration `0001_research_data` creates verified extensions, 16 application tables, indexes, triggers, grants and forced RLS. It uses frozen SQL instead of importing mutable ORM definitions for schema creation. Migration `0002_runtime_chunk_guard` is the current head: it revokes direct chunk ACLs and installs an after-insert guard that secures new chunks within the creating transaction. Parent-table RLS alone does not protect direct chunk reads. Readiness detects unexpected direct privileges. Repeating upgrade is idempotent. Environment checks reject Phase 01/unknown database names; no implicit fallback exists. Extensions/bootstrap roles are privileged prerequisites. Any future schema change requires a new reviewed migration; do not regenerate the applied initial SQL.

Downgrade is supported **only in empty, explicitly named disposable `t1d_test_*` databases**. It refuses any patient records and every persistent Phase 02 database, leaving extensions/roles intact. Populated recovery requires reviewed forward migration or a separately approved backup/restore procedure; no automatic destructive rollback exists. No persistent downgrade/reset is part of verification.

## Disposable tests and synthetic export

```sh
uv run --frozen --no-sync pytest -q --ignore=tests/integration
uv run --frozen --no-sync python scripts/run_database_tests.py
uv run --frozen --no-sync python scripts/generate_synthetic_data.py --seed 42 --count 12 --output /tmp/t1d-synthetic-phase02.json
```

The runner starts a uniquely named RAM-backed pinned-image container, generates temporary credentials in a mode-0600 file, creates new UUID-named databases per test, runs actual migrations and drops only those test databases. It stops only its owned `--rm` container. No named volume is attached. Test output redacts its generated credentials and fixture representations hide migration URLs. On interruption, inspect containers bearing `t1d.purpose=disposable-tests` and stop only the identified owned test container; never prune unrelated containers or volumes.

The export command connects to no database, refuses overwrites and labels deterministic patient markers/events/corrections/missingness/duplicates as synthetic. Correction descriptors require resolving the returned predecessor UUID; they are not ready-made real data imports. Fixtures claim no physiological realism or model accuracy. Remove only the explicitly generated temporary export when finished. The integration fixtures provision synthetic studies/consent/grants separately under privileged test credentials; runtime cannot self-provision access.

## Reliability and scale limits

The runtime pool has 5 connections plus 5 overflow, 5-second pool/connect/statement timeouts, 2-second lock timeout and 15-second idle transaction timeout. Each operation uses a bounded transaction, parameter binding and redacted SQL errors. There is no blind server retry after ambiguous commit: clients retry an identical idempotency key. Retrying transient lock/conflict/outage failures is a caller decision with bounded backoff; changing the key is unsafe after an unknown result. Advisory locks and unique constraints serialize duplicate writes.

History is bounded to 200 records, batch ingestion to 100 and body size to 1 MiB. CGM uses seven-day chunks and scope/time indexes; no retention or compression policy is enabled. Capacity planning may begin with one five-minute CGM stream (~288/day/patient) but this is an assumption, not a supported-volume guarantee. The 20-record local synthetic timing/query-plan sample in the review is a diagnostic only. Meal reconstruction currently performs bounded related-record queries; optimize only against measured workloads. No production SLA, backup restore, failover, TLS deployment or encryption verification is claimed.

Linux CI uses the same digest's AMD64 image, a fresh uv environment and Docker runner; local Apple silicon uses ARM64. Local filesystem duplication affected editable Python paths and `.next` cache: wheel reinstall / clean generated build cache resolved it without changing type or test assertions. This environment observation is not a hosted CI result.
