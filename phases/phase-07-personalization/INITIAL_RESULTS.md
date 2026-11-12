# Phase 07 first offline comparison

The benchmark reused the checksum-validated Phase 06 point models and matched
their original held-out MAE before scoring any personal correction. Phase 07
then scored a cold-start track and a later warm track. Compare methods within
the same track. Phase 06's published full-window averages include different
windows.

## Pooled warm forecasts

Mean absolute error in mg/dL across 15,780 windows from nine test participants.
Development selected the context correction at 90 and 120 minutes and the
frozen forecast at 30 and 60 minutes.

| Method | 30 min | 60 min | 90 min | 120 min |
| --- | ---: | ---: | ---: | ---: |
| Frozen Phase 06 | 13.34 | 21.99 | 27.31 | 30.81 |
| Fixed first-week correction | 13.24 | 21.84 | 27.16 | 30.43 |
| Rolling correction | 13.23 | 21.79 | 26.85 | 30.12 |
| Rolling correction with context | 13.19 | 21.73 | 26.81 | 30.01 |
| Development-selected combination | 13.34 | 21.99 | **26.81** | **30.01** |

Mean error across horizons decreased 1.39% for the development-selected
combination. The pooled cold-start track scored 2,567 windows with the frozen
model. Its errors were 14.42, 23.39, 28.73 and 32.55 mg/dL.

## Dataset holdouts

The underlying Phase 06 model was trained outside each test dataset. The
adaptation used only each test participant's earlier eligible outcomes. Ohio's
official test outcomes were excluded from Phase 07 feedback. Earlier matured
outcomes from the unsplit sources were eligible during warm replay.

| Held-out dataset | Warm test participants | 120-minute MAE before | 120-minute MAE after | Mean MAE reduction |
| --- | ---: | ---: | ---: | ---: |
| OhioT1DM | 12 | 38.95 | 37.92 | 1.87% |
| PhysioCGM | 10 | 34.49 | 30.66 | 8.54% |
| AZT1D | 24 | 31.35 | 30.63 | 1.59% |

At 120 minutes the pooled interval coverage was 91.4% against a 90% target.
The Ohio holdout remained below that target at 83.7%. The pooled
exercise-after-insulin subgroup had fewer than three participants with usable
warm evaluation windows, so it did not receive a subgroup estimate.

These initial results use previously studied datasets and event-time replay
with unverified logging availability. The follow-up
[independent qualification](INDEPENDENT_VALIDATION.md) reports a fresh
cohort and the Phase 05 integration checks. Exercise subgroup evidence and
reviewed physiological inputs remain open.
