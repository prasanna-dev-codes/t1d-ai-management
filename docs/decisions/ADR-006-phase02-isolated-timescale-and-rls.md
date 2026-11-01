# ADR-006 — Isolated Phase 02 TimescaleDB, revision registry and RLS

Status: Accepted by explicit user approval on 2026-11-01. Scope: Phase 02 research infrastructure only.

The user approved the pinned publisher OSS image, separate Compose project/volume/port, non-owner runtime role with RLS, and UUID revision registry alongside time-inclusive hypertable keys. The actual PostgreSQL 17.10 patch level, older than Phase 01's 17.11, was disclosed before approval. See [preflight](../phase-02-preflight.md) for manifest, SQL and upstream licensing evidence.

Use `timescale/timescaledb:2.29.0-pg17-oss@sha256:1a34ea7d1472a57a8d6384a492ffece6d20e4079e81b765833675077cf98b207`, with PostgreSQL 17.10, TimescaleDB 2.29.0 in Apache mode and pgvector 0.8.1. ARM64 runs locally; the multi-platform manifest includes AMD64 for Linux CI. This is a fresh database, not an in-place downgrade. Keep Phase 01 PostgreSQL/Neo4j volumes intact.

`event_revisions` owns stable UUID identity, scoped source uniqueness, temporal availability and append-only revision chains. `cgm_readings` uses `(event_time,id)` identity and a matching scoped/time/kind foreign key. Seven-day chunks and scope/time indexes are a conservative starting point; no automatic retention, compression, vector index, embeddings or derived graph writes are enabled.

Separate privileged `t1d_migrator` bootstrap/migration access from `t1d_runtime`, which has no ownership, superuser, bypass-RLS, role creation or database creation privileges. Trusted server code sets transaction-local actor/study/patient context. Service/repository authorization requires live grants and consent; forced RLS protects unfiltered queries. Migration owners remain privileged and runtime credentials remain inside the trusted server boundary. RLS does not authenticate principals or make leaked database credentials safe.

Alternatives considered: replacing Phase 01 in place (unnecessary volume risk), silently using plain PostgreSQL (does not satisfy verified time-series capability), and a custom source-build image (more maintenance than the verified publisher image). Review security patches and licensing before any later deployment; the selected patch is a documented local research limitation.

ClinicalSettings, MetabolicEpisode, Prediction and SafetyEvaluation persistence is explicitly deferred until their parameter, episode, model and policy contracts are approved. No speculative fields or treatment authority are introduced. Detailed operations and rollback restrictions are in [database operations](../database-operations.md).

## Implementation security verification and conditions for reconsideration

A direct internal chunk read bypassed parent RLS in the disposable synthetic regression. Migration `0002_runtime_chunk_guard` removes direct chunk ACLs, including on preexisting chunks, and installs a restricted SECURITY DEFINER after-insert trigger to remove new chunk grants before the inserting transaction commits. Normal parent-table operations remain protected and tested. Runtime readiness rejects unexpected direct chunk privileges. PostgreSQL documents [separate parent/child access checks and RLS](https://www.postgresql.org/docs/17/ddl-inherit.html); inherited protection alone must not be claimed to secure direct chunk queries. Global schema denial was unsuitable for this publisher image's driver initialization, so the guard operates on chunk ACLs. This refinement does not add an exposed API or change clinical policy.

Reverify extension/image upgrades, chunk ACL propagation, privileged GRANT changes, trigger propagation and new chunk/retention/compression features before enabling them. No compression/background chunk creation is enabled now. Changing this verified topology, approved clinical semantics or deployment settings requires a new reviewed decision.
