# Phase 02 technical preflight and database decision

Date: 2026-11-01. Status: **Preflight/compatibility PASS; isolated image/storage/revision/RLS design explicitly approved by the user. Implementation and final verification are tracked in phase-02-review.md.** The supplied Phase 02 brief authorizes this preflight; earlier instructions forbidding Phase 02 progression are historical. No Phase 03 work, commit or push is authorized.

## Repository and reused components
Actual HEAD: `ef903a7d9b12a637b3f2f63f4d3dc91fa77642ec`, branch `main`, initially clean and synchronized with `origin/main`. This is newer than the brief's foundation reference `c53ae897e49bf187c67e0c8f06ab8c5c3dd2cff4`.

Read AGENTS.md; requirements; architecture; canonical model; API contracts; datasets; memory architecture; safety/privacy; development standards; roadmap; Phase 01 review; relevant ADRs; and the existing API/auth/settings/readiness, tests, exporter, manifests/lockfiles, Compose and CI. Existing reusable boundaries are the isolated FastAPI factory, UUID request correlation, redacted errors/logs, fail-closed authenticator and principal, readiness probes, Pydantic schemas, generated health/error types, Python/npm workspaces and regression checks. No real sessions or production identity provider exists.

Current persistent stores are healthy Phase 01 PostgreSQL 17.11 on native ARM64 and Neo4j 5.26.32. The PostgreSQL image is `postgres:17.11-alpine3.23`; inspection confirmed no TimescaleDB/pgvector in its extension inventory. Existing named volumes remain `t1d-ai-local_postgres_data`, `t1d-ai-local_neo4j_data` and `t1d-ai-local_neo4j_logs`.

## Concrete database recommendation — Approved
Use the publisher-maintained **OSS** image in a separate Phase 02 Compose project, new named volume and loopback port **5434**, preserving the existing Phase 01 service, image, credentials, volume and port 5433. The image proposal is:

```text
timescale/timescaledb:2.29.0-pg17-oss@sha256:1a34ea7d1472a57a8d6384a492ffece6d20e4079e81b765833675077cf98b207
```

Manifest inspection verified both Linux ARM64 and AMD64 entries. The multi-platform digest allows local Apple silicon and hosted AMD64 to resolve their own native platform. Runtime verification here is ARM64 only; AMD64 execution remains NOT RUN until the integration runner/CI executes it.

**Version caveat:** the actual publisher image reports **PostgreSQL 17.10**, while Phase 01 runs **17.11**. This is not an in-place downgrade because the proposal uses a fresh separate database and leaves Phase 01 untouched. The older patch must remain visible in the approval decision; there is no claim of complete security suitability. If this patch level is unacceptable, the alternative is to verify/build a PostgreSQL 17.11 image with pinned extension source revisions before proceeding. No fallback or custom image is silently selected.

Licensing direction: the selected OSS image reports `timescaledb.license = apache`. Upstream has separate Apache and Timescale License source areas; this proposal deliberately selects OSS functionality, not an unrestricted claim about every edition. pgvector uses the PostgreSQL License. Preserve notices and review base-image/transitive terms before redistributing images. No hosted service, commercial entitlement or legal-compliance determination is asserted.

## Observed compatibility results
A temporary container named `t1d-phase02-compat` was launched with **no published ports**, `--tmpfs /var/lib/postgresql/data`, automatic removal on stop and a project-specific disposable label. Its generated credential file `infrastructure/docker/.env.phase02-probe` is ignored, mode 0600, and never printed. No existing named volume was attached. This tests compatibility only and is not the final deployment configuration.

Commands and observations:

- `docker buildx imagetools inspect timescale/timescaledb:2.29.0-pg17-oss` — **PASS**, digest above; ARM64 manifest `sha256:609d46bd6c08caae2745cc860edf39610a380aeebcebb8c79a80dcd89b46c7a6`; AMD64 manifest `sha256:014868fc93dfdf35fec099775b231afb7b9b95da933e9613d4d8840acfffab39`.
- `docker pull --quiet <tag@digest above>` — **PASS**.
- `docker exec t1d-phase02-compat pg_isready -U postgres -d t1d_compat` — **PASS**.
- SQL `CREATE EXTENSION IF NOT EXISTS timescaledb; CREATE EXTENSION IF NOT EXISTS vector; SELECT version(); SELECT extname,extversion FROM pg_extension;` — **PASS**, **PostgreSQL 17.10**, **TimescaleDB 2.29.0**, **pgvector 0.8.1** active together.
- A generic `compat_series(id UUID, event_time TIMESTAMPTZ, value NUMERIC, PRIMARY KEY(id,event_time))` table was converted with `create_hypertable('compat_series','event_time')` — **PASS**; listed in `timescaledb_information.hypertables`.
- `SELECT vector_dims('[0,1]'::vector);` — **PASS**, returns 2. This is a literal capability probe, not embedding generation or similarity retrieval.
- `SHOW timescaledb.license;` — **PASS**, `apache`.
- Enabled and forced RLS on the disposable hypertable. A `NOLOGIN NOSUPERUSER NOBYPASSRLS` reader with SELECT and no allow policy saw **0 rows**; the bootstrap administrator saw the **1 generic synthetic row** — **PASS** default-deny enforcement. This is a capability test, not a completed patient-isolation implementation.
- `docker image inspect timescale/timescaledb@sha256:1a34ea7d1472a57a8d6384a492ffece6d20e4079e81b765833675077cf98b207 --format '{{.Os}}/{{.Architecture}}'` — **PASS**, `linux/arm64`.

One metadata command using only the bare tag returned “No such image” because the pull used the digest-qualified reference. Inspecting the digest-qualified image succeeded; this was not an extension/runtime failure. The generic compatibility objects exist only in disposable RAM-backed storage and are removed when that owned probe container stops. No clinical schemas, patient data, retention policy, graph retrieval or model behavior was introduced.

## Schema and access proposal — Pending approval
Separate immutable event-revision metadata from CGM measurement storage. This preserves globally addressable UUID revision identities and a canonical source/revision uniqueness registry while allowing a CGM hypertable key to include `event_time`, as required by TimescaleDB. Enforce composite patient/study/revision foreign keys. Do not sacrifice source deduplication or cross-patient referential integrity to obtain a hypertable.

Use SQLAlchemy 2.x and Alembic; separate privileged migration/bootstrap credentials from a normal non-owner `NOSUPERUSER NOBYPASSRLS` runtime login. Force RLS on scoped records and test absent/malformed scope, foreign patients and direct unfiltered queries. Principal/study/patient context must be established by trusted server code per transaction, not arbitrary client authorization claims. Database owners/superusers remain an explicitly privileged boundary, never normal application users. Consent/grants must be current and revocation fail closed. No production identity provider or runtime development-principal bypass is proposed.

The likely supporting records are research studies, pseudonymous patients, consent revisions, access grants, approved data-source/provenance metadata, immutable event revisions, ingestion batches, protected audits and an outbox. Each must have a demonstrated integrity/security purpose. Runtime credentials must not administer grants, alter schemas or delete records. Administrative fixture/provisioning operations require separate explicit commands and audit evidence.

Stable Phase 02 entities: Patient, CGMReading, Meal, MealComponent, NutritionRecord, InsulinEvent, ActivityEvent and AuditEvent; ModelVersion may receive only already-defined immutable metadata if required by source lineage. ClinicalSettings parameter definitions/approval workflows and MetabolicEpisode, Prediction and SafetyEvaluation semantics need explicit later-phase migration decisions wherever implementing them now would force unapproved clinical/model contracts. No clinical parameter values, FPU formula or treatment protocol will be invented. Deferrals will be tracked per entity, not represented as implemented tables.

## Temporal, numeric and API design to finalize
- Keep event time, source recorded time, server ingestion time and server availability time distinct. Normalize aware timestamps to UTC, preserve original offset/provenance, and reject naive/ambiguous inputs. Clients cannot backdate availability.
- Queries reconstruct the latest revision known by explicit cutoff, not the latest revision today. Filter by both event time and availability; apply patient/study authorization at service and repository/DB boundaries. Revoked current authorization blocks historical reads.
- Preserve original glucose values/units. Canonical-unit selection and a versioned deterministic Decimal conversion will be documented before implementation; no physiological thresholds or implicit unit inference. Numeric validation must not silently truncate JSON decimals or fixed-scale database values.
- Atomic bounded batches, scoped idempotency key/request digest, deterministic duplicate/conflict handling and revision lineage. Failed transactions must not leave partial clinical records; denial/rejection auditing needs a separate defined transaction strategy.
- Preserve Phase 01 health/session/error/readiness behavior. Database-backed capability readiness must reflect runtime-role, migration and extension availability. Keep liveness independent.
- Existing proposed CGM/insulin/activity endpoints can be implemented. Base meal ingestion and bounded plain-history reads need explicit Phase 02 contract documentation; these are structured data operations, not vision/graph/retrieval/forecasting features.
- Batch/payload/query/time limits are operational safeguards to document and test; no clinical quality threshold is enabled without approval. Quarantine/accepted warnings/missingness must be explicit, never converted into falsely confirmed observations.

## Implementation order and proposed files/tests
1. Resolve approval of the isolated image/storage/RLS approach; record the approved decision in an ADR. Verify any chosen alternative before final schema work.
2. Add reviewed Phase 02 Compose/configuration, separated runtime/migration credentials, typed SQLAlchemy session/model/repository modules, and Alembic prerequisites/migrations. Never migrate, reset or downgrade the existing Phase 01 volume implicitly.
3. Add strict input/provenance/Decimal/time schemas, scoped authorization, idempotent atomic ingestion, protected audits and revision-aware query services, with thin FastAPI routers.
4. Add a deterministic development-only synthetic generator and future authorized-dataset adapter/manifest interface. No real data acquisition or physiological-realism claim.
5. Add unit, integration, security, temporal and safety-regression tests under `tests/`; run migrations/rollback only in explicitly disposable test databases. Test concurrency, stale grants/consent, cross-patient references, missing/future/late revisions, secret-safe failures and dependency outages.
6. Extend CI with isolated verified database tests; preserve frontend checks and regenerate only applicable shared contracts. Hosted Phase 02 CI remains NOT RUN without a separately approved commit/push.
7. Update architecture, canonical data/API contracts, technology and development docs; create ingestion, governance, temporal-integrity, database-operations and Phase 02 review reports with exact outcomes and per-criterion status.

## Approval boundary and implementation status

The user explicitly replied “Approve this isolated Phase 02 design” to the image/new volume/5434/non-owner RLS/revision-registry proposal. The PostgreSQL patch caveat was disclosed. This authorization covers the Phase 02 implementation, not Phase 03, a commit or a push. The compatibility probe was stopped/removed and Phase 01 preserved. Subsequent schema/API/test results and limitations are in [Phase 02 review](phase-02-review.md); the preflight design notes above remain the original implementation plan, not evidence of completed checks.

## Authoritative verification references
- [TimescaleDB publisher Dockerfile](https://github.com/timescale/timescaledb-docker/blob/main/Dockerfile) and [image build definitions](https://github.com/timescale/timescaledb-docker/blob/main/Makefile): extension source/build and multi-platform provenance.
- [TimescaleDB releases](https://github.com/timescale/timescaledb/releases) and [supported platforms](https://www.tigerdata.com/docs/get-started/timescaledb-supported-platforms): release/platform evidence, supplemented by actual manifest/SQL checks above.
- [TimescaleDB license](https://github.com/timescale/timescaledb/blob/main/LICENSE), [separate Timescale License](https://github.com/timescale/timescaledb/blob/main/tsl/LICENSE-TIMESCALE) and [pgvector license](https://github.com/pgvector/pgvector/blob/master/LICENSE).
- [Hypertable uniqueness constraints](https://www.tigerdata.com/docs/build/performance-optimization/hypertables-and-unique-indexes): time-inclusive unique keys.
- [PostgreSQL 17 RLS documentation](https://www.postgresql.org/docs/17/ddl-rowsecurity.html): owner/superuser/BYPASSRLS boundaries and default-deny behavior.
