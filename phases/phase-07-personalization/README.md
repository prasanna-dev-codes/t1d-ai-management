# Personalized & Physiology-Informed Prediction

Owner: Archit. Workstream: `workstream/archit-phases-05-08`.

Phase 07 evaluates personal corrections to the frozen Phase 06
30-, 60-, 90-, and 120-minute research forecasts. It compares the frozen
forecast with a fixed seven-day correction, a rolling 14-day correction, and
a rolling correction conditioned on CGM direction and recorded meal and
exercise context. Corrections use each participant's earlier observed errors.

## Evaluation

The first seven days of each held-out history form the cold-start track.
Warm evaluation starts after that period. For Ohio, only earlier training-file
outcomes supply Phase 07 residual feedback. Warm scoring uses the official
testing files with the existing Phase 06 causal features. In AZT1D and PhysioCGM, earlier scored
outcomes can update later forecasts after the entire outcome window becomes
available. Availability remains unverified under the approved event-time replay.

The development and interval-calibration participants are disjoint and drawn
from the original Phase 06 calibration pool. The test participants and the
underlying Phase 06 weights are frozen. A candidate must improve development
MAE by at least 0.1 mg/dL for that horizon to replace the frozen prediction in
the comparison. The report includes cold-start error, warm error, interval
coverage, feedback availability, and sufficiently populated context and time
subgroups.

See [initial benchmark results](INITIAL_RESULTS.md) for the pooled and
dataset holdout measurements.

The optional meal-memory and personal-interval comparisons reuse the same
chronological splits. The [ablation report](MEMORY_AND_INTERVALS.md) gives
the measured effect of each addition and the available evidence.

The [independent qualification](INDEPENDENT_VALIDATION.md) evaluates the
locked model and interval artifacts on the University of Manchester
T1D-UOM cohort and reports the recorded-event timing candidate.

Corrections are regularized and bounded to ±15 mg/dL as a research model
parameter. The model estimates forecast bias from recorded outcomes.
The Phase 05 service-to-feature path is tested with confirmed synthetic meals
and fixture-backed storage. Verified profile inputs and reviewed physiology
definitions are prerequisites for evaluating insulin on board or insulin
sensitivity. [Phase 07 decision record](../../docs/decisions/010-phase07-offline-adaptation.md)

## Run locally

Use the existing Phase 06 research environment and artifacts. Set the input
variables to the paths from the [Phase 06 benchmark](../phase-06-forecasting/ANALOGUE_RESULTS.md)
and use a fresh output folder outside the repository.

```powershell
.venv\Scripts\python.exe phases/phase-07-personalization/evaluate.py --ohio $ohio --azt $azt --physiocgm $physiocgm --history $v4 --analogues $v5 --output $phase7 --context-availability event-time-replay
.venv\Scripts\python.exe -m pytest -q phases/phase-07-personalization/tests
```

Append `--meal-memory --personal-intervals` and choose a fresh output folder
to run both additional comparisons and export the locked Phase 07 profiles.
Use the pooled profile to forecast from the latest eligible reading in the
source. The output path must be a new file outside the repository.

```powershell
.venv\Scripts\python.exe phases/phase-07-personalization/predict.py --dataset physiocgm --source $cgmCsv --participant $subject --history "$v4/pooled" --analogues "$v5/pooled" --profile "$phase7/pooled-inference.json" --output $forecast --context-availability event-time-replay
```
