# Architecture — T1D AI Management

Status: Initial scaffold; detailed design to be finalized before implementation.

## Goals
Research-oriented, clinician-supervised Type 1 Diabetes decision-support prototype with explainable inputs, traceable processing, and conservative safety boundaries.

## Proposed logical components
1. **Frontend** — user interface for meal information, glucose/context entry, result review, and uncertainty notices.
2. **API** — authentication, schema validation, request orchestration, audit metadata.
3. **Nutrition pipeline** — food-image classification, human-confirmed portion estimates, nutrition lookup, carbohydrate estimation.
4. **Clinical decision-support domain** — independently testable deterministic logic, explicit clinician-configured parameters, hard safety gates; no autonomous dosing.
5. **Model services** — versioned models, confidence/quality thresholds, evaluation reports, fallback behavior.
6. **Persistence** — minimal necessary data, encryption, access control, retention/deletion procedures.
7. **Observability** — privacy-preserving logs, model/version traceability, test and safety metrics.

## Suggested implementation stack (provisional)
- Frontend: Next.js, TypeScript.
- API: Python FastAPI, Pydantic.
- Database: PostgreSQL with migrations.
- ML inference: Python with ONNX Runtime where appropriate.
- Tests: pytest, API integration tests, frontend tests, safety regression fixtures.
- CI: GitHub Actions with lint, type checking, tests, and secret scanning.

## Trust boundaries
User input and model output are untrusted. All clinical computations require schema, units, provenance, freshness, and safety validation. No LLM is the authority for clinical calculations.

## Open decisions
- Exact module scope and approved clinical references.
- Whether any dosing-related module is permitted, and under what clinician oversight.
- Model and dataset selection, evaluation criteria, deployment environment.
- Privacy/compliance requirements and intended users.

Record decisions in `docs/decisions/`.
