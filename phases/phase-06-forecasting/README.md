# Phase 06 — Glucose forecasting

Owner: Archit. Branch: `workstream/archit-phases-05-08`.

Implemented research slice: four-horizon persistence, observed-window linear trend
and a trained ridge candidate; portable SHA-256-checked JSON weights/calibration;
patient-disjoint chronological synthetic evaluation; protected forecast API with
current consent, grants, source approval, revision/cutoff and audit checks.

This bundle is qualified only on fictional data. The API explicitly abstains on
nonsynthetic source types. It cannot provide medical advice or treatment actions.
Read [the model card and evaluation protocol](MODEL_CARD.md) before interpreting results.

```powershell
uv sync --frozen --all-packages
uv run python -m pytest phases/phase-06-forecasting/tests tests/test_forecast_api.py -q
uv run python scripts/evaluate_forecasting.py
uv run python scripts/run_memory_tests.py --tb=short
```

The final command needs Docker and runs actual disposable TimescaleDB/pgvector
and Neo4j integration tests, including Phase 06. Hosted branch CI runs the same
qualification and exports the synthetic evaluation report. No persistent database
is migrated or changed by this implementation; canonical Phase 02 storage and
audit tables are reused.

## API

`POST /api/v1/patients/{patient_id}/forecasts`, authenticated researcher/clinician,
current scoped grant/consent, `X-Study-ID` header. Example body:

```json
{"input_cutoff":"2026-11-07T12:00:00+05:30","horizons_minutes":[30,60,90,120],"model_profile":"persistence-v1"}
```

Use a real applicable cutoff no later than server time; the example is syntax,
not a valid seeded request. Supported profiles: persistence-v1, linear-v1,
ridge-v1. The default stays persistence; no automatic promotion based on test scores.
No client-supplied glucose arrays, weights, model paths, context guesses or doses.
Eligible results include all requested target times, points and intervals in
mg/dL, immutable model/feature/policy versions, input hash and source revision IDs.
Abstentions have data=null and explicit reasons. Identity remains deny-all until
an existing approved authenticator is configured; there is no test bypass route.

Domain code/artifacts/tests live here. API integration, generated shared contracts,
root workspace and real-service tests retain their existing shared locations.
Phase 07 personalization and Phase 08 clinical simulation are not implemented.
