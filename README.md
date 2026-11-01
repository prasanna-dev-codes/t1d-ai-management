# T1D AI — AI-Powered Type 1 Diabetes Management System

Academic research and engineering prototype for three Computer Engineering students. **Current status: Phase 03 dataset-independent vision infrastructure; empirical work gated.** Phase 01/02 foundations and hosted verification are retained in their reviews. The new vision API/UI has no configured live identity provider or evaluated food model; authentication remains fail-closed. No real patient dataset, dosing or deployment exists. See [Phase 03 review](docs/phase-03-review.md).

## Phase 03 decision checkpoint

The approved ephemeral inference/testing UI and synthetic software checks are implemented. The [revised cloud-first proposal](docs/vision-cloud-workflow.md), [10-source assessment](docs/vision-dataset-assessment.md) and [provisional taxonomy](docs/food-taxonomy.md) await dataset/environment decisions. Food-101 is an optional general benchmark; no Indian primary or final class list is selected. No full local corpus, cloud job, weights or substantial training has started. Phase 03 hosted CI is NOT RUN; Phase 04 is not authorized.

## Problem and research objectives
Meal composition, historical metabolic context and future glucose trajectories are uncertain and heterogeneous. The project will investigate how food-image analysis, human corrections, personalized historical retrieval and time-series forecasting can support interpretable research review. Objectives are to measure food/nutrient estimation error, compare leakage-safe 30/60/90/120-minute forecasting baselines, quantify uncertainty and abstention, and make evidence and limitations traceable. Model complexity and historical similarity are not assumed to improve prediction or imply physiological equivalence.

## Clinical safety
Research, simulation and authorized retrospective evaluation only. **Not a clinically validated medical device; outputs must not be used as medical advice or treatment instructions.** No autonomous insulin administration, unvalidated patient-facing dosing recommendations, LLM dosing authority or automatic treatment-parameter updates. Any future insulin-related research estimate requires qualified clinician review and explicit uncertainty, assumptions and missing-data warnings. See [safety and privacy](docs/safety-and-privacy.md); the prototype does not provide emergency coverage.

## Five-tier architecture
1. **Vision-to-Nutrition Intelligence:** image validation, food detection/segmentation/classification, portion and nutrient estimates, confidence and corrections.
2. **Personalized Metabolic Memory:** patient-scoped structured/graph/vector evidence, source lineage and strict knowledge-time cutoffs.
3. **Glucose Forecasting and Personalization:** baseline-led four-horizon forecasts and uncertainty, independent of dosing.
4. **Safety and Clinical Research Simulation:** deterministic eligibility/abstention and conditional restricted protocol research under qualified review.
5. **Human-in-the-Loop Application:** web correction, confirmation, history, experimental forecast review, explanations and research analytics.

Use a modular monolith with independently organized domain modules. PostgreSQL owns structured records; TimescaleDB is its time-series extension, pgvector and Neo4j are derived retrieval indexes, and governed object storage holds binary artifacts. See [architecture and diagrams](docs/architecture.md).

## Planned technology stack
Backend: Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy and Alembic. Web: Next.js, TypeScript, Tailwind CSS and shadcn/ui. Data: PostgreSQL, TimescaleDB, pgvector, Neo4j and S3-compatible storage. Research: PyTorch, scikit-learn, XGBoost, ONNX Runtime, MLflow and Pandera. Verification: pytest, Ruff, mypy and later Playwright. Integration direction: Docker Compose/GitHub Actions; Redis/workers only if justified. Observability: structured logging, with OpenTelemetry/Sentry conditional on redaction and governance approval.

Phase 01 frontend/backend dependencies and Phase 02 SQLAlchemy/Alembic/Psycopg are installed and locked in `uv.lock` and `package-lock.json`; see the exact-version register. The approved isolated database combination is verified locally; ML and later infrastructure selections remain planned. EfficientNet-B0, YOLO, Gemini and advanced time-series architectures are candidates to evaluate. See [technology register](docs/technology-stack.md).

## Repository layout
```text
AGENTS.md                    Repository-wide agent and safety instructions
README.md                    Current status and navigation
.editorconfig / .gitignore   Whitespace and local-artifact conventions
apps/api/                    FastAPI foundation, settings and auth boundary
apps/web/                    Minimal research shell and connectivity state
packages/shared-contracts/   Generated health/error/ingestion receipt schemas and types
services/vision/             Future Tier 1 image domain module
services/nutrition/          Future Tier 1 portion/nutrient domain module
services/memory/             Future Tier 2 retrieval domain module
services/forecasting/        Future Tier 3 forecasting domain module
services/safety/             Future Tier 4 deterministic eligibility module
ml/datasets/                 Future manifests/pipelines; no data payloads in Git
ml/experiments/               Future reproducible experiment definitions
ml/training/                 Future offline training
ml/evaluation/               Future locked evaluation tooling
infrastructure/docker/      Verified optional local PostgreSQL/Neo4j stores
infrastructure/migrations/  Future database migrations
tests/                       Synthetic backend and contract tests
.github/workflows/           Configured CI; hosted execution not yet verified
docs/                        Specifications, review record and ADRs
```
Deferred directories retain `.gitkeep` markers. The five domain services, ML work and clinical database migrations remain unimplemented.

## Development roadmap
The [12-phase roadmap](docs/roadmap.md) defines prerequisites, tasks, deliverables, acceptance, three-developer ownership and approximate durations:

00 Requirements and Architecture → 01 Repository and Backend Foundation → 02 Data Engineering and Database → 03 Food Vision Intelligence → 04 Portion and Nutrition Estimation → 05 Personalized Memory and RAG → 06 Glucose Forecasting → 07 Personalization and Hybrid Modeling → 08 Safety and Clinical Simulation → 09 Frontend and Human Oversight → 10 Integration and Deployment → 11 Evaluation and Research.

Safety gates and tests accompany every feature; they do not wait until Phase 08. No phase progression is automatic.

## Documentation and future development
Start with the [documentation index](docs/README.md), [requirements](docs/requirements.md), [architecture](docs/architecture.md), [development standards](docs/development-standards.md), [ADRs](docs/decisions/README.md), and [Phase 00 review](docs/phase-00-review.md). Read [AGENTS.md](AGENTS.md) before changes. The user authorized Phase 01 and its limited frontend/local-infrastructure scope addition on 2026-11-01. No Phase 02 work is authorized. Do not download datasets, add ML stacks, begin clinical/data features, commit or push implicitly. See the [Phase 01 review](docs/phase-01-review.md).


## Local setup and checks
Prerequisites: Python 3.12, uv 0.13.6, Node.js 24 and npm 11. Docker/Compose is optional; local ARM64 stores are now verified. Run from the repository root:

```sh
uv sync --frozen --all-packages --cache-dir .uv-cache
npm ci
make api
# In another terminal:
make web
```

Web: `http://127.0.0.1:3000`; API: `http://127.0.0.1:8001`. Health: `/api/v1/health/live` and `/api/v1/health/ready`; development OpenAPI: `/docs`. Authentication fails closed. Stop foreground servers with Ctrl-C. `make check-api` runs backend lint/format/types/contracts/tests; `make check-web` runs frontend lint/types/tests/build. CI is configured but has not run remotely.

See [local development](docs/local-development.md) for uv bootstrap, `.env.example` setup, environment variables, CORS, port collisions, exact commands, safe logging, infrastructure startup and troubleshooting. Docker setup and limitations are in the [infrastructure guide](infrastructure/docker/README.md). Local stores require unique ignored development passwords and bind only to loopback. TimescaleDB/pgvector support remains unverified; the supplied fallback is plain PostgreSQL. No actual credentials are committed.
