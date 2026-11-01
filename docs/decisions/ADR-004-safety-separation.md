# ADR-004: Separate forecasting from clinical decision support

- **Status:** Accepted direction in the Phase 00 project brief; implementation details remain proposed and require review.
- **Date:** 2026-11-01

## Context
Experimental predictions and uncertain nutrition must not become autonomous treatment instructions. Existing repository rules already prohibit autonomous dosing.

## Decision
Tier 3 emits experimental glucose forecasts only. Tier 4 independently validates eligibility and abstention. Any later clinician-defined protocol evaluation is a separate restricted research simulation requiring explicit approval and qualified review; no patient-facing dose or actuation route.

## Alternatives
End-to-end LLM treatment output; direct forecast-to-dose coupling; dose clipping as safety guarantee.

## Rationale
Deterministic boundaries and traceable qualified oversight prevent model output from becoming dosing authority. This records existing boundaries; it introduces no clinical thresholds or dose formula.

## Consequences
No automatic clinical-setting changes. Incomplete inputs/policies abstain; UI, workers, caches and APIs share gates. Qualified clinical review remains a prerequisite, not evidence already obtained.

## Conditions for reconsideration
Only explicit human authorization and qualified clinical/regulatory review of a new intended use can propose changes; autonomous insulin administration remains outside this project scope.

## Verification and approval boundary
[Requirements](../requirements.md), [architecture](../architecture.md), and [roadmap](../roadmap.md) define phase acceptance. No runtime, license, clinical validation, operational setting, or future-phase implementation is approved solely by this record. Changes to shared architecture require explicit approval and an ADR update/successor.
