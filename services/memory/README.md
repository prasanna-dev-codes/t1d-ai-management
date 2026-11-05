# Phase 05: Personalized memory and retrieval

Owner: Archit. Branch: `workstream/archit-phases-05-08`. This package retrieves
patient-scoped historical evidence for later forecasting. It does not forecast,
calculate insulin or provide clinical advice. Exact verification and limitations:
`docs/phase-05-review.md`. Design decision: ADR 008.

## Implemented path

Reuse Phase 02 confirmed meals/nutrients and CGM/insulin/activity revisions;
apply current consent/grants/RLS and knowledge-time reconstruction; assemble
versioned episodes; persist immutable canonical manifests and derived pgvector
features; publish a separately rebuildable scoped Neo4j graph; rank evidence;
reconstruct canonical episodes after search and audit before returning results.

`eligibility.py` remains the initial standalone filter. Integrated retrieval uses
canonical reconstruction and full manifest comparison, not client-supplied
`latest_at_cutoff` assertions. Prasanna's food model is not needed for synthetic
development: the existing reviewed-meal contract already supports manual meals.

## Frozen research definition

`research-response120-context120-v1`: response [meal, meal+120 minutes], context
[meal-120 minutes, response end]; >=2 distinct valid CGM instants; first-to-last
observed span >=50% of window; maximum boundary/internal gap <=30 minutes.
Missing samples are never interpolated. Disagreeing simultaneous sensors cause
omission. Agreeing duplicates retain provenance and count once. CGM units are
explicit; mmol/L conversion uses the existing 0.0555 convention. Overlapping
meals and quality warnings are disclosed. Missing activity/insulin means unknown,
not inactivity/zero exposure. Planned insulin is not delivered insulin.

These `EpisodeDefinition` fields are software research parameters chosen under
the user's Phase 05 instruction, not clinician-approved thresholds. The API only
exposes this frozen version. A changed definition needs a new version/hash and
reviewed evaluation. No clinical safety/dosing policy is altered.

## Ranking/embedding manifests

| Profile | Experimental score | Required services |
| --- | --- | --- |
| `structured-v1` | Mean relative macronutrient similarity | PostgreSQL |
| `vector-v1` | 0.5 nutrient + 0.5 food-vector cosine | PostgreSQL/pgvector |
| `hybrid-v1` | 0.5 nutrient + 0.3 vector + 0.2 exact graph food overlap | PostgreSQL/pgvector/Neo4j |

Ties use recent event then UUID; scores are not confidence or physiological
equivalence. Glucose outcomes are not used to score the target. Context events
provide provenance/warnings; ranking does not model insulin kinetics or exercise.

`food-hash64-v1`: NFKC/casefold/whitespace normalization, canonical food-reference
IDs preferred, SHA-256 first 8 bytes modulo 64, nonnegative counts, L2 norm.
No learned weights, training corpus, provider calls, notes or patient IDs enter
the vector. Hash collisions and incomplete food normalization are limitations.
This is a **local feature embedding, not a Sentence Transformer or semantic LLM**.
Profile/embedding/definition/hash/summary identities accompany results/manifests.
Do not mix incompatible embedding versions or infer clinical superiority.

## API handoff

Existing MealInput/NutritionInput/HistoryRecord contracts remain authoritative.
The following additive routes reuse `X-Study-ID`, trusted principals, bounded
exact JSON parsing, redacted errors, correlation IDs and no-store responses:

- POST `/api/v1/patients/{patient_id}/memory/rebuild`, JSON `{}`: researcher/
  clinician plus current write grant. Content-idempotent, preserves prior
  availability timestamps and records each operation in the protected audit.
- POST `/api/v1/patients/{patient_id}/historical-retrievals`: `input_cutoff`,
  `anchor_meal_id` (existing revision UUID), optional `limit` (1-20; default 5),
  `retrieval_profile_version` (default structured-v1). Requires researcher/
  clinician read access and a confirmed accessible anchor.

`RebuildResult`/`RetrievalResult` and request types are generated into shared
TypeScript/JSON contracts. Results declare experimental/review-required status,
profile/definition/hash, revision refs, historical glucose summary, component
scores, reasons, warnings and index watermark. `audit_reference` is the
correlation UUID locating the protected audit; `retrieval_id` identifies its
resource. Empty evidence returns abstained/NO_ELIGIBLE_HISTORY. Graph failure
returns 503 for hybrid; no silent fallback to a different profile.

Cutoff must be explicitly zoned and not future. Database-stamped materialization
is never backdated: older-cutoff online queries may abstain. Retrospective research
reconstruction must not be presented as evidence of historical online availability.
Normal runtime authentication remains deny-all; do not introduce a demo bypass.

## Setup and verification

Python 3.12, existing pinned uv workflow:

```text
uv sync --frozen --all-packages
uv run python -m pytest services/memory/tests tests/test_memory_api.py -q
uv run python scripts/evaluate_memory.py
uv run python scripts/run_memory_tests.py --tb=short
```

The last command requires Docker and runs all database integration tests plus
memory/API/actual-Neo4j tests on disposable RAM-backed containers with random
credentials, ephemeral loopback ports and no persistent volumes. It stops only
its own named containers. The same runner executes in memory.yml on this branch.

Existing persistent development stores need separately reviewed migration to
`0003_memory`; never migrate them implicitly. Existing role/URL guards remain.
Optional graph configuration requires all of `T1D_MEMORY_NEO4J_URI` (loopback Bolt
only), `T1D_MEMORY_NEO4J_USER`, `T1D_MEMORY_NEO4J_PASSWORD`. Use a dedicated governed
local account/database. Adapter-owned constraints/projections use T1DMemory*
labels only. Keep credentials outside Git, outputs and notebooks.

## Lifecycle, bounds and governance

Source corrections, late context and current source approval invalidate stale
identities on read before index rebuild. Rebuild tombstones obsolete manifests;
replay cannot resurrect tombstones. Current consent/grants are always checked.
Graph replacement is atomic per scope and generation-checked. No retrieval cache.

Research bounds: 5,000 visible records per kind, 1,000 episodes per patient/profile,
20 returned evidence items. Overflow refuses rather than silently truncates.
SQL retains five-second statement and existing lock budgets; graph has bounded
connections/transactions. Larger longitudinal histories need evaluated incremental
ingestion. In-process evaluation timings are not full-service latency promises.

Governed erasure: revoke consent/access first to stop reads, then have the
authorized database administrator purge only the selected scope's memory_episodes,
memory_index_state and T1DMemoryEpisode/Food/Source/Scope nodes. Do not erase
canonical histories/audits as a side effect. Rebuild only from permitted records.
Backup retention and actual health-data retention require separate governance;
there is no automatic deletion schedule or claim of erasing backups/training
influence. This memory implementation trains no model on patient events.

## Ownership

Prasanna: 03/04/09. Archit: 05/06/07/08. Shared changes here are only additive
Phase 05 API registration, workspace/dependency wiring, generated contracts,
migration and qualification tests/workflow. Existing applied migrations, vision,
nutrition and frontend implementation remain unchanged. Main merge needs review.
