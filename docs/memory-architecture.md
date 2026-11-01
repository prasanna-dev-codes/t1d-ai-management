# Tier 2 — Personalized Metabolic Memory

Status: Proposed Phase 05 design. Historical retrieval is evidence search, **not a physiological digital twin**, causal model, or treatment authority. See [data model](data-model.md) and [research evaluation](ml-research-plan.md).

## Canonical events and graph ontology
PostgreSQL owns source event revisions and episode manifests. An episode links an anchor Meal revision, its confirmed NutritionRecord, bounded CGM response records, and known insulin/activity context, with source/knowledge timestamps and a versioned completeness description. Episode windows and required context are **Pending approval**; no undocumented fixed response window is assumed.

Derived Neo4j node kinds: PatientScope, MealRevision, FoodConcept, NutritionRevision, CGMWindow, InsulinEventRevision, ActivityEventRevision, MetabolicEpisode, and ModelVersionReference. Edges: `OWNS`, `CONTAINS`, `MAPS_TO`, `HAS_NUTRITION`, `ANCHORS`, `HAS_RESPONSE_WINDOW`, `HAS_CONTEXT`, `DERIVED_FROM`, and `SUPERSEDES`. Every private node/edge carries patient/study scope, source revision refs, `event_time`, `available_at`, deletion state and derivation version. FoodConcept nodes may share public ontology metadata; traversal from them must never expose another patient's events. Graph is rebuildable and not a clinical source of truth.

## Embedding representation
Create a deterministic, versioned episode summary from approved structured nutrients, food concepts, timing and context with explicit missingness. Avoid free-text identifiers and raw clinical notes. Specify field inclusion, unit normalization, text template, embedding model/version/dimension, training cutoff, and transformation hash. Keep provenance fields filterable rather than relying on semantic text. Summarized outcomes are allowed only when the entire response and annotation were available by the query cutoff. Embeddings are sensitive derived data and cannot be exported to an external provider by default.

Embeddings live in pgvector with canonical episode/revision reference, patient/study, summary/embedding versions, availability time, and tombstone state. Similarity models require evaluation against structured retrieval; nutrient closeness alone does not imply comparable metabolism. Different embedding versions must not share a distance space without explicit validated migration.

## Query and ranking algorithm
1. Authorize actor, study, patient and consent before any candidate enumeration. Resolve an immutable anchor revision and server-validated cutoff.
2. Construct an eligible canonical pool: same scope; event/window end no later than cutoff; all constituent `available_at` values no later than cutoff; confirmation/derivation/embedding availability eligible; no withdrawn, deleted or superseded revisions. Exclude the current target episode and future outcome.
3. Apply structured constraints on documented context, units, meal/review completeness and profile applicability. Missing required metadata excludes candidates, rather than defaulting to known context.
4. Search vector candidates within this restricted scope, then use bounded graph traversals with the same scope/time predicates on every node/edge. Approximate nearest-neighbor overfetch must not leak foreign candidates through counts, logs or diagnostics.
5. Recheck all candidate ownership, time bounds, revisions and constituent lineage against PostgreSQL immediately before use. Exclude stale index entries; derived search filters alone are insufficient authorization.
6. Rank eligible evidence using a versioned configuration of nutrient/context similarity, review quality, completeness and temporal relevance. Weight values and cutoff counts are **Pending approval** after retrieval evaluation; never treat scores as causal confidence or prescriptions.
7. Return only authorized evidence refs, versioned ranking reasons, index watermarks, and explicit unavailable/degraded status. The forecast model must be validated for the available retrieval profile; no silent fallback.

## Leakage example
A meal happened at 10:00, its response window ended at 12:00, and an annotation was entered at 13:00. An 11:00 forecast cannot retrieve the complete episode; a 12:30 forecast still cannot use the 13:00 annotation. A derived embedding created at 14:00 cannot be represented as available earlier in online evaluation. Backfilled study data without original availability times need conservative reconstruction and explicit limitations. Patient-disjoint evaluation also prevents test-patient outcomes leaking through global embedding adaptation or caches.

## Updates, consistency and caches
Canonical transactions append event/confirmation revisions and an outbox reference. Idempotent consumers rebuild affected episode summaries and indexes, preserving availability rather than backdating. Correction/withdrawal marks affected index entries ineligible, invalidates caches and downstream feature snapshots, and triggers lifecycle review of artifacts. Never let a stale vector or graph copy restore a deleted fact. Outbox replay and full rebuild are testable from canonical records.

If caching is introduced, keys include authorized patient/study scope, actor authorization context/version, input cutoff, source revision manifest, retrieval profile, embedding version and policy version. Reauthorization and canonical checks are still required on cache hits. Revoked grants, consent changes, policy revisions and source corrections invalidate eligibility. Cache TTL is not a temporal leakage control.

## Evaluation and failure behavior
Build synthetic relevance judgments plus authorized expert-reviewed research sets when available. Measure precision/recall@k, ranking quality, latency, structured-only comparison and downstream forecast change; report patient/time-split conditions and disagreement in relevance judgments. Correctness tests plant foreign patients, future response windows, late annotations, pending meal confirmations, stale graphs, deleted embeddings and incompatible versions; none may enter returned evidence.

PostgreSQL failure means no authoritative validation and blocks retrieval. Neo4j/pgvector outages may permit only a separately evaluated structured profile with explicit degraded status and compatible forecast model. Otherwise abstain. Limit traversal depth/candidate count after benchmarking to prevent resource exhaustion. No retrieval query may modify clinical settings or supply dosing authority.

## Privacy and oversight
Use least-privilege scoped DB roles, protected object references, encryption, audit of access, consent-bound retention and no public graph browser. Review explanations for inadvertent identifying details. Dataset/embedding model permissions, retention periods, graph schema constraints, ranking weights, deletion of training influence and clinician-reviewed episode definitions remain unresolved before Phase 05 implementation.
