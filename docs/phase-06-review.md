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

## Three-dataset offline extension (2026-11-07)

User approved recorded-context models with missingness masks, unknown-clock local
elapsed-time handling and explicitly labeled event-time replay. The official
AZT1D outer/inner archives were verified against the local working copy; selected
Ohio and public PhysioCGM inputs remain outside Git. The first fixed experiment
completed pooled and three held-out-dataset runs in 144.83 seconds. Full aggregate
results and inference timings are in phases/phase-06-forecasting/results/, with
interpretation in REAL_DATA_RESULTS.md. Raw records and learned research weights
are not committed. Prespecified settings and test limitations are recorded in
MULTIDATASET_DECISIONS.md; no serving artifact or clinical policy was replaced.

Local regression before final packaging: 118 focused Phase 05/06/API/contract
checks passed; subsequent targeted adapter/window/metric/forecast tests passed
41 checks. Strict mypy passed 92 source files; lint/format and generated contracts
match. Actual branch CI is the final software qualification. Wide uncertainty
bands and context degradation on one external dataset are reported rather than
hidden; these results do not establish full clinical/research acceptance.

Commit 1adc429 passed hosted foundation and actual-service qualification:
https://github.com/prasanna-dev-codes/t1d-ai-management/actions/runs/42287772896
https://github.com/prasanna-dev-codes/t1d-ai-management/actions/runs/42287773202
All 16 research model exports across four runs were subsequently verified for
recorded SHA-256, feature dimensions/order and finite four-horizon inference.
Five fictional parameter-validation tests pass. Verification output is committed
as aggregate hashes only; raw records and trained weights remain external.
NEXT_DECISIONS.md records the uncertainty/context/serving questions held for the
user's return. No revised calibration target or live promotion was assumed.

## Per-forecast interval and project-wide factor extension

The user authorized revisions on 2026-11-07. Frozen v1 point artifacts were reused
for exploratory v2 per-forecast intervals; validation residuals fit the scale
learner and distinct calibration patients set quantiles. Previously inspected
test sources are disclosed. Reports preserve external undercoverage. Local
history-only inference completed on actual Ohio source data, with individual
results outside Git. Six hand-calculation/invalid-input interval tests and three
causal-feature/inference tests pass. The eleven-factor matrix is linked as FR-016
and includes a concrete Prasanna handoff. Missing physiological parameters remain
explicit; no treatment policy, Phase 07 implementation or live serving was added.
