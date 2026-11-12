# Phase 07 independent offline qualification

The University of Manchester T1D-UOM v1.0.4 release supplied an independent
retrospective cohort. It was held out from model fitting, profile selection,
and interval calibration. The offline benchmark applies the locked pooled
Phase 06 point artifact and Phase 07 calibration artifact. The warm evaluation
updates each person's correction using that person's matured outcomes only.
[Official T1D-UOM release and citation](https://zenodo.org/records/17361905)

## Data and eligibility

The release is licensed CC BY 4.0. The downloaded archive matched the
publisher's MD5 and is pinned by SHA-256
`f9725405a0761e4e6f51be7a0ea0a221e58afe8eda96ecedb213998cf382526c`.
The reader imports CGM, recorded carbohydrate amounts, and recorded bolus
delivery. It converts glucose from mmol/L with the existing project
conversion. The raw dates parse in chronological order with day-first
formatting. Month-first parsing failed on over 211,000 CGM timestamps.
The source clocks stay local and actual logging availability remains
unverified in event-time replay. Simultaneous ambiguous meal or bolus records
are excluded. No CGM samples are interpolated.

Nine of the 17 participants had eligible uninterrupted five-minute windows.
There were 2,331 cold windows in the first seven days and 28,355 warm windows.
The results apply to the nine eligible participants.

## Forecast and interval results

Mean absolute error in mg/dL on the same warm test windows.

| Model | 30 min | 60 min | 90 min | 120 min |
| --- | ---: | ---: | ---: | ---: |
| Frozen Phase 06 | 14.83 | 24.21 | 29.60 | 32.90 |
| Locked Phase 07 | 14.83 | 24.21 | **29.16** | **32.27** |
| Recorded-event timing candidate | 14.83 | 24.21 | 29.11 | 32.22 |

The recorded-event timing candidate compares earlier errors under recent
carbohydrate and bolus patterns. It distinguishes a recorded event in the
previous hour from one recorded earlier in the four-hour lookback. It also
uses observed CGM direction and recorded activity-after-bolus context when
available. The bins are research features for temporal association.
Estimating IOB, ISF, or treatment response would require verified profile
inputs and reviewed physiological definitions. The timing candidate remains
exploratory. The independent comparison evaluates its fixed recipe without
using this cohort to choose the offline forecast.

| Phase 07 interval | 30 min coverage | 60 min coverage | 90 min coverage | 120 min coverage |
| --- | ---: | ---: | ---: | ---: |
| Constant width | 87.6% | 87.5% | 88.2% | 89.0% |
| Personal width | 88.7% | 88.9% | 89.4% | 89.9% |

The 120-minute mean width moved from 137.5 to 136.9 mg/dL. Coverage is
retrospective and is sensitive to the cohort. The 90% target was only
approximately reached at 120 minutes on this cohort.

## Reproduction and integration scope

The offline forecast command takes history through the most recent eligible
CGM reading, a checksum-verified Phase 06 artifact, and the exported
Phase 07 calibration. It returns forecasts at 30, 60, 90, and 120 minutes
with intervals, research status, model and feedback lineage, and support
flags. The current query has no glucose outcomes attached.

Phase 05 integration tests use the production retrieval service to assemble
and rank fictional, complete meals. The tests round-trip structured, vector,
and hybrid responses through the Phase 07 evidence consumer. Storage and
graph adapters use test fixtures. The current research sources support an
offline carbohydrate-distance comparison. Full confirmed-nutrition evaluation
through live stores and validated physiological profile inputs remain open.

```powershell
.venv\Scripts\python.exe phases/phase-07-personalization/validate_uom.py --source $uom --history "$v4/pooled" --analogues "$v5/pooled" --profile "$phase7/pooled-inference.json" --output $report --context-availability event-time-replay
```
