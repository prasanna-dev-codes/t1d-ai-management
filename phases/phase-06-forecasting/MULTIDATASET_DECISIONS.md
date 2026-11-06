# Three-dataset forecasting decisions

Owner: Archit. Date: 2026-11-07. This records decisions, not completed training.

- Datasets: full 2018/2020 OhioT1DM raw XML, PhysioCGM and official AZT1D archive.
- Context is included from the first model, with explicit missing-data indicators;
  compare a CGM-only baseline to measure whether context actually helps.
- User approved local elapsed-time processing for offline research. Preserve the
  source clock and mark timezone unknown; do not invent UTC offsets. Check clocks
  within participants and across their streams. Exclude unresolved discontinuities.
- No shared absolute calendar is required across different participants. Live
  ingestion remains separate and requires documented timestamp semantics.
- Context availability is a separate decision: unknown logging time does not
  establish that a meal or insulin record was known at a prediction cutoff.
  User approved explicitly labeled offline event-time replay on 2026-11-07.
  The window builder still defaults to verified availability only; the training
  CLI requires an explicit policy choice and records it in the evaluation and
  input fingerprint. This does not establish actual real-time availability.
- Official AZT1D outer archive verified from the user-provided path. Its inner
  ZIP SHA-256 is 2c6b4183fdc729c708c1b3230ab1988d2c9006dd35729537f2de07f649f0d113.
  The existing working copy matches it exactly.
- Preserve the initial synthetic qualification and current live-serving gate.
  Dataset selection is not evidence of real-data model accuracy or calibration.

Outstanding research choices in the draft pipeline, requiring review before a
real run: cadence tolerance, ambiguous CGM/BGM source handling, source basal-rate
units, temporary basal overrides, held-out dataset protocol, and performance
criteria. Do not silently narrow scope, infer missing context or accept unknown
units. Raw records and trained research artifacts stay outside Git.

## Fixed first experiment

No test results were used to choose these settings. Compare persistence, OLS
trend, residual ridge (alpha 1) and residual XGBoost (200-round maximum,
learning rate .05, depth 5, seed 20261107, four CPU threads, early stopping on
validation only). Fit CGM-only and context variants for both trained candidates.
Optional research dependencies are NumPy 2.5.4 (BSD), scikit-learn 1.9.1 (BSD)
and XGBoost 3.4.1 (Apache-2.0), pinned in the optional research extra/lockfile.
The serving environment retains its existing dependencies and synthetic gate.

Namespace participants by dataset. Fixed hashed participant assignment separates
fit/validation patients from calibration and test patients. Chronological
validation inside fit patients includes a context/label embargo. Supplied Ohio
testing files never fit, select or calibrate a model. In the pooled protocol,
three patients per dataset calibrate and three test; in each external protocol,
all patients of one dataset test and five patients from each other dataset
calibrate. These are new-patient evaluations, not official BGLP leaderboard scores.

Balance fit weights equally across datasets and participants. Select on
validation dataset/patient macro MAE across four horizons. Report all fixed
comparators, without promoting one from test results. Calibrate symmetric radii
using the 90% finite-sample order statistic of calibration-patient maximum
residuals. Report actual coverage and width; cross-dataset shift invalidates
unconditional coverage claims. Bootstrap MAE by patient with a fixed seed.

Preserve original clocks and source order; create segments only with observed
cadence 295–305 seconds and labels within five seconds of each requested horizon.
No glucose interpolation. Use 12 past observations, a 120-minute recorded context
window, and at most one anchor every six observations. Repeated identical
observations collapse; conflicting timestamps are excluded and their gaps break
windows. Unknown basal units stay masked. Active temporary overrides mask the
normal basal rate. Exercise duration cannot contribute before its recorded
interval completes. Unknown context is represented with a numeric placeholder
and a separate observation mask, never asserted to be zero exposure.

AZT1D's mixed CGM/BGM column is retained by the adapter but excluded from the
CGM-only glucose channel because the source does not identify which measurements
are sensor values. Exclusion counts must be reported. All three datasets must
contribute windows or the experiment fails. Prior runs/models are preserved in
separate external output directories. Raw records and research weights stay out
of Git. Source acquisition and adapter behavior are not a clinical validation.
