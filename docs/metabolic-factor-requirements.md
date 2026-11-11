# Project-wide metabolic factor requirements

User requested these eleven factors on 2026-11-07 for the entire project.
This tracks acceptance and implementation across phases. See the
[Phase 06 history benchmark](../phases/phase-06-forecasting/HISTORY_RESULTS.md)
for measured offline availability and forecast error.

## Factor ownership and current status

| Factor | Source and interpretation | Phase ownership | Current implementation / remaining work |
| --- | --- | --- | --- |
| CGM and trained models | Explicit glucose units, event/knowledge times, device quality and immutable revisions | 02, 06, 07 | Canonical storage, temporal checks and four-horizon offline forecasts exist; real-data live qualification remains separate |
| Carbohydrate intake | Human-confirmed meal revisions or recorded research events, with amount, unit and uncertainty | 03/04 (Prasanna), 02, 05, 06 | Recorded context sums/masks in research pipeline; image-derived estimates must pass confirmation before use |
| Insulin on board (IOB) | Derived estimate requiring delivery history, formulation, reviewed action model and parameters | 07 research, 08 review | Not implemented; recorded bolus/basal features are not IOB; never invent an action duration/curve |
| Insulin sensitivity factor (ISF) | Verified, versioned individual parameter with units, effective interval and review provenance | 02 profile, 07/08 | Not implemented; do not substitute a population heuristic or infer a treatment setting from a forecast |
| Physical activity | Recorded type, start/end, duration/intensity with explicit missingness | 02, 05, 06, 07 | Phase 06 uses recorded duration and Ohio self-reported intensity with masks. A physiological sensitivity effect still needs validation. |
| Sleep hours | Observed/reported sleep intervals with source and completeness | 02, 05, 06/07, 09 | Phase 06 measures elapsed time in valid completed Ohio wearable intervals. Pump sleep mode remains a separate device field. |
| Daily routine | Historical within-person timing of meals, activity and sleep, known by cutoff | 05, 06/07, 09 | Phase 06 uses prior same-clock CGM patterns and completed Ohio work intervals. Meal and activity routine modeling remains open. |
| Dawn phenomenon | Research hypothesis about recurring early-morning glucose patterns with relevant confounders | 07/08 | Phase 06 measures prior source-clock 04:00–06:00 CGM change in Ohio. Interpretation as dawn phenomenon requires independent validation. |
| Activity after insulin delivery | Timing relationship between recorded delivered insulin and later observed activity | 05, 06/07 | Phase 06 models completed exercise after an earlier completed bolus. Long-horizon performance in this subgroup needs further validation. |
| Body weight / BMI | Verified measurement, units, measurement date and provenance; BMI additionally needs verified height or a sourced BMI value | 02 profile, 06/07, 09 | Not implemented in forecast features; Ohio's weight=99 is a documented placeholder and must remain unavailable |
| Insulin type | Verified formulation/type and validity dates, linked to actual delivery records | 02 profile/history, 07/08 | Phase 06 uses Ohio's source type as a categorical feature attached to observed boluses. Verified profile history and action modeling remain separate. |

## Required data semantics

Each enabled factor needs value/unit, source revision, event or effective time,
availability time (or explicit unverified availability), observation status,
uncertainty/review status and provenance. Derived factors additionally need the
algorithm/version, immutable source references and reviewed parameters. Planned,
cancelled and delivered insulin events must remain distinct. Absence is not zero.

Store recorded facts in canonical PostgreSQL; Phase 05 indexes remain derived.
Forecast feature profiles declare precisely which factors they consume. A CGM-only
baseline remains necessary to test added value. Context-enabled profiles must
include observation masks and make unsupported factors visible. Adding a factor
to this requirement list does not create a valid value in any dataset.

Unknown local timestamps remain local in offline research. Glucose and context
alignment must be verified within participant/stream; do not assign UTC offsets
from neighbouring timestamps or use date-shifted months as real seasonality.
Research event-time replay remains explicitly labeled availability unverified.

## Acceptance and evaluation

- Check units, stale/missing values, revisions and temporal eligibility before use.
- Compare factor groups and interactions against the same held-out baselines;
  report effects by horizon, dataset and missingness subgroup, including harm.
- Fit scalers, derived parameter learners and personalization only on eligible
  development histories. Test outcomes and future context cannot enter features.
- Trace each output to the enabled factor profile, input revisions and model.
- Invalid required factors lead to an explicit abstention. Optional unavailable
  factors remain masked only in models evaluated for that missingness pattern.
- The UI distinguishes recorded context, estimated features and unverified or
  missing factors; it must not display unavailable IOB/ISF as zero or certainty.
- User lived-experience review guides usability/scenarios; independent clinical
  review remains necessary for physiological interpretations or treatment protocols.

No automatic dosing, sensitivity adjustment, exercise multiplier or diagnosis is
introduced here. Clinical personalization and simulation remain separate reviewed
phases. Prasanna's implementation modules are unchanged by this requirements update.
