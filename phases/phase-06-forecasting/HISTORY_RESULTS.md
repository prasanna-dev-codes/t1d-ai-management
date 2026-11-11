# Phase 06 offline history benchmark

The v4 profile forecasts glucose at 30, 60, 90 and 120 minutes from observed
history. It adds up to three hours of CGM trends, recurring source-clock CGM
patterns from the previous two days, and recorded metabolic context. The
research CLI emits the four estimates, per-horizon intervals, input lineage
and factor availability. The HTTP API continues to serve the synthetic profile.

## Evaluation protocol

OhioT1DM, PhysioCGM and AZT1D provide the same 101,514 scoring anchors as the
original experiment. Participants are disjoint across training, calibration and
testing. Development validation comes from the later portion of training
participants' records after a two-day history embargo. Three additional runs
each exclude an entire dataset from fitting, selection and calibration. Ohio's
official testing files never enter fitting, selection or calibration.

Compare the frozen v1 context XGBoost artifact against XGBoost with longer CGM
history, longer CGM plus context, and a pseudo-Huber version of the context
model. Two fixed blends are also evaluated. Select the profile with the lowest
dataset- and participant-balanced development MAE before evaluating held-out
outcomes. The standard 30-minute training stride is the default. A sensitivity
run adds 15-minute anchors only to the fitting partition. Validation,
calibration, and test anchors remain identical. Development results were close
between the two strides, within 0.033 mg/dL in all four protocols.

The held-out sets were already used in earlier research. These comparisons
measure retrospective improvement and need replication on an unseen cohort.
Unknown source clocks remain unknown. Context replay uses recorded event times
where actual logging availability is unverified. Completed sleep and activity
intervals and earlier bolus delivery can contribute at the forecast cutoff.

## Forecast accuracy

Pooled held-out balanced MAE in mg/dL, lower is better. Nine test participants
contributed 22,800 windows. The development selection was the history context
model with pseudo-Huber loss.

| Profile | 30 min | 60 min | 90 min | 120 min |
| --- | ---: | ---: | ---: | ---: |
| Frozen v1 context | 14.42 | 23.97 | 30.09 | 34.12 |
| Longer CGM only | 13.80 | 23.16 | 28.81 | 32.34 |
| Longer CGM and context, squared loss | 13.76 | 22.96 | 28.81 | 32.51 |
| Longer CGM and context, pseudo-Huber | **13.65** | **22.71** | **28.35** | **31.94** |

Mean MAE across horizons fell 5.8% relative to v1. Stratified paired patient
bootstrap 95% intervals for the changes were −0.97 to −0.59, −1.69 to −0.96,
−2.79 to −1.08 and −3.74 to −1.14 mg/dL, respectively. These intervals describe
the nine held-out participants. The denser sensitivity run lowered pooled MAE
5.3% relative to v1.

| Entire dataset held out | 30 min | 60 min | 90 min | 120 min | Mean MAE reduction vs v1 |
| --- | ---: | ---: | ---: | ---: | ---: |
| OhioT1DM | 14.61 | 25.69 | 33.92 | 39.72 | 3.0% |
| PhysioCGM | 14.62 | 24.57 | 31.69 | 35.76 | 2.6% |
| AZT1D | 13.99 | 23.06 | 28.83 | 32.09 | 2.7% |

Context contribution varies. The CGM-only history model had lower 120-minute
error than the selected profile on all three external holdouts. In the 193
pooled windows with recorded activity after a bolus (three Ohio participants),
the selected model improved 30-, 60- and 90-minute MAE while 120-minute MAE
rose from 35.6 to 38.9 mg/dL. The ablation compares feature bundles and
training objectives. It cannot isolate the effect of one factor.

Pooled patient-macro coverage of the nominal 90% per-forecast intervals was
90.6%, 90.4%, 90.3% and 90.7%. Mean widths were 63, 103, 126 and 141 mg/dL.
At 120 minutes on the external Ohio holdout, coverage was 81.6%. The model
remains offline research only. Its uncertainty is wide and shifts across
cohorts. The inference path abstains when any lower interval bound falls at
or below zero.

## Factor availability

Pooled held-out coverage measures recorded inputs visible to the feature
transform. Missing inputs are masked. The latest feature profile supports
seven requested factors directly or through recorded history, plus an
exploratory early-morning CGM feature.

| Factor | Held-out availability and interpretation |
| --- | --- |
| CGM | 22,800 windows. Includes short trends, longer history and missingness indicators. |
| Carb intake | 6,678 windows with numeric carb entries in the preceding four hours. |
| Insulin on board | No verified values. Four-hour recorded delivery is a separate feature. |
| Insulin sensitivity factor | No verified individual settings with effective dates. |
| Physical activity | 394 windows with recent self-reported exercise or intensity. Pump mode is modeled separately. |
| Sleep hours | 6,367 Ohio windows had usable wearable intervals, 97.2% of the Ohio windows. The adapter rejected reversed self-report intervals. Overlapping wearable intervals count once. Recorded duration may miss unlogged sleep. |
| Daily routine | 14,336 windows with earlier same-clock CGM patterns or completed work intervals. |
| Dawn phenomenon | 3,962 Ohio windows had a prior completed source-clock 04:00–06:00 CGM pair. This feature describes a glucose change and does not establish dawn phenomenon. |
| Activity after insulin | 193 Ohio windows with completed activity after documented bolus delivery within the four-hour lookback. |
| Weight / BMI | No verified measurements. Ohio's placeholder weight is excluded. |
| Insulin type | 6,522 Ohio windows with a recent delivery and a consistent source-recorded insulin type. The type is categorical context and carries no action curve. |

## Reproduction

Use the pinned optional research environment from the [Phase 06 README](README.md).
The commands below take the same three sources used in v1 and its local artifact
directory. Both output paths must be outside the repository. To reproduce the
sensitivity run, use a new output directory and `--fit-stride 3`.

```powershell
python scripts/evaluate_forecast_history.py --ohio $ohio --azt $azt --physiocgm $physiocgm --baseline $v1 --output $history --context-availability event-time-replay
python scripts/predict_research_forecast.py --dataset ohio --source $ohio --participant $subject --models "$v1/pooled" --history "$history/pooled" --context-availability event-time-replay --output $result
```

The [aggregate results](results/history-v4-summary.json) include model hashes,
factor counts, development and test scores, interval metrics and subgroup
comparisons. Trained research weights and source records stay outside Git.
This experiment does not measure a Phase 05 retrieval contribution. A fresh
cohort with timestamped activity and verified profile inputs is needed to test
the remaining factors and the activity subgroup.
