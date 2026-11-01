# Phase 02 structured research ingestion

The API stores synthetic research events. The default authenticator denies every request; only tests inject synthetic principals. No device connector, login provider, dataset acquisition, inference, dose recommendation or enrollment flow exists.

All patient requests require authentication, an opaque patient UUID in the path, `X-Study-ID`, a current patient/study grant and current consent. Writes additionally require researcher/clinician role and a write grant. POST requests require `Idempotency-Key` (1–128 characters).

Implemented POST resources under `/api/v1/patients/{patient_id}`:

- `/cgm-readings`: `{readings: CGMInput[]}` → `CGMReceipt` with reading IDs.
- `/meals`: `{meals: MealInput[]}` → `MealReceipt` with meal IDs.
- `/insulin-events`: `{events: InsulinInput[]}` → `EventReceipt`.
- `/activity-events`: `{events: ActivityInput[]}` → `EventReceipt`.

Each returns 201, `accepted`, `duplicates`, resource UUIDs, server receipt time and fact-based warning codes. The backend Pydantic models and development OpenAPI are the exact field contracts. Generated TypeScript/JSON schema includes these receipt types; typed history response models are exposed by OpenAPI and currently have no frontend consumer.

Every record requires an aware event timestamp, source event reference, revision, predecessor when correcting, and provenance containing source type/reference/version and recorded timestamp. A separately approved DataSource with matching study/type/version must exist. API bodies cannot assign patient scope, availability time, ingestion time or internal UUIDs. Model/derived source data is quarantined; a model estimate cannot self-confirm a meal. Source registration is privileged local fixture administration, not a runtime endpoint.

Validation is layered: Pydantic rejects extra/missing fields, unsupported units, nonfinite/excess-precision numbers and invalid revision pairs; services enforce time ordering, source registration, current authorization and source-chain identity; SQL constraints, triggers and RLS enforce scoped references, structural ranges and append-only records. Numeric input is decoded directly into Decimal, limited to 28 total digits/12 fractional digits and stored in unscaled NUMERIC. Confirmed meal component totals must equal their declared aggregate; no energy formula or FPU formula is inferred. Portions use grams, nutrients grams/kcal, insulin history U and activity duration minutes with original times retained. Repeating fractional duration conversions carry an explicit approximation flag.

Canonical glucose is mmol/L. Original value/unit are retained. Version `niddk-0.0555-v1` uses Decimal `mg/dL * 0.0555`, supported by [NIDDK's conversion reference](https://www.niddk.nih.gov/-/media/Files/Strategic-Plans/Diabetes-in-America-3rd-Edition/DIA_Conversions.pdf). Forward conversion is exact within supported input precision. Reverse conversion uses 64-digit Decimal precision and explicitly reports inexact rounding; it is not silently substituted for the original measurement. No clinical glucose thresholds, freshness cutoff or forward filling is enabled.

Batches are **atomic**, 1–100 records, with a 1 MiB decoded-body transport limit and 50 components per meal. One rejection rolls back all clinical payloads, batches and outbox changes. The safe error envelope identifies an invalid record index when available and never echoes its value. There is no partial-success ingestion mode or silent record discard.

Idempotency uses actor/study/patient/operation/key hash plus a canonical request digest. Identical replay returns the original receipt only after fresh authorization. Same key/different content is 409. Source identity includes patient/study/kind/source/device stream/source-event/revision; an exact source duplicate returns the existing UUID, conflicting content is 409. Corrections append the next revision with the exact predecessor; no overwrite is permitted. Transaction advisory locks plus SQL uniqueness serialize same-key/source races. All lock/session state is transaction-local.

Outcomes are hard rejection (invalid schema/time/unit/source/scope/conflict), accepted warning (e.g. factual recorded delay or unverified sensor), quarantine (model/derived), and explicitly missing sensor data (null values plus `missing`). There are no approved physiological quality bounds. Quarantined revisions are stored/audited but excluded from ordinary history. Warning codes do not establish forecasting eligibility.

Errors include INVALID_INPUT/VALIDATION_ERROR, INVALID_UNIT, INVALID_TIMESTAMP, MISSING_PROVENANCE, SOURCE_UNAVAILABLE, EVENT_CONFLICT, IDEMPOTENCY_CONFLICT, RESOURCE_UNAVAILABLE, PAYLOAD_TOO_LARGE and DATABASE_UNAVAILABLE/CONFIGURATION. Denied scope returns indistinguishable 404; authentication failure is 401; invalid content 422; conflict 409; dependency failure 503. Malformed JSON is 422. A failed batch has no partial-success receipt. Sensitive database exceptions and validator inputs are suppressed.

See [temporal integrity](temporal-integrity.md), [governance](data-governance.md), [operations](database-operations.md) and [Phase 02 verification](phase-02-review.md).
