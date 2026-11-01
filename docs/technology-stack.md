# Technology stack and adoption register

Status: Phase 00 architectural selection register retained. Phase 01 foundation dependencies are now installed and locked as recorded below; data/ML/future infrastructure items remain uninstalled or unverified. Phase 00 itself installed nothing. “Selected” means planned baseline; “Candidate” means evaluate before adoption. All exact package/image versions, licenses, platform support, extension combinations, and costs are **Verification required** before installation. Python 3.12+ and Pydantic v2 are specified version families, not dependency pins. No claim of current upstream support is made here.

Each entry records purpose, selection rationale/advantages, alternatives, limits/dependencies, cost/operations, and obligation. Future adoption records must add exact resolved version/digest, official source/license, verification date, compatible peer versions, and evidence on macOS architecture and CI Linux. No dependency is added by this register.

## Backend and contracts
- **Python 3.12+ — Selected, mandatory:** typed domain logic and scientific ecosystem; readable for three students. Alternative: TypeScript-only backend. Limits: runtime typing needs explicit validation, scientific wheels vary by platform. Depends on a selected minor version and package manager. No runtime subscription assumed; environment maintenance and compute cost remain.
- **FastAPI — Selected, mandatory:** API orchestration and OpenAPI generation; integrates with Pydantic. Alternatives: Django/DRF, Flask. Advantages: schema-driven interface; limits: async handlers must not block on CPU inference, authentication remains our responsibility. Depends on ASGI server and validation stack. Low initial operational footprint; worker capacity needs measurement.
- **Pydantic v2 — Selected, mandatory:** explicit input/output schemas and strict unit/time validation. Alternative: dataclasses plus manual validators. Advantages: consistent schemas; limits: coercion must be reviewed and domain eligibility remains separate. Depends on compatible FastAPI. Local runtime cost only; test strictness and serialization compatibility.
- **SQLAlchemy and Alembic — Selected, mandatory:** typed persistence and reviewed migration history. Alternatives: direct SQL, Django ORM. Advantage: explicit transactions and portable migration process; limits: tenant filters and SQL correctness are not automatic. Depend on PostgreSQL driver and compatible versions. Additional migration/test maintenance; no automatic shared-database application.

## Frontend
- **Next.js and TypeScript — Selected, mandatory in Phase 09:** typed web review workflows, routing and shared UI. Alternatives: Vite React SPA, native mobile. Advantage: web-first reach; limits: server/client boundaries, session security, generated types, and runtime payload validation require care. Depends on supported Node.js and selected package manager. Hosting cost and build resources to measure; avoid premature frontend setup.
- **Tailwind CSS and shadcn/ui — Selected, mandatory baseline:** consistent review forms and accessible component foundation. Alternatives: plain CSS, other UI kits. Advantages: reusable styles/components; limits: accessibility still needs testing and copied components need maintenance. Depend on compatible React/Next.js and build tooling. No paid service required by design; verify component licenses and upstream changes.
- **React Native/Expo — Candidate, future enhancement:** only if evaluated web workflows justify native access. Alternative: responsive web. Extra platform maintenance/build cost; no Phase 00/01 adoption.

## Data and storage
- **PostgreSQL — Selected, mandatory:** authoritative structured patient/study records, revisions, transactions, audit and job metadata. Alternative: document database. Advantages: constraints and transactional consistency; limits: access policies and backups need explicit design. Depends on reviewed schema and driver. Local container first; hosting, encryption, backups, and operations require budgets and approval.
- **TimescaleDB — Selected, Phase 02 baseline subject to verification:** time-series management within PostgreSQL. Alternative: ordinary partitioned PostgreSQL if extension compatibility/licensing fails and change is approved. Advantage: CGM-oriented time-window operations; limits: extension version, license/edition, retention semantics, backup and PostgreSQL compatibility need review. Adds database operations complexity; do not assume every feature is freely available.
- **pgvector — Selected, Phase 05:** derived embedding similarity in PostgreSQL. Alternatives: exact SQL features, standalone vector store. Advantage: scope metadata near canonical data; limits: approximate search recall and filtering may interact. Depends on PostgreSQL/extension/embedding-dimension compatibility. Index memory, build time, and storage must be benchmarked; not a second record authority.
- **Neo4j — Selected, Phase 05:** derived relation traversal and explainable episode links. Alternative: SQL adjacency/join queries. Advantage: explicit graph paths; limits: cross-store consistency and edition/license questions. Depends on canonical revision/outbox mapping. Extra process and memory cost; assess value against SQL-only baseline without silently removing the selected component.
- **S3-compatible object storage — Selected, provider pending:** governed images and model artifacts; alternative: local adapter for synthetic development. Advantage: reference-based large objects; limits: provider-specific APIs, encryption, lifecycle, signed access and egress. Depends on approved residency/retention/identity controls. Cost depends on capacity/requests/egress; no provider or deployment settings selected.

## ML and data validation
- **PyTorch — Selected research baseline, install only when needed:** vision/time-series training flexibility. Alternatives: TensorFlow, classical-only models. Advantages: broad model tooling; limits: GPU/macOS acceleration and determinism differ by backend. Depends on supported Python/hardware and licensed weights. Large install/compute footprint; no Phase 00 installation.
- **scikit-learn — Selected for baselines:** preprocessing, classical comparisons and metrics. Alternative: custom NumPy routines. Advantage: reproducible simple baselines; limits: avoid leakage from fit-before-split preprocessing and default metrics. Depends on scientific Python wheels. CPU-friendly baseline, still needs memory/runtime measurement.
- **XGBoost — Selected comparison tool, adoption at forecasting phase:** tabular lag/context benchmark. Alternatives: linear model, random forests. Advantages: strong structured-data candidate; limits: not inherently temporal or calibrated, no superiority assumed. Depends on lag feature schema and compatible wheels. CPU/GPU and tuning cost must be budgeted.
- **ONNX Runtime — Selected inference option where compatible:** artifact execution separated from training. Alternative: native PyTorch inference. Advantage: potential portability; limits: export/operator/precision/uncertainty parity must be tested. Depends on model export and runtime provider support. Benchmark before adopting; maintain native evaluation reference.
- **MLflow — Selected experimentation register:** config, metrics and artifact lineage. Alternatives: versioned manifests, other trackers. Advantage: comparable runs; limits: tracking store/artifact security and operational overhead. Depends on approved artifact paths/backing store. Start local with synthetic/de-identified metrics only; no uncontrolled hosted export.
- **Pandera — Selected data-validation tool:** offline dataframe contracts and missingness/range checks. Alternative: explicit pandas/Pydantic checks. Advantage: dataset-level validation reports; limits: it does not establish clinical correctness or consent. Depends on compatible dataframe engine and scientific stack. Test size/runtime before using on large cohorts.
- **Sentence Transformers — Selected embedding tooling for Tier 2, model pending:** reproducible episode embeddings. Alternatives: structured features, lexical retrieval. Advantage: candidate semantic similarity; limits: model/weight license, clinical semantics, memorization and dimensionality. Depends on PyTorch/tokenizer and approved model manifest. CPU/GPU inference and index rebuild cost; no assumed dataset access or protected text sent externally.

## Model candidates, not selections
- **EfficientNet-B0:** food classification candidate; compare to simple transfer-learning baselines. Limits: meal mixtures, domain shift and weight/data licenses; depends on curated labels and image preprocessing. Fine-tuning compute measured in Phase 03.
- **YOLO segmentation:** multi-food segmentation family candidate, exact implementation/version unset. Alternative: other instance segmentation models/manual regions. Advantage: joint localization; limits: training labels, occlusion, and distribution/weight licensing need verification. No license entitlement implied by the family name.
- **Gemini multimodal models:** optional portion/food research candidate against locally evaluated alternatives. Limits: image scale ambiguity, provider changes, hallucinations, data processing terms and metered cost. Requires approved external-data governance and model/version recording. No protected uploads or subscription assumed.
- **Persistence, linear/statistical models, GRU/LSTM, TCN, Transformers, physiology-informed hybrids:** forecasting comparison ladder. Simple models mandatory baselines; advanced models research candidates. Compare patient/time splits, uncertainty, subgroup error, compute and latency; never assume complexity improves performance. No architecture-specific implementation or pretrained weights selected.

## Infrastructure, verification and observability
- **Docker Compose — Selected local integration design:** reproducible multi-process development when needed. Alternative: native processes. Advantage: small-team reproducibility; limits: image compatibility, local memory and Docker distribution terms require review. No Kubernetes/Kafka. Actual settings require approval; Phase 00 creates no Compose file.
- **GitHub Actions — Selected future CI:** small deterministic lint/type/test jobs. Alternative: local/manual CI. Limits: runner permissions, untrusted PRs, artifact privacy and usage budget. Pin action revisions and least-privilege tokens in the implementing phase; no workflow configured now.
- **Redis and background workers — Optional, need demonstrated queue/cache requirement:** bounded asynchronous tasks. Alternative: synchronous work or simple PostgreSQL-backed jobs. Advantage: decouple expensive tasks; limits: duplicate delivery, expiry, invalidation, license/version review, extra operations. Canonical state stays in PostgreSQL. Never cache across patient/cutoff boundaries.
- **pytest, Ruff, mypy — Selected Python verification baseline:** behavior, formatting/lint and type checking. Alternatives: unittest, other linters/checkers. Advantage: fast deterministic feedback; limits: tests need meaningful clinical/scope fixtures, types do not prove safety. Depend on pinned Python/plugins. CPU CI cost; exact commands/configuration in Phase 01.
- **Playwright — Selected frontend verification:** human-review and abstention workflows. Alternative: manual browser checks alone. Advantage: repeatable end-to-end evidence; limits: browser/toolchain size and flaky timing. Depends on web/API synthetic fixtures. Install at frontend phase; no browser download for Phase 00 docs.
- **Structured logging, OpenTelemetry, Sentry — Selected observability direction; external export conditional:** operational visibility. Alternatives: logs/local metrics only. Advantages: correlated failures/latency; limits: telemetry can leak health data and identifiers. Redaction, sampling, consent and export governance precede integration. Sentry hosting/plan, OpenTelemetry collector and telemetry residency are pending; measure volume/cost.

## Phase 01 verification queue
Choose supported Python minor and package manager, propose exact FastAPI/Pydantic/SQLAlchemy/Alembic/testing pins, check licenses and macOS/Linux compatibility, and document reproducible installation. Review PostgreSQL/TimescaleDB/pgvector combinations before Phase 02; graph edition and weight/provider terms before their feature phases. None of these questions is settled by naming the technology.


## Phase 01 exact dependency register — 2026-11-01
Observed environment: Python 3.12.14 on macOS arm64, Node.js 24.11.1, npm 11.6.2, uv 0.13.6. `uv.lock` resolves Python runtime/test transitive packages with hashes; `package-lock.json` records npm workspace versions/integrities. All direct dependencies below are pinned in manifests; no ML/database client stack is installed. Linux compatibility is configured for CI but not verified by a hosted run. Dependency license labels below come from installed package metadata, not a completed legal/transitive-license audit.

Python runtime and build:
- FastAPI **0.162.0**, MIT: API routing and OpenAPI.
- Pydantic **2.14.2**, MIT: typed response and principal validation.
- pydantic-settings **2.16.2**, MIT: environment configuration validation; separate settings package is required by the selected FastAPI/Pydantic approach.
- Uvicorn **0.54.0**, BSD-3-Clause: loopback ASGI server without access logging.
- Starlette **1.10.0**, BSD-3-Clause: directly used HTTP exception/response middleware interfaces; also FastAPI's resolved transport dependency.
- Hatchling **1.33.0**, MIT: editable/wheel package build backend, exact pin in the API build-system section. uv build isolation uses this pin; build-tool transitive pins are not a full reproducible-build attestation.

Python engineering tools:
- pytest **9.2.0**, MIT: deterministic backend, failure and contract tests.
- httpx2 **2.16.0**, BSD-3-Clause: test transport required by the installed Starlette release; the initial legacy httpx adapter emitted a deprecation warning and was removed.
- Ruff **0.17.3**, MIT: lint/import sorting and formatting.
- mypy **2.4.1**, MIT: strict typing.
- uv **0.13.6**, MIT/Apache-2.0 upstream tooling: isolated dependency management/bootstrap; not an application dependency.

Frontend runtime:
- Next.js **16.4.3**, React/React DOM **19.3.1**, MIT: minimal local App Router shell and real readiness UI; no shadcn/ui package needed for this bounded shell.
- `@t1d/shared-contracts` **0.1.0**: private workspace source, generated from backend models; no third-party patient schemas.

Frontend build and verification:
- TypeScript **7.0.2**, Apache-2.0: strict cross-layer type checking.
- Tailwind CSS and `@tailwindcss/postcss` **4.3.3**, MIT: responsive shell styling/build plugin.
- ESLint **10.14.0** and eslint-config-next **16.4.3**, MIT: linting including React/accessibility rules. Next's transitive lint chain still includes a deprecated ESLint 9 copy.
- `@types/node` **24.19.2**, `@types/react` and `@types/react-dom` **19.3.0**, MIT metadata: compile-time platform/React definitions.
- Vitest **5.0.5**, jsdom **27.0.1**, Testing Library React **16.3.3**, Testing Library jest-dom **7.0.1**, MIT: loading/success/error/retry and malformed-response tests without installing browsers. jsdom 30 required a newer Node patch than installed; 27.0.1's published Node engine was verified compatible. The transitive whatwg-encoding package emits a deprecation notice.

## Verification references and residual dependency risk
Used official [FastAPI settings guidance](https://fastapi.tiangolo.com/advanced/settings/), [uv installation documentation](https://docs.astral.sh/uv/getting-started/installation/), [Next.js installation documentation](https://nextjs.org/docs/app/getting-started/installation/) and actual npm registry metadata/installed package metadata for release and compatibility selection. Next.js build does not replace a separate ESLint run. Installed CLI help verifies the supported `--webpack` option; it is selected after Turbopack's internal socket failed under this execution environment.

`npm audit` returned **16 moderate development-tool findings** propagated from [minimatch globparts amplification](https://github.com/advisories/GHSA-g3hv-75wg-m249); no high/critical findings were reported. `npm audit --omit=dev` returned **zero runtime advisories**. The suggested automatic fixes included incompatible major downgrades, so no force fix or broad major-version override was applied. These findings remain open, not waived or hidden; keep glob inputs controlled, monitor upstream fixes, and rerun the lint/test/build suite for any update. Audit output is point-in-time registry evidence, not a security guarantee.

`npm ls --depth=0` after clean installation lists all direct versions consistently. npm also reports two optional native-support packages (`@emnapi/runtime` and `@img/sharp-wasm32`) as extraneous on this machine; the command exits successfully after clean `npm ci`, and they are neither direct application dependencies nor project source. Platform-specific optional installation behavior needs Linux CI confirmation.

No TimescaleDB/pgvector image combination is claimed compatible. See the [optional infrastructure guide](../infrastructure/docker/README.md) for verified tag leads, plain PostgreSQL fallback, missing Docker checks, credentials and digest limitations. Software names in the Phase 00 register above remain research directions, not blanket adoption approvals.
