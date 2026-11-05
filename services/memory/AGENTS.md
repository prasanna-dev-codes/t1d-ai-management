# Archit's Phase 05 ownership

This directory belongs to Archit's metabolic workstream. Follow root AGENTS.md
and the existing architecture, temporal-integrity and memory-design documents.

- Workstream branch: `workstream/archit-phases-05-08`.
- Archit owns phases 05 memory, 06 forecasting, 07 personalization and 08 safety
  research. Progress one phase at a time. The user's 2026-11-06 instruction
  authorizes Phase 05 and its necessary additive API/persistence/contracts/test
  integration. Exact verification belongs in docs/phase-05-review.md.
- Prasanna owns phases 03 vision, 04 nutrition and 09 frontend. Do not change
  those modules as part of this workstream without explicit coordination.
- Shared contracts, authentication, consent, auditing, database migrations,
  root dependencies, infrastructure and CI require coordinated review.
- Reuse existing meal/history contracts. Do not infer portions, nutrients,
  response windows, missing context, treatment parameters or clinical thresholds.
- No real patient data, datasets, credentials or model binaries in commits.
- Do not equate unit-test success with full Phase 05 completion. Report the
  unimplemented adapters, retrieval/ranking, evaluation and authorization checks.
- Push only when requested; do not merge into main implicitly.
