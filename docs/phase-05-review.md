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
are in phases/phase-05-memory/README.md, with ADR 008.

## Executed evidence

- Local focused memory/API regression after moving Phase 05 to its own folder:
  65 passed. Ruff lint/format checks and strict mypy (68 files) passed; frozen
  workspace installation resolved the new package location successfully.
- Initial full Windows unit run: 137 passed, 3 failed. The memory route allowlist
  was fixed. Two existing vision tests hit Windows symlink privilege and
  multiprocessing cleanup issues; their code was not weakened or modified.
- Hardened implementation commit `6d2a915d9edc116d4430fdf33eeba12d02e23a0a`:
  [Research foundation](https://github.com/prasanna-dev-codes/t1d-ai-management/actions/runs/42090248829)
  passed backend, frontend and database jobs.
  [Actual-service qualification](https://github.com/prasanna-dev-codes/t1d-ai-management/actions/runs/42090248851)
  passed 54 integration tests against disposable PostgreSQL/TimescaleDB/pgvector
  and Neo4j services, including the authenticated API, lineage, withdrawal,
  tombstones and concurrent rebuild checks.
- The phase-folder reorganization retains this implementation and updates the
  workspace, lockfile, test discovery and CI paths. Exact commit checks are
  available in the branchâ€™s GitHub Actions history; earlier runs above establish
  implementation evidence, not verification of later commits.

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

## Efficiency and evaluation refinement

Implementation commit `f104f0cb600719099c7febfab65f3ed7c2abfa40` passed
[all foundation jobs](https://github.com/prasanna-dev-codes/t1d-ai-management/actions/runs/42096403322)
and [56 actual-service integration tests](https://github.com/prasanna-dev-codes/t1d-ai-management/actions/runs/42096403327).
Local focused tests: 78 passed, including the judged-input CLI round trip,
invalid judgments, patient-cluster uncertainty and inclusive time-window boundaries.
Strict mypy passed 72 files, lint/format passed, generated contracts matched.
See [the efficiency/evaluation protocol](phase-05-evaluation.md) for measured
assembly speedups, verified SQL batching and scientific limitations. A subsequent
regression also covers context payload batching and exact source-version
withdrawal in the same transaction; its exact-head run is in branch Actions.
Research evidence is still synthetic. Better evaluation tooling does not establish
independent real-world relevance or forecast improvement.
