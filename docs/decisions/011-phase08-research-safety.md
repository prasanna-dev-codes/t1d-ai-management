# ADR 011 — Phase 08 synthetic forecast safety qualification

Status — implemented for the synthetic research workflow on 2026-11-12.

The existing Phase 06 research policy governs source eligibility, CGM
freshness, observed cadence, and artifact qualification. Phase 08 adds a
shared final gate for finite positive ordered points, complete requested
horizons, and exact cutoff-relative target times. The protected forecast API
and local integration demo use the same gate. The API rechecks canonical
readings, authorization, and source approval before audit and response.

The integration exercise consumes the existing Phase 02 meal confirmation
schema and Phase 05 retrieval contract. It verifies canonical evidence
identity, response, source references, cutoff and scope before Phase 07
feedback can use it. A successful empty retrieval permits the evaluated
cold-history branch. An unavailable memory dependency or audit produces an
abstention. Retry re-evaluates from current inputs and authorization.

The comparison uses authored synthetic observations and fixture-backed
storage. Personalization shifts the example forecast and its original
interval bounds. That interval is illustrative for the adjusted forecasts.
The experiment measures software behavior and supports the presentation
handoff to Phase 09.

Clinical simulation is deferred under the roadmap until independent
qualified protocol approval, reviewed settings, uncertainty assumptions,
and reviewer roles are available. This decision implements technical
research checks using existing constraints. It approves no treatment
thresholds, clinical settings, or deployment policy.
