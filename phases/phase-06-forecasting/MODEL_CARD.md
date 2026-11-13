# Model card — synthetic four-horizon forecasting v1

Date: 2026-11-07. Status: synthetic research engineering qualification only.

## Intended use and exclusions

Demonstrate reproducible prediction at 30/60/90/120 minutes from canonical,
known-by-cutoff CGM. The API permits only approved sources marked synthetic.
No real-data accuracy, clinical validity, treatment readiness or dosing claim.
No automatic insulin actions, treatment thresholds, meal/insulin/activity effects,
personalized adaptation or Phase 05 retrieval-enabled forecast improvement.

## Data and protocol

Authored positive oscillating mathematical signals, not a physiological simulator
or third-party dataset. Forty fictional patients, 16 windows each: patients 1–20
fit, 21–30 calibrate, 31–40 held-out test. Patient groups are disjoint and their
calendar ranges are chronological; the complete 120-minute label window of an
earlier partition precedes every cutoff in the next. Labels are generated future
signal values and never enter input features. No model selection or hyperparameter
search uses test outcomes. Test windows are correlated within patient.

Features: intercept, latest glucose/100, mean glucose/100, observed OLS slope/10,
population standard deviation/100, age of latest sample/5. Twelve observations on
an exact five-minute grid, latest age at most five minutes, all availability at
or before cutoff. These are fixed technical research profile choices, not clinical
eligibility thresholds. No interpolation or fabricated missing context.

Persistence uses the last reading. Linear trend projects the observed OLS slope
to cutoff plus the requested horizon, accounting for observation age. Ridge uses
six coefficients per horizon, fixed penalty 0.1 including intercept, fit only on
training patients with partial-pivot elimination. No additional runtime dependency
beyond the existing Pydantic pin; no pickle or arbitrary code/model loading.
XGBoost/deep sequence models are deferred until suitable permitted data supports
meaningful comparisons; complexity is not evidence of benefit.

## Uncertainty and results

For each model/horizon, take each calibration patient's largest absolute residual
across its 16 windows, then the ceil((n+1)*0.9)-th order statistic over ten independent
patient units. Symmetric intervals use this radius. The nominal level is 90%,
not a clinical guarantee or a statement of empirical coverage for any subgroup.
The small calibration/test cohorts and artificial generator severely limit inference.

Observed synthetic MAE in mg/dL, from the initial deterministic run:

| Model | 30 min | 60 min | 90 min | 120 min |
| --- | --- | --- | --- | --- |
| Persistence | 4.82 | 8.63 | 11.30 | 13.85 |
| Linear trend | 4.09 | 9.13 | 15.17 | 21.48 |
| Ridge candidate | 3.40 | 6.24 | 8.87 | 11.23 |

The evaluator also reports RMSE, signed bias, interval width, window coverage,
whole-patient coverage and predeclared observed-trend-sign subgroups. Whole-patient
coverage is only 0.8 for persistence at 30 minutes and ridge at 60 minutes in this
held-out cohort, despite nominal 0.9. Do not hide these misses or retune on this test
set. A new modeling/calibration decision needs a new version and untouched test data.

## Serving, lineage and failure handling

A content-addressed packaged JSON resource is checked against a code-pinned SHA-256 before
use; all coefficients and radii are finite and schema validated. LF line endings
are enforced for digest stability. The generator and weights are authored here;
no pretrained artifact or dataset license is introduced. Regeneration is explicit:
`uv run python scripts/evaluate_forecasting.py --write-bundle`. This overwrites only
the explicitly synthetic package artifact/manifest and must be reviewed. Prior artifact files are retained; new bundles use their SHA-256 in the filename.
Normal evaluation does not modify artifacts. Floating math libraries can differ slightly
across platforms; tests compare refitted parameters within 1e-8, while the frozen
release file has exact byte integrity.

Current principal expiry/roles, scoped grant and consent are checked before/after
inference. Latest known revisions are resolved before time/quality filtering;
quarantined or missing readings cause abstention, never revival of predecessors.
Policy v2 explicitly permits only SOURCE_RECORDED_AFTER_EVENT and
INGESTED_AFTER_SOURCE_RECORDING recording warnings, preserving their flags in
input lineage and disclosing warning retention in the output. Unknown or
inconsistent quality flags remain blocked. Phase 02 marks ordinary delayed
ingestion as warning; treating every warning as invalid made the first API
implementation unusable. Positive integration assertions remain unchanged.
Recent source approval is checked again after prediction with ORM refresh enabled.
Missing/irregular/stale/ambiguous history, nonsynthetic sources, withdrawn sources
and nonpositive/nonfinite predicted intervals cannot yield eligible predictions.
An audit records the forecast ID, profile and content hash reference. The response
includes the canonical source revision IDs, cutoff and bundle digest. The content
hash is a reference, not a separately persisted copy of health records; canonical
revision retention is required to reconstruct it. There is no forecast cache.

Known bounds: 500 candidate observations in a 65-minute scoped query; exceeding
this returns unavailable. This is a bounded small inference workload, not a
production load/concurrency benchmark. No OOD calibration or subgroup coverage
guarantee exists. The research profile deliberately rejects irregular sampling;
real-device tolerance/resampling requires independently evaluated new profiles.

## Completion limits

Working software, synthetic comparisons and executed integration tests establish
an engineering slice. Full research acceptance still needs permitted CGM/context
data, prespecified targets, independent expert review, larger patient/time-separated
evaluation, robust interval calibration, subgroup/shift analysis and realistic
service benchmarks. Real-data serving must not be enabled by relabeling records
as synthetic. Forecasts are experimental and require human review.
