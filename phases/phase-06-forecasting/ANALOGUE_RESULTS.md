# Phase 06 forecasts using earlier CGM trajectories

The v5 offline comparison adds observed glucose responses from earlier, similar
episodes in the same participant and source partition. The fixed transform
matches current glucose, trend, variability, recorded clock and recent
recorded meal and bolus amounts. It summarizes observed changes, their
dispersion, matching distance and support. A missingness flag marks windows
without six eligible earlier episodes. No individual model is fitted at
inference time.

An earlier anchor must be within 46 hours, leaving room for the two-hour
matching inputs inside the existing validation embargo. All four outcomes must
have been observed and available at least one hour before the current cutoff.
The source-order check excludes earlier-looking timestamps recorded later in a
stream after a backward clock change. The replay CLI recreates these features
from the supplied history. The real sources use the previously approved
event-time replay assumption for unknown logging availability.

## Evaluation

All 101,514 scoring anchors and the v4 patient partitions were retained.
The frozen v4 model reproduced its reported MAE in every evaluation. We
compared v4 context and CGM-only models, two analogue models trained with
pseudo-Huber and absolute-error objectives, and fixed blends. A second run
tested a small standardized neural network and three blends with the tree
models. Model choices for each horizon were written before scoring held-out
outcomes, with a 0.05 mg/dL development improvement required to switch away
from the frozen baseline. The reused test cohorts make these retrospective
comparisons. A fresh cohort is required to independently confirm them.

### Held-out point forecasts

Pooled patient- and dataset-balanced mean absolute error in mg/dL.

| Model | 30 min | 60 min | 90 min | 120 min |
| --- | ---: | ---: | ---: | ---: |
| Original v1 context model | 14.42 | 23.97 | 30.09 | 34.12 |
| Frozen v4 history model | 13.65 | 22.71 | 28.35 | 31.94 |
| Earlier-trajectory comparison | 13.65 | **22.47** | **28.00** | **31.48** |
| Earlier trajectories with neural comparison | 13.65 | 22.55 | 28.00 | 31.45 |

The tree comparison lowered mean MAE across horizons by **1.08% vs v4** and
about **6.8% vs v1**. The selected 30-minute profile remained v4. At 60, 90
and 120 minutes the pooled selection averaged v4 and the pseudo-Huber analogue
model. The paired 95% patient-bootstrap intervals for change in MAE at those
horizons were −0.30 to −0.17, −0.45 to −0.26 and −0.63 to −0.28 mg/dL.
Earlier trajectories were available in 22,654 of 22,800 pooled test windows.

| Dataset held out | 30 min | 60 min | 90 min | 120 min | Mean reduction vs v4 |
| --- | ---: | ---: | ---: | ---: | ---: |
| OhioT1DM | 14.52 | 25.56 | 33.80 | 39.33 | 0.64% |
| PhysioCGM | 14.42 | 23.88 | 30.56 | 35.06 | 2.56% |
| AZT1D | 13.99 | 22.82 | 28.31 | 31.44 | 1.44% |

The neural comparison improved development scores but raised mean MAE on
the PhysioCGM holdout by 0.49% vs v4. It also raised pooled 120-minute MAE
after recorded exercise following a bolus to 40.04 mg/dL. The offline demo
uses the tree comparison because its held-out improvements were more
consistent across datasets and the exercise subgroup. Individual horizon
profiles were selected using development data in both experiments.

In the pooled exercise-after-bolus subgroup (193 windows, three participants),
120-minute MAE decreased from 38.94 to 38.25 mg/dL. In the Ohio-only holdout
subgroup (403 windows, ten participants), it increased from 36.16 to 36.66
mg/dL. This needs prospective replication with more activity records.
Pooled nominal 90% interval coverage was 90.3% to 90.7% across horizons.
At 120 minutes, coverage was 81.8% on the Ohio holdout. These are offline
research forecasts. The HTTP API continues to use its synthetic profile.

## Reproduction

Use the pinned optional research environment and existing v4 artifacts.
Provide new external output directories for both experiments.

```powershell
python scripts/evaluate_forecast_analogues.py --ohio $ohio --azt $azt --physiocgm $physiocgm --history $v4 --output $v5 --context-availability event-time-replay
python scripts/evaluate_forecast_analogues.py --ohio $ohio --azt $azt --physiocgm $physiocgm --history $v4 --neural-from $v5 --output $v5neural --context-availability event-time-replay
python scripts/predict_research_forecast.py --dataset ohio --source $ohio --participant $subject --models "$v4/pooled" --analogues "$v5/pooled" --context-availability event-time-replay --output $result
```

[Aggregate results](results/analogue-v5-summary.json) contain cohort and
subgroup counts, validation scores, selected profiles, test metrics and
artifact checksums. Raw records, forecasts and model weights remain local.
