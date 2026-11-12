# Phase 05–08 follow-up benchmarks

## Phase 05 memory

The second canonical read still runs after ranking, followed by the authorization
check. If the fresh canonical records compare equal to the initial records,
retrieval can reuse the already validated episodes. A changed read triggers
the existing rebuild and evidence invalidation checks. A regression test
uses independently copied records for the equal case and removes previously
retrieved evidence in the changed case.

On 5,201 synthetic events yielding 200 episodes, the median CPU cost of this
step fell from 103.09 ms for a second build to 6.40 ms for record comparison,
over seven warmed measurements per method. This measures Python work only.
PostgreSQL, pgvector, Neo4j, and request latency were outside the timing run.

The offline meal study adds CGM trend similarity and compares bolus amounts
only when both amounts were recorded. The same eligible historical meals were
used for each ranking recipe. On the 1,305 matched pooled-test windows, the
120-minute MAE was 37.73 mg/dL for the locked forecast, 37.85 for carb-and-age
matching, and 37.90 for the richer ranking. On 3,525 matched UOM windows,
the values were 37.68, 37.91, and 37.61. These datasets support recorded
carbohydrate proxies. Real-world rankings with confirmed food identities and
complete nutrition still need independent judgments.

## Phase 06 15-minute CGM research

The experiment trains on measured observations spaced 15 minutes apart,
selected from uninterrupted five-minute runs in OhioT1DM, AZT1D, and PhysioCGM.
Each window uses eight previous samples, explicit context presence indicators,
and observed labels. It excludes cadence gaps, conflicting timestamps, inputs
known to have arrived late, and misaligned labels. It uses local elapsed time
and event-time replay when logging availability is unknown.

The validation split selected boosted trees with context at all four horizons.
The original test split covers 9 held-out people and 22,271 windows. The
independent native [T1D-UOM v1.0.4 cohort](https://zenodo.org/records/17361905)
covers 8 people and 3,600 windows. The native cohort was excluded from fitting,
selection, and interval calibration for the transferred model.

| Cohort and method | 30 min | 60 min | 90 min | 120 min |
| --- | ---: | ---: | ---: | ---: |
| Held-out decimated, persistence | 16.44 | 26.68 | 33.48 | 38.20 |
| Held-out decimated, trained on decimated data | 14.14 | 23.36 | 29.19 | 32.89 |
| Native UOM, persistence | 9.96 | 16.43 | 21.85 | 26.66 |
| Native UOM, trained on decimated data | 9.80 | 17.64 | 24.50 | 30.31 |
| Native UOM, exploratory native-trained cross-validation | 9.16 | 15.72 | 21.06 | 25.97 |

Values are dataset- and participant-balanced MAE in mg/dL. Persistence
forecasts the latest observed glucose value at each horizon. In the exploratory
follow-up, ridge regression was fit on seven native participants and tested on
the eighth, rotating through the eight participants. The approximate 95%
participant-bootstrap interval for the 120-minute MAE difference was
−1.25 to +0.02 mg/dL. The exploratory follow-up needs a second native
cohort. All 15-minute forecasts are research-only.

## Phase 07 latest forecast and correction routing

The latest-only prediction path computes corrections for the requested cutoff
using the same eligible feedback and the same calculation as full replay.
On 3,402 eligible windows from one PhysioCGM participant, the complete
forecast response matched full replay across four alternating pairs. The
median of three timed runs per method dropped from 4,700.69 ms to 2,754.53 ms
after an initial warm-up pair. Timing includes feature and model work and
excludes loading the source file from disk.

The experimental routing rule uses previously issued forecasts whose outcomes
have matured within the rolling lookback. It switches a horizon back to the
frozen point model when a minimum of 48 comparable past forecasts indicates
that the locked correction raised mean absolute error by over 0.5 mg/dL.
It raised 120-minute MAE from 30.006 to 30.026 mg/dL on the pooled test and
from 32.272 to 32.292 mg/dL on UOM. The locked profiles remain the defaults.

## Phase 08 interval research

The experiment estimates one width multiplier per horizon and observed trend
group using the six original calibration participants and the locked Phase 07
point forecasts. A group with fewer than three calibration participants falls
back to the original personal radii. The partitions and dataset timestamps
follow the same retrospective event-time replay protocol as Phase 07.

| Warm cohort | 60-min coverage, rising CGM | 60-min mean width, rising CGM | 60-min mean width, all windows |
| --- | ---: | ---: | ---: |
| Pooled test, 15,780 windows | 80.15% → 90.17% | 100.73 → 135.13 mg/dL | 98.42 → 95.71 mg/dL |
| Independent UOM, 28,355 windows | 75.26% → 88.16% | 103.20 → 138.44 mg/dL | 101.47 → 98.62 mg/dL |

Coverage is averaged across participants. Mean interval score, which penalizes
both excessive width and misses, improved at all four horizons on both cohorts.
The 90% target remained out of reach in several subgroups. The candidate produced
one additional nonpositive lower bound at 120 minutes in the pooled test, and one
each at 60 and 90 minutes in UOM. It remains an offline candidate. The runtime
output gates and approved research profile are used for every existing API path.

## Reproduce locally

From the repository root, use the existing forecasting environment with
NumPy, scikit-learn, and XGBoost. Supply the four local source paths, the frozen
pooled model directories, and the locked inference profile. Write the reports
outside Git. The reports contain aggregate results.

```powershell
$env:PYTHONPATH = 'phases/phase-07-personalization;phases/phase-08-safety;phases/phase-06-forecasting/src;phases/phase-05-memory/src'
$sources = @('--ohio', $ohio, '--azt', $azt, '--physio', $physio, '--uom', $uom)
.venv\Scripts\python.exe phases/phase-07-personalization/validate_cadence.py @sources --output $cadenceReport
.venv\Scripts\python.exe phases/phase-07-personalization/validate_improvements.py @sources --history $history --analogues $analogues --profile $profile --output $followUpReport
```
