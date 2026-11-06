# Decisions queued for Archit's return

The user is offline and requested independent work to continue, with scope or
tradeoff decisions held for discussion. No response is inferred from elapsed time.

## Uncertainty target

The first protocol used calibration-patient maximum residuals across entire
histories. Its pooled context-model intervals are roughly 389–528 mg/dL wide.
Near-100% window coverage is achieved with low precision; this is not a useful
confidence claim. Keep these results visible as the fixed first experiment.

For discussion: should the next protocol target individual-forecast coverage
rather than covering every forecast of a whole patient? This can produce narrower
intervals, but changes the statistical target and sacrifices a joint-coverage
interpretation. Conditional/scaled residual methods and domain-shift checks may
also be investigated. None guarantees clinical coverage. Do not replace the
current calibration silently or tune against the already inspected test outcomes.
Any exploratory revision must be labeled and independently revalidated.

## Context and external generalization

Context improved pooled XGBoost MAE modestly but worsened external PhysioCGM
performance versus CGM-only. Preserve both candidates. A context-gated strategy
would be a new model decision, not something to choose using these test scores.
Unknown basal units, ambiguous CGM/BGM records, unknown logging availability and
missing context must remain explicit. Additional metadata could resolve some of
these limitations; do not infer facts from absent records.

## Serving transition

Real-data research weights are external offline artifacts with different features
from the existing synthetic API bundle. Their checksums, dimensions and finite
inference were verified; that does not authorize silent live promotion. A serving
transition requires a separately reviewed feature/clock/availability contract,
model-domain and uncertainty eligibility checks and appropriate evaluation.

No Phase 07 work, deployment, personal-data collection, or treatment logic has
been started. The user's lived experience can guide usability and scenario review;
it does not substitute for held-out evaluation or qualified clinical review.
