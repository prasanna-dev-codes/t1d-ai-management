# Phase 06 engineering verification register

Owner: Archit. Authorized by the user on 2026-11-06; implementation continues
2026-11-07 on workstream/archit-phases-05-08. This is a synthetic research slice.

Delivered: three four-horizon predictors, trained/calibrated immutable JSON bundle,
strict typed contracts, deterministic patient/time-disjoint experiment with bias,
MAE/RMSE, interval and observed-trend subgroup metrics, current-authorized/audited
canonical forecast API, missingness/quality/time abstention and generated contracts.
No applied migrations, Prasanna modules, clinical thresholds or deployment settings
were changed. No real data or third-party weights were acquired.

Verification before initial push: 101 focused Phase 05/06 + API/contract/benchmark
checks passed before adding the artifact integrity test; the subsequent Phase 06
and API/contract selection passed 55 tests. Strict mypy passed 83 source files;
lint/format and contract generation passed. Actual database integration tests run
in branch Actions; exact-head results must be checked before final completion.
The implementation does not claim that unexecuted checks passed.

Read phases/phase-06-forecasting/MODEL_CARD.md for synthetic held-out numbers,
whole-patient interval coverage misses and deferred real-data/retrieval/advanced
sequence-model evaluation. Engineering execution is not full research acceptance.
Only separately permitted real-data evaluation can support external validity.

## Restart audit and correction (2026-11-07)

The user requested a fresh start. Preserve prior commits and recheck requirements
and evidence rather than erase history. Initial commit 15e1c94 passed backend and
frontend CI, but both actual database runs failed the positive forecast assertion:
Phase 02 assigns recording-delay warnings to normal ingestion, while the first
forecast profile accepted only the accepted quality state. This is an integration
bug, not a reason to weaken positive assertions or bypass quality checks.

Policy v2 permits only the two explicit recording metadata warning flags and
preserves them in hashed source lineage. Missing, invalid, quarantined, unknown
or inconsistent quality still abstains. The output discloses warning retention.
An added regression checks equivalent features, changed lineage hash, unknown
warnings and inconsistent accepted-with-flags rejection. All 56 focused Phase 06,
API and contract tests pass locally; hosted actual-service revalidation is required.
New artifact filenames are content-addressed; the initial bundle stays preserved.
