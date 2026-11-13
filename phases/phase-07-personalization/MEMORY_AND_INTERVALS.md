# Phase 07 meal-memory and uncertainty comparisons

The comparison reused the initial Phase 07 warm and cold evaluation windows,
development participants, and interval-calibration participants. The Phase 06
model weights and original Phase 07 point profiles supplied the reference.

## Meal memory

The offline adapter uses the carbohydrate-distance component from Phase 05
structured ranking. Ohio meal rows contain carb amounts, meal type, and time.
AZT1D provides carb amounts and pump events. PhysioCGM supplies CGM only in the
approved files. The approved datasets lack the confirmed food identities and
complete meal totals needed for Phase 05's full structured, vector, and graph
profiles. The shared scoring component was also checked using the canonical
Phase 05 episode builder and ranker with fictional, complete meals.

A query needs a single positive recorded carbohydrate entry within the previous
two hours. The candidate search uses the participant's earlier eligible
forecast errors and uses a maximum of one forecast per earlier meal. Carb
amount and elapsed time since the meal determine rank. All feedback must be
available at the query cutoff under the study's event-time replay assumption.
The blend uses three to five matched earlier meals and bounds the total
correction to ±15 mg/dL. The routed candidate preserves the reference
prediction for every query without support. A horizon switches only if the
development gain reaches 0.1 mg/dL.

| Test split | Windows with retrieved meals | 120-minute MAE with context | 120-minute MAE with meal memory |
| --- | ---: | ---: | ---: |
| Pooled | 1,305 | 37.73 | 37.85 |
| OhioT1DM held out | 1,122 | 38.57 | 37.73 |
| AZT1D held out | 7,468 | 36.61 | 36.34 |
| PhysioCGM held out | 0 | — | — |

These MAEs in mg/dL compare exactly the windows with retrieval support.
Development chose routed meal memory for the pooled 120-minute horizon. On
the full warm test it raised MAE from 30.0064 to 30.0288 mg/dL. Results vary
by cohort and the evidence favors the initial Phase 07 point model for the
offline demo.

## Personal uncertainty

The interval comparison holds the original Phase 07 point forecasts fixed.
The adaptive scale combines the independently calibrated constant radius with
the 80th percentile of each participant's recent absolute Phase 06 forecast
errors. The past errors use the same 14-day cutoff and feedback checks as
point adaptation. The normalized residual quantile is fit on calibration
participants. When local error history or calibration support is insufficient,
the interval uses the constant radius.

Coverage measures how often observed CGM fell inside the range. Width
measures how much uncertainty the range presents. The interval score penalizes
both wider ranges and missed observations. All results are retrospective
offline research from the existing cohorts.

| 120-minute test split | Constant coverage | Personal coverage | Constant width (mg/dL) | Personal width (mg/dL) |
| --- | ---: | ---: | ---: | ---: |
| Pooled | 91.36% | 92.04% | 137.50 | 131.87 |
| OhioT1DM held out | 83.70% | 87.96% | 129.80 | 145.33 |
| PhysioCGM held out | 93.03% | 93.11% | 144.47 | 145.08 |
| AZT1D held out | 90.68% | 90.32% | 138.34 | 134.22 |

The pooled 120-minute interval score improved from 167.93 to 162.30. The
Ohio score improved from 216.46 to 210.42. Ohio's 120-minute coverage stayed
below the nominal 90% target. The fixed point forecasts and constant-width
results matched the original Phase 07 benchmark in all four splits.

Full nutrient retrieval needs recorded food identities and complete confirmed
meal totals. Physiological inputs such as IOB and ISF need verified treatment
profiles and reviewed modeling definitions. The current evidence supports a
research comparison of historical errors and available carb records.
