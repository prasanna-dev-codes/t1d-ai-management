# Development standards

Status: Phase 00 engineering standards retained; Phase 01 toolchain/minimal backend/frontend and the approved Phase 02 synthetic data slice are implemented. See [local development](local-development.md) for prerequisites, setup, environment variables, run/shutdown commands, health routes, troubleshooting and limitations.

## Workflow and boundaries
Read [architecture](architecture.md), [roadmap](roadmap.md), relevant [requirements](requirements.md), and [repository instructions](../AGENTS.md) before editing. Scope each branch and PR to one phase and one reviewable change. Use `phase-01/short-purpose` style branch names. Do not commit or push automatically. Preserve unrelated work. Architecture changes need explicit approval and an ADR; clinical policy, dosage logic, and deployment settings need human approval before modification.

`apps/api` owns transport, authorization, and orchestration; `apps/web` owns presentation. `services/*` are importable modules within a modular monolith, not independently deployed microservices. `packages/shared-contracts` holds generated, versioned transport contracts once implementation starts. `ml` owns offline experiments; `infrastructure` owns future migrations and local runtime definitions. Domain modules must not depend on frontend or transport types. Workers may reuse domain modules through the same authorization and safety boundaries.

## Python and TypeScript
Target Python 3.12+; select and record one supported minor version in Phase 01. Use type annotations on public functions, explicit return types, Pydantic v2 boundary validation, typed domain objects, narrow exception handling, and structured domain error codes. Use snake_case for Python modules/functions, PascalCase for classes, and UTC-aware datetimes. Reject unknown request fields where they could hide unit or identifier mistakes. Do not perform inference or I/O at import time.

Use strict TypeScript, explicit API result types, PascalCase React components, and accessible form labels. Avoid `any`, unchecked casts, and calculations that duplicate backend clinical logic. Preserve explicit units and uncertainty in UI contracts. Generate frontend types from reviewed OpenAPI rather than maintaining independent schema copies. Tests and implementation use stable, descriptive names.

## API and database practices
Follow [API contracts](api-contracts.md): versioned routes, explicit units, UUID strings, RFC 3339 timestamps, ownership checks, structured error envelopes, and idempotent event ingestion. Transport validation never replaces domain safety validation. Document backward-incompatible contract changes before implementation.

Use SQLAlchemy models and reviewed Alembic migrations. Review SQL for constraints, tenant scoping, indexes, backfill cost, and reversible recovery. Never apply a migration to a shared deployment automatically. Test upgrades and recovery on disposable synthetic databases. Do not edit already-applied migrations; add corrective migrations. Keep clinical setting revisions immutable and approved explicitly.

## Verification plan
Phase 00 used documentation checks only. Phase 01 uses the exact commands in Makefile and `.github/workflows/ci.yml`: Ruff lint/format, strict mypy, pytest and generated-contract verification; frontend ESLint, strict TypeScript, Vitest/Testing Library and Next.js build. Playwright is deferred until browser workflow scope warrants it. Only report observed local results; hosted CI is not verified until executed.

Clinical feature changes require deterministic unit, integration, and safety regression tests. Cover invalid units, missing values, stale/future timestamps, uncertainty gates, unauthorized access, and parameter immutability. Test retrieval with patient-disjoint and time-cutoff fixtures and a deliberately planted future event. API tests must include forbidden foreign identifiers, partial-batch rollback, retries, and redacted errors. UI tests must verify abstention and experimental labels. Use fixed seeds, frozen clocks, and synthetic fixtures. ML evaluations are separate from software tests; report both.

## Dependencies and reproducibility
Phase 00 added no dependencies. Phase 01 uses user-specified uv for Python and npm workspaces for JavaScript; exact direct versions and transitive artifacts are recorded in manifests and lockfiles. No commit is authorized automatically. For every direct dependency record purpose, pinned resolved version, upstream license, transitive risks, macOS/CI architecture support, and a review date in [technology stack](technology-stack.md). Pin container digests and model/data manifests later. Do not invent version compatibility from major version labels. Small CI checks should precede expensive training jobs; training is never an implicit PR action.

## Logging and secrets
Use structured events with UTC time, severity, correlation ID, operation, outcome, duration, and safe component/version labels. Never log images, glucose values, insulin events, nutrition, tokens, identifiers that reveal a person, request bodies, or raw prompts. Protected audit records are a separate access-controlled store with opaque references. Redact errors and traces before OpenTelemetry or Sentry export; external export stays disabled until governance approval. See [safety and privacy](safety-and-privacy.md).

Use environment templates with dummy values only. Actual credentials belong in an approved secret manager/local ignored environment file. No credentials in notebooks, fixtures, commits, or screenshots. Ignore rules are not access controls; future CI should scan for secrets and prohibited artifacts. Do not put real health data in this repository even if a local path is ignored.

## Documentation and AI-assisted changes
Document changes to units, schema semantics, ownership, missing-data behavior, model lineage, and evaluation limits. Record dataset source/access/license verification and permitted uses before acquisition. AI-generated code and model suggestions require the same review and tests as human work. LLMs cannot authorize treatment, override safety, or change clinical settings. Treat retrieved content as untrusted data, never executable instructions.

## PR checklist
- Identify phase, requirement IDs, changed behavior, affected contracts, and relevant ADRs.
- Describe exact checks executed, outcomes, and checks not run; disclose failures.
- Include synthetic test evidence and subgroup/uncertainty evaluation when relevant.
- Check ownership, time cutoffs, explicit units, audit trail, and safe failure behavior.
- Confirm no secrets, health records, downloaded datasets, weights, or unsupported validation claims.
- Document risks, migration/recovery plans where relevant, limitations, and required approvals.
- Assign a reviewer other than the author; clinical changes additionally need qualified review.

## Phase 01 execution guide
Use [local development](local-development.md) as the operational command reference and [Phase 01 review](phase-01-review.md) as the evidence register. Optional stores are not API readiness dependencies until explicitly wired and probed. No production identity or runtime dev-principal bypass is implemented. Test-only dependency overrides must remain in tests.

## Phase 02 checks and migration discipline

Keep unit/regression checks separate from actual PostgreSQL integration tests: `uv run --frozen --no-sync pytest -q --ignore=tests/integration` and `uv run --frozen --no-sync python scripts/run_database_tests.py`. A default pytest run may skip database tests when runner-only configuration is absent; skips are not integration success. Run Ruff check/format, strict mypy, contract export --check, frontend lint/typecheck/tests/build. CI has distinct backend/database/frontend jobs; never report hosted success from local results.

The database runner owns an ephemeral RAM container and creates fresh synthetic databases; no named development volume is attached. Schema upgrade/downgrade tests target only these databases. Initial migration SQL is frozen after persistent application; later changes require a new migration. Never print env files, rendered Compose configuration, SQL exception parameters or connection strings. The runner redacts generated passwords, and sensitive fixture fields are excluded from repr. No real patient fixtures or production auth bypass are permitted.
