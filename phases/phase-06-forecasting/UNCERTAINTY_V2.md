# Exploratory per-forecast uncertainty v2

Executed 2026-11-07 under the user's permission to revise the uncertainty work.
V1 point models, settings, source windows and original whole-patient intervals
are preserved. This changes the interval target, not point-prediction accuracy.
The test datasets were already inspected in v1; this is exploratory re-evaluation,
not fresh independent confirmation. There was no test-label fitting or method
switching based on test scores. All fixed alternatives are reported.

## Method

1. Reload the frozen validation-selected v1 context model after hash verification.
2. Compare original whole-patient maximum residual intervals with a
   dataset/patient-balanced empirical 90th residual percentile.
3. Fit a fixed residual-scale XGBoost model using chronological validation
   residuals only (100 trees, depth 3, learning rate .05, seed 20261107).
4. Calibrate scaled residual quantiles on separate calibration patients. A
   numerical scale floor of 1 mg/dL prevents division by zero; it is not a
   treatment threshold. Test labels fit neither model nor quantile.
5. Report coverage, patient-bootstrap coverage intervals, average/p95 width,
   interval score, and negative bounds by horizon and held-out dataset.

These are patient-balanced empirical intervals, not distribution-free clinical
or simultaneous patient-level guarantees. Correlated windows and domain shift
remain limitations. Negative bounds are counted in evaluation, not hidden by
clipping; offline inference abstains when any returned interval leaves the
positive glucose domain. A point model can still produce an inappropriate result
outside the evaluated distribution; live serving remains separate.

## Pooled patient-average coverage and average width

| Method | 30 min coverage / width | 60 min | 90 min | 120 min |
| --- | --- | --- | --- | --- |
| Whole-patient v1 | 100% / 389 mg/dL | 100% / 528 | 100% / 462 | 100% / 447 |
| Balanced per-forecast | 90.5% / 66 | 90.4% / 106 | 90.7% / 130 | 91.0% / 146 |
| Scaled per-forecast | 90.3% / 60 | 89.7% / 99 | 90.2% / 124 | 90.8% / 139 |

The narrower intervals give up the original whole-history coverage target. They
are not a free increase in confidence. On external Ohio, scaled patient-average
coverage drops to 86.3% and 84.9% at 90/120 minutes. On external PhysioCGM it is
86.9% at 30 minutes. Full aggregate results, including all alternatives and
confidence intervals, are in results/uncertainty-v2/summary.json. Do not describe
this as consistent 90% external calibration or clinical readiness.

## History-only inference

`scripts/predict_research_forecast.py --help` exposes a local research command
requiring explicit source, participant, model directory, uncertainty directory,
interval method, availability policy and external output path. It uses the latest
12 observed records and past context, never future target readings. The feature
transform is shared with training; source scope, cadence, conflicts, model hashes,
feature version/order, dimensions and finite outputs are checked. The target
reference is the latest observation time, not an invented current UTC instant.

An actual Ohio-source local inference run completed with four research forecasts;
its individual output is retained outside Git. No real patient inference output
is committed. Test fixtures show that twelve observations are enough without
future labels and that the inference transform matches training. This CLI does
not activate a live API or treatment workflow.

## Reproduction

Use `scripts/evaluate_forecast_uncertainty.py --help` with the three explicit source
paths, original v1 artifact directory and a new external output directory. Scale
model JSON/hashes remain outside Git. The run fails if frozen source-window
identities or point-model hashes change. Model reload equivalence is checked.

Next evidence needs include independent prospective/uninspected evaluation,
broader subgroup/shift tests and a separately reviewed real-data serving profile.
The newly requested eleven factors are tracked in docs/metabolic-factor-requirements.md;
this calibration revision does not make unavailable IOB/ISF/sleep/BMI features real.
