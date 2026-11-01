# ADR-003: Evidence-based ML model selection

- **Status:** Accepted direction in the Phase 00 project brief; implementation details remain proposed and require review.
- **Date:** 2026-11-01

## Context
Food/nutrition and time-series tasks face domain shift, limited cohorts and uncertain compute. Larger models are not proven superior.

## Decision
Evaluate simple reproducible baselines before advanced models. Use patient/dish-disjoint splits, temporal holdouts, calibrated uncertainty, subgroup reporting and prespecified selection criteria. No model is selected as winner in Phase 00.

## Alternatives
Transformer-first design; choosing pretrained models by popularity; single aggregate metric.

## Rationale
Evidence, reproducibility, failure behavior and resource cost are more useful than architecture complexity alone.

## Consequences
Maintain comparable manifests/evaluations; accept negative results and retain a simple model if warranted. Exact data/model licenses, metrics targets and uncertainty thresholds need review.

## Conditions for reconsideration
New authorized datasets or changed intended use require new evaluation; approved study protocol may revise selection criteria before locked test access.

## Verification and approval boundary
[Requirements](../requirements.md), [architecture](../architecture.md), and [roadmap](../roadmap.md) define phase acceptance. No runtime, license, clinical validation, operational setting, or future-phase implementation is approved solely by this record. Changes to shared architecture require explicit approval and an ADR update/successor.
