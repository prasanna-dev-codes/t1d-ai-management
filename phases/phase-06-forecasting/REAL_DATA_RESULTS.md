# Three-dataset offline experiment v1

Executed 2026-11-07 on Archit's workstation. This is retrospective exploratory
research with user-approved unknown-local-clock handling and event-time replay.
Actual logging availability is unverified. These results do not establish live
clinical accuracy or safe treatment decisions.

## Inputs and protocol

Full 24-file OhioT1DM raw XML mirror (2018/2020), ten public PhysioCGM CGM exports,
and the user's official AZT1D archive. The official AZT1D inner archive matches
the working copy byte-for-byte. Raw data and model weights remain outside Git.
See MULTIDATASET_DECISIONS.md for the exact fixed protocol, pins and assumptions.

Eligible windows: Ohio 24,801; PhysioCGM 35,813; AZT1D 40,900. Source order and local
clocks are preserved. No glucose interpolation is used. An ambiguous mixed
CGM/BGM source is excluded from the sensor channel (13,003 observations), leaving
24 AZT1D participants contributing eligible CGM windows. Conflict and cadence
exclusions are reported in results/summary.json; excluded data is not silently
reclassified as reliable CGM.

The pooled run has 28 fit/validation patients, nine calibration patients and nine
held-out test patients. Three further runs each hold an entire dataset out, while
fitting/validating/calibrating on the other two. The validation score selected
XGBoost with context in all four runs. Patient assignment, candidate settings,
early stopping and score definition were fixed before reading test metrics.

## Point prediction results

Pooled held-out patient-macro MAE (mg/dL; lower is better):

| Model | 30 min | 60 min | 90 min | 120 min |
| --- | --- | --- | --- | --- |
| Persistence | 16.52 | 26.86 | 33.73 | 38.47 |
| Ridge with context | 14.47 | 24.56 | 30.86 | 34.79 |
| XGBoost CGM-only | 14.50 | 24.21 | 30.28 | 34.33 |
| XGBoost with context | 14.42 | 23.97 | 30.09 | 34.12 |

External held-out dataset, patient-macro MAE:

| Test dataset | Persistence 30/120 min | XGBoost context 30/120 min |
| --- | --- | --- |
| OhioT1DM | 17.56 / 44.61 | 15.53 / 40.46 |
| PhysioCGM | 16.64 / 37.38 | 15.33 / 36.45 |
| AZT1D | 17.02 / 40.62 | 14.62 / 32.83 |

Context is not uniformly beneficial: on external PhysioCGM, CGM-only XGBoost
achieved 15.17/35.29 at 30/120 minutes, outperforming the context candidate.
PhysioCGM has no recorded numeric meal/insulin fields in these CGM exports.
Do not select the final model using these test results or claim universally
better accuracy from pooling datasets or adding context. Reports include every
candidate, per-dataset scores, bias, RMSE and patient-bootstrap MAE intervals.

## Uncertainty limitation

Calibration uses a maximum residual over all windows of each calibration patient.
This targets a stringent whole-patient outcome, not merely average-window
coverage. For pooled context XGBoost, interval widths at 30/60/90/120 minutes are
approximately 389/528/462/447 mg/dL. Coverage is near 100%, but these bands are too
wide to describe as precise or decision-ready. Symmetric bands can cross zero;
the offline report does not silently clip them or convert them into live outputs.
Nominal 90% coverage is not a domain-shift or clinical guarantee. Better uncertainty
needs a separately specified calibration protocol and new validation; do not
retune against these observed test outcomes and call it independent confirmation.

## Efficiency and artifacts

All four experiment runs, including source adapters/window generation, finished
in approximately 145 seconds. This is one machine/run, not a training-time SLA.
On 100 warmed fictional single-input predictions, the pooled context XGBoost
artifact (~2.85 MB JSON) took about 0.40 ms median / 0.60 ms p95. Ridge context
took about 0.007 ms with a ~5.9 KB artifact. These timings exclude file loading,
feature extraction, database queries, HTTP and network latency. No production
throughput or end-to-end API latency claim follows.

XGBoost JSON reload predictions were checked against in-memory predictions.
Ridge coefficients/scaler parameters are exported as JSON; no pickle is used.
Hashes and full aggregate evaluations are in results/summary.json; model files
remain under D:/Archit/Others/t1d-forecast-research/results/three-dataset-v1/.

## Sources and remaining acceptance work

- OhioT1DM: Marling and Bunescu, 2020, https://ceur-ws.org/Vol-2675/paper11.pdf.
  Inspected mirror: https://www.kaggle.com/datasets/ryanmouton/ohio-data-set.
  Archive SHA-256: 1918d2bf97579102488970a44467d8fd1b5953fb110933569542ef3ec9c99eb8.
  Counts match the publication (2020 testing files include the warm-up hour);
  no official checksums were available to establish exact release identity.
- PhysioCGM: Quamer et al., https://doi.org/10.6084/m9.figshare.28136294.v1.
  Publisher lists CC0; only bounded CGM entries were retrieved, not ECG archives.
- AZT1D: Khamesian et al., https://doi.org/10.17632/gk9m674wcx.1, CC BY 4.0.
  Original user-supplied archive retained unchanged; no raw data redistributed here.

Model development has moved beyond synthetic-only evaluation, but live serving,
useful calibrated intervals, independent clinical review, further robustness and
Phase 05 retrieval-enabled forecast comparisons remain separate acceptance work.
Current context masks reflect recorded events, not verified complete logging.
Dates are not a shared UTC calendar, and unknown timezone/availability metadata
cannot be reconstructed by adding a fictional offset. These artifacts are not
promoted into the live API, whose previous guards and tests remain in place.
