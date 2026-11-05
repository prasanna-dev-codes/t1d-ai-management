# ADR 008: scoped experimental episode retrieval

Date: 2026-11-06. Implemented under the user's Phase 05 instruction on Archit's
branch; main integration still requires review. No clinical protocol, dosing
policy or production deployment is approved by this decision.

Preserve Phase 02 canonical authority, append-only histories, current grants,
consent, RLS and audit. Add manifests/vectors with migration 0003_memory; do not
edit applied migrations. Readiness accepts the existing Phase 02 head or additive
memory head. Memory operations on an unmigrated store fail unavailable; unsafe
roles remain rejected.

Use the frozen research response120/context120 profile in the memory README.
Database-stamped materialization cannot be backdated. Source/definition/summary/
embedding manifests determine content-addressed identity. Canonical reconstruction
detects late records/corrections even when derived projections are stale.

Use deterministic local food feature hashing and exact scoped pgvector similarity
as the reproducible baseline embedding. This is not a neural semantic encoder;
hash collisions and missing synonym generalization are disclosed. A pretrained
semantic encoder needs independent provenance/permission/version and relevance
evaluation. No unsupported superiority claim or model download is introduced.

Neo4j is a scoped derived episode/food/source graph. Filter scope/cutoff on every
traversed node/edge; generation checks reject stale projections. Canonical checks
and authorization repeat after search. Hybrid outage is explicit, with no silent
fallback. Structured retrieval remains a separately requested profile.

Alternatives: global embedding search (unnecessary scope exposure), authoritative
graph storage (conflicting facts), external generative explanations (unnecessary
transfer/hallucination risk), and fitting an encoder on tiny synthetic fixtures
(not scientifically justified). Retain transparent ranking pending independently
judged research relevance.

Real-world relevance, clinical episode definitions, production identity, retention
and forecast benefit remain distinct research/governance questions. Synthetic
precision is never clinical accuracy.
