# Handoff for Prasanna: project-wide metabolic context

Archit requested eleven project-wide factors on 2026-11-07 and authorized necessary
cross-phase changes. This document specifies coordination needs; Prasanna's vision,
nutrition and frontend implementation files were not modified in this change.
See [the factor matrix](metabolic-factor-requirements.md) for complete ownership,
current status, and acceptance criteria.

## Phase 03: food recognition

- Preserve image capture time and source separately from actual meal/event time.
- Return candidate food identities, uncertainty and correction references.
- Image recognition does not establish consumed carbohydrate or meal timing.
- Do not infer insulin type, IOB, ISF, sleep or physiological state from an image.

## Phase 04: portions and nutrition

- Produce carbohydrate grams and other nutrition estimates with versioned food
  references, portion units, uncertainty and component-level lineage.
- Human confirmation establishes a reviewed meal revision, not an earlier
  availability timestamp. Preserve event time, confirmation time and availability.
- Return changes as revisions so retrieval/forecasts cannot reuse stale inputs.
- Missing or unconfirmed estimates stay unknown; zero requires actual evidence.

## Phase 09: context and research review UI

- Present the 30/60/90/120-minute estimates with intervals, model/profile version,
  reference time, missing factors, warnings and abstention reasons.
- Distinguish recorded facts, unvalidated estimates, reviewed parameters and
  unavailable factors. Never render unavailable IOB/ISF or context as zero.
- Add reviewed input flows, once corresponding backend contracts exist, for
  carbohydrate confirmation, activity, sleep intervals, routine, measured weight/
  height or sourced BMI, and verified insulin formulation. Record source/time/units.
- Insulin sensitivity and action-model parameters need provenance and qualified
  review; do not auto-fill them from common formulas or population defaults.
- Pump sleep mode must be labeled device mode, not hours slept. A morning glucose
  pattern is not automatically diagnosed as dawn phenomenon.
- Do not display raw research predictions as treatment instructions. Offline
  local-clock/event-time-replay results must be visibly identified as retrospective
  research, not real-time predictions with verified availability.

## Archit's side

Own canonical context/profile contracts and validation in coordination with shared
Phase 02 storage; phase-specific models/features, factor ablations, temporal
eligibility, provenance and forecast APIs. IOB/ISF, activity interactions and
physiology/dawn-pattern research belong to the reviewed Phase 07/08 workstream.
The current real-data models do not yet implement all eleven factors.

## Message Archit can send

“We added a project-wide eleven-factor requirement matrix. Please keep meal
event/capture/confirmation times distinct, preserve nutrition uncertainty and
revision IDs, and plan UI states for recorded/estimated/missing context. We must
not treat pump sleep mode as sleep duration or unavailable IOB/ISF as zero.
I will handle forecasting/context backend contracts and share implemented API
schemas before frontend integration. See docs/metabolic-factor-requirements.md
and docs/prasanna-phase-handoff.md on my workstream branch.”
