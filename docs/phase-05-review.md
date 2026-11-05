# Phase 05 implementation and verification register

Date: 2026-11-06. Owner: Archit. Branch: workstream/archit-phases-05-08.

The user authorized implementation, actual execution and branch pushes. No Phase
06 implementation, clinical dosing policy, deployment or main merge is included.

## Delivered software

Versioned episode assembly; reviewed Phase 02 meal/nutrient/CGM/context reuse;
explicit missingness and source lineage; PostgreSQL canonical manifests and
pgvector features; RLS and database-stamped availability; scoped Neo4j graph;
structured/vector/hybrid profiles; canonical rechecks; idempotent rebuild and
tombstones; authenticated/audited API; generated contracts; reproducible evaluation
and disposable actual-service runner. Operations, limits and erasure procedures
are in services/memory/README.md, with ADR 008.

## Executed evidence (final exact-head evidence to be added)

- Local focused memory/API regression: 63 passed at the first complete software
  draft; subsequent lineage/contract refinements need final revalidation.
- Initial full Windows unit run: 137 passed, 3 failed. Authorized memory routes
  were added to the route allowlist, which now passes. Two existing vision tests
  hit Windows symlink privilege/multiprocessing cleanup issues; their code was
  not weakened or modified. Linux hosted regression is recorded separately.
- Hosted implementation commit 49d81d56df8332d29960d0e471ef9315b0c85bff:
  [Research foundation](https://github.com/prasanna-dev-codes/t1d-ai-management/actions/runs/42088799936)
  passed backend, frontend and PostgreSQL/pgvector database jobs. This supports
  only that intermediate commit, not subsequent working-tree changes.
- Actual Neo4j qualification and final exact-head checks are pending here.

## Evaluation interpretation and limits

Authored synthetic corpus: 80 episodes, 25 CGM samples each, 60 historical/20
query episodes. Relevance is exact food overlap, independent of ranking code,
not metabolic equivalence. Report precision/recall/nDCG@5, reciprocal rank and
measured in-process p50/p95 latency. These are not clinical relevance, expert
agreement, full-service latency or forecast benefit measurements.

No claim of perfection/clinical validation. Feature hashing is not a Sentence
Transformer. Context is traced/disclosed, not a physiology model. Real-data
permission, independent relevance judgments, larger patient/time-separated
evaluation, production identity and real-data retention remain research/governance
work. Bounded pools refuse oversized histories. Default identity is deny-all.
Review before advancing to Phase 06.
