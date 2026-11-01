# Proposed API contracts

Status: Phase 01 health/session routes and Phase 02 structured ingestion/plain-history/audit routes are implemented. Later vision/retrieval/forecast/simulation routes below remain proposals. Exact current fields are Pydantic/OpenAPI models; [ingestion](data-ingestion.md) records the implemented subset and limits.

## Common transport rules
UUID identifiers, UTC RFC 3339 timestamps, explicit units, finite numbers, and versioned provenance are mandatory. Patient routes require authenticated subject, current study/patient grant, and consent; do not trust a body `patient_id` instead of authorization. Foreign or missing resources return indistinguishable `404` responses where appropriate. Research simulation requires additional researcher/clinician scope and an independently approved protocol. Cookies require CSRF protection; the identity/session provider and deployment-specific transport remain **Pending approval**. No bespoke password database is selected.

Mutation requests use `Idempotency-Key` scoped by actor, operation, patient, and request digest; reusing a key for different content is `409`. Revision-changing requests include `expected_revision`; stale revisions return `409` without overwriting. List requests use `cursor` and bounded `limit`; final limits are unapproved. Server time is authoritative for receipt; clients cannot backdate `available_at`. Input snapshots, model version, and cutoffs are selected/validated server-side, never unrestricted client authority.

Errors use this redacted envelope; `details` contains field names/reason codes, never medical values:

```json
{"error":{"code":"INVALID_UNIT","message":"Explicit supported unit required","details":[{"field":"glucose_unit","reason":"unsupported"}],"correlation_id":"00000000-0000-4000-8000-000000000001"}}
```

Common statuses: `400` malformed transport, `401` unauthenticated, `403` forbidden action, `404` missing/inaccessible resource, `409` revision/idempotency conflict, `413` too large, `415` unsupported media, `422` schema/domain validation, `429` rate limit, `503` required dependency unavailable. A valid but scientifically ineligible request returns a documented `200` abstention envelope, not an invented numeric result. Unsupported/unconfigured policy can return `503` when no evaluation is possible. Never return stack traces or object-store credentials.

Experimental output envelope (`ResearchResult<T>`): required `status: eligible|abstained`, `experimental: true`, `input_cutoff`, `safety_evaluation_id`, `policy_version`, `reason_codes: string[]`, `assumptions: string[]`, `missing_data: string[]`, `warnings: string[]`, `review_required: true`, and `data: T|null`. Invalid requests have the error envelope instead. Eligible does not mean clinically safe; it means eligible for the specified research operation.

## Health and authentication
- **GET `/health/live`**: process liveness, no auth, no body; `200 {"status":"alive"}`. Minimal output; `503` if incapable of responding. Does not probe or reveal records.
- **GET `/health/ready`**: minimal readiness, no auth and no sensitive dependency details; no body; `200 {"status":"ready"}` or `503` redacted unavailable response. Required dependencies depend on enabled capabilities; readiness does not certify clinical safety.
- **POST `/auth/session`**: establish a session through a selected external identity adapter; unauthenticated, rate limited. Proposed request `{authorization_code:string, code_verifier:string, redirect_uri:string}`; response `200 {subject_id:UUID, roles:string[], expires_at:timestamp}` plus secure session mechanism chosen during implementation. Validate provider state/nonce, PKCE, allowed redirect, and code replay; `401/422/429/503`. Code exchange semantics are pending provider selection; do not log credentials.
- **GET `/auth/session`**: authenticated, no body; response `200 {subject_id:UUID, roles:string[], expires_at:timestamp}` or `401`. Roles do not replace resource grants.
- **DELETE `/auth/session`**: authenticated and CSRF-protected if cookie-based; no body; `204` revokes local session; `401/503`. No patient data response.

## Meal image submission
**POST `/patients/{patient_id}/meal-images`** — authorized participant/researcher, multipart upload with `image: binary` and `metadata: {event_time:timestamp, captured_at:timestamp, provenance:Provenance}`. Decode safely, validate MIME/content consistency and metadata, strip unnecessary identifying metadata, and enforce approved limits before storing. Response `201 {image_id:UUID, image_object_ref:string, status:"validated"}`; reference is opaque, not a public URL. Errors `413/415/422/503` plus common auth errors. No inference or dosing implied by successful upload.

```json
{"event_time":"2026-10-01T07:00:00Z","captured_at":"2026-10-01T07:00:00Z","provenance":{"source_type":"synthetic","source_ref":"fixture:meal-a","source_version":"1","recorded_at":"2026-10-01T07:01:00Z","transformation_version":null}}
```

## Food recognition and job retrieval
**POST `/patients/{patient_id}/food-recognition`** — authorized meal submitter/researcher; request `{image_id:UUID, event_time:timestamp}`. Validate ownership and image expiry; select approved vision version. Response `202 {job_id:UUID, status:"queued", status_url:string}`. Errors `404/409/422/503`. Synchronous inference may later share the same job/result contract; no unreviewed food is confirmed automatically.

**GET `/patients/{patient_id}/jobs/{job_id}`** — same scope, no body; response `200 {job_id, status:queued|running|succeeded|abstained|failed, result:ResearchResult<Recognition>|null, error_code:string|null}`. `Recognition` has `meal_id`, `meal_revision`, `model_version_id`, `components: [{id, food_label, confidence, portion_value:number|null, portion_unit:"g"|null, uncertainty:object, status:"proposed"}]`. Errors `404/503`. All candidates remain unconfirmed; model confidence is not guaranteed probability. `status_url` always points to this scoped route. Expired outputs cannot be reused without revalidation.

## Nutrition estimation
**POST `/patients/{patient_id}/meals/{meal_id}/nutrition-estimates`** — authorized reviewer/researcher; request `{expected_revision:integer, components:[{id:UUID, food_reference_id:string, portion_value:number, portion_unit:"g"}]}`. Response `200 ResearchResult<{nutrition_record_id:UUID, meal_revision:integer, carbohydrate_g:number, protein_g:number, fat_g:number, energy_kcal:number, uncertainty:object, reference_manifest:object}>`. Missing or unsupported portion/reference yields abstention or `422` for invalid schema; `404/409/503` for access, revision, dependency failures. No experimental FPU formula is selected; any future field requires reviewed definition and no treatment interpretation.

## Meal confirmation
**POST `/patients/{patient_id}/meals/{meal_id}/confirmations`** — authorized human reviewer; request `{expected_revision:integer, nutrition_record_id:UUID, confirmed_component_ids:UUID[], acknowledge_uncertainty:boolean}`. Response `201 {meal_id:UUID, meal_revision:integer, status:"confirmed", confirmed_at:timestamp, nutrition_record_id:UUID, audit_event_id:UUID}`. Reject stale/mismatched components (`409`), incomplete review (`422`), or unauthorized confirmation (`403/404`). Acknowledgement does not override gates or convert uncertain nutrition to ground truth. Append a revision; any later change invalidates dependent feature snapshots.

## CGM and context ingestion
**POST `/patients/{patient_id}/cgm-readings`** — authorized ingestion client/researcher; request `{readings:[{source_event_ref:string, event_time:timestamp, glucose_value:number, glucose_unit:"mg/dL"|"mmol/L", device_ref:string, provenance:Provenance}]}`. Response `201 {accepted:integer, duplicates:integer, reading_ids:UUID[], received_at:timestamp}`; exact retries reuse idempotent response. Batch is atomic; errors identify indexes and reason codes without echoing medical values. `413/409/422/503`. Freshness and clock issues may exclude accepted historical readings from current forecasting; storage acceptance is not eligibility.

```json
{"readings":[{"source_event_ref":"synthetic-cgm-001","event_time":"2026-10-01T07:00:00Z","glucose_value":110,"glucose_unit":"mg/dL","device_ref":"synthetic-device","provenance":{"source_type":"synthetic","source_ref":"fixture:cgm-a","source_version":"1","recorded_at":"2026-10-01T07:01:00Z","transformation_version":null}}]}
```

**POST `/patients/{patient_id}/insulin-events`** and **POST `/patients/{patient_id}/activity-events`** — authorized retrospective ingestion only. Requests `{events:InsulinEventInput[]}` or `{events:ActivityEventInput[]}` use the corresponding [entity fields](data-model.md), excluding server IDs, `available_at`, and revision metadata. Required event times, units and provenance remain explicit. Responses `201 {accepted, duplicates, event_ids:UUID[], received_at}`; atomic batch errors as CGM. These routes record history only; they cannot administer insulin, create recommendations, or infer active insulin. Planned insulin is distinct from delivered exposure.

## Historical retrieval
**POST `/patients/{patient_id}/historical-retrievals`** — authorized researcher/reviewer; request `{input_cutoff:timestamp, anchor_meal_id:UUID, limit:integer, retrieval_profile_version:string}`. Response `200 ResearchResult<{episodes:[{episode_id:UUID, source_revision_refs:UUID[], available_at:timestamp, score:number, evidence_reasons:string[]}], retrieval_version:string, index_watermark:timestamp, degraded_mode:string|null}>`. Cutoff cannot exceed the allowed study/current time. `404/422/503`; no other patient, late annotation, future outcome, or stale revision may survive canonical rechecking. A score means similarity, not physiological equivalence. Any degraded profile must be separately evaluated.

## Glucose forecasting
**POST `/patients/{patient_id}/forecasts`** — authorized research reviewer; request `{input_cutoff:timestamp, horizons_minutes:[30,60,90,120]}`. The server resolves eligible snapshot, model and required context; optional context must be declared in the model schema, never silently assumed. Response `200 ResearchResult<{prediction_id:UUID, model_version_id:UUID, input_snapshot_ref:string, points:ForecastPoint[], evidence_refs:UUID[]}>`; abstained results have `data:null`. Errors `422/503` plus auth errors. `ForecastPoint` is defined in the data model. No insulin doses, prescriptions, or automatic parameter updates.

```json
{"input_cutoff":"2026-10-01T07:00:00Z","horizons_minutes":[30,60,90,120]}
```

Illustrative abstention, not an implemented result or approved threshold:

```json
{"status":"abstained","experimental":true,"input_cutoff":"2026-10-01T07:00:00Z","safety_evaluation_id":"00000000-0000-4000-8000-000000000002","policy_version":"proposed-unapproved","reason_codes":["MISSING_REQUIRED_CONTEXT"],"assumptions":[],"missing_data":["required_recent_cgm_window"],"warnings":["Research only; no treatment instructions"],"review_required":true,"data":null}
```

## Safety evaluation
**POST `/patients/{patient_id}/safety-evaluations`** — authorized research reviewer; request `{operation:"forecast"|"nutrition"|"simulation", input_snapshot_ref:string, input_cutoff:timestamp}`. The service selects the approved policy for the operation; clients cannot choose relaxed thresholds. Response `200 {id:UUID, status:"eligible"|"abstained"|"rejected", policy_version:string, reason_codes:string[], missing_data:string[], assumptions:string[], warnings:string[], review_required:true}`. `404/422/503`. A previous eligible result cannot bypass re-evaluation when inputs/policy change; no standalone medical clearance is provided.

## Restricted research simulation
**POST `/research/studies/{study_id}/simulations`** — researcher plus qualified protocol approval, enabled only after Phase 08 authorization. Request `{patient_id:UUID, protocol_ref:string, protocol_version:string, clinical_settings_id:UUID, input_snapshot_ref:string, input_cutoff:timestamp}`. Response `202 {simulation_id:UUID, job_id:UUID, status_url:string}` using the scoped job route. `403/404/409/422/503`; missing approvals/settings/uncertainty context block execution. Job result is `ResearchResult<{simulation_id, protocol_ref, protocol_version, outcome_report_ref:string, assumptions:string[], uncertainty:object, clinician_review_required:true}>`, accessible only to authorized study reviewers. The protected report may eventually contain investigational protocol comparisons after separate approval; no dose algorithm, patient-facing dose field, actuation, or clipping guarantee is defined here.

## Audit history
**GET `/patients/{patient_id}/audit-events?cursor=...&limit=...`** — explicitly authorized audit reviewer; no body; response `200 {events:[{id:UUID, action:string, resource_type:string, resource_id:UUID, resource_revision:integer, occurred_at:timestamp, outcome:string, correlation_id:UUID}], next_cursor:string|null}`. `403/404/422/503`. Audit read access is itself audited; records are protected metadata and not operational log export. No medical values, tokens, or re-identification data in the response.

## Contract implementation gate
Phase 01 must settle identity/session handling, grant model, validation/error enums, and OpenAPI generation for its limited endpoints. Later phases finalize job expiry/cancellation, upload/batch bounds, supported device profiles, settings approval flows, and retention. No clinical thresholds or exact performance limits are implied by these illustrative schemas. Contract tests must cover ownership, unit mismatch, temporal leakage, idempotency, conflicting revisions, failures, and abstention.

## Phase 02 implemented routes and contract refinements

Under `/api/v1/patients/{patient_id}`, POST/GET `/cgm-readings`, `/meals`, `/insulin-events`, `/activity-events`, plus GET `/audit-events` are implemented. POSTs return CGMReceipt/MealReceipt/EventReceipt; histories return HistoryPage with a validated metadata envelope and JSON payload preserving decimals as strings, plus nullable next_cursor. GET histories require cutoff; limit defaults to 100 and is bounded 1–200. AuditPage is current scoped audit history and does not accept a retrospective clinical cutoff. All require a trusted principal, X-Study-ID and current grant/consent; POSTs also require researcher/clinician role, write grant and Idempotency-Key. The runtime default remains deny-all.

Phase 02 corrections use `revision` and `supersedes_id`, refining the earlier proposed expected_revision field: the exact next revision/predecessor is checked under a source-chain lock. Unknown body fields fail validation. Receipt schemas/types are generated into shared-contracts; no patient UI consumes these yet. Operational limits are 100 records, 1 MiB and 50 components/meal. Invalid JSON/input yields a redacted 422, unsupported/missing units 422, opaque inaccessible scope 404, conflict 409, oversized body 413 and dependency/configuration failure 503. Source/version approval, quality warnings and all-or-nothing semantics are described in data-ingestion.md. No 429 rate limiter or deployment media/upload policy is claimed.


## Phase 03 approved ephemeral vision refinement

[ADR 007](decisions/007-ephemeral-vision-and-cloud-training.md) supersedes the earlier unimplemented stored-image/job recognition proposal for current Phase 03. GET `/api/v1/patients/{patient_id}/vision/model` and raw JPEG/PNG POST `/api/v1/patients/{patient_id}/vision/analyses` use existing principal/current patient-study grant/consent checks; analysis also needs researcher/clinician role and write access. Generated VisionAvailability/VisionResult schemas bind review-required outputs to model/taxonomy/preprocessing identity. No image/job/meal is persisted and no evaluated food artifact is supplied. Exact bounds, denial, unavailable/abstention and audit semantics: [vision inference](vision-inference.md).
