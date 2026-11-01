# ADR-001: Modular monolith versus microservices

- **Status:** Accepted direction in the Phase 00 project brief; implementation details remain proposed and require review.
- **Date:** 2026-11-01

## Context
A three-student prototype spans five domains but has no existing application or operational team.

## Decision
Use one backend application with independently organized domain modules and optional workers reusing those modules. Keep web, API, domain, adapters, training and inference separated.

## Alternatives
Distributed microservices; one unstructured application.

## Rationale
Module boundaries permit isolated tests while a single orchestration layer reduces deployment, transaction and authentication overhead.

## Consequences
Shared process/resource limits require bounded inference and careful imports; services/ is a code organization convention, not a network boundary. No Kubernetes or Kafka.

## Conditions for reconsideration
Measured independent scaling or organizational constraints justify separation, and an approved ADR includes failure/auth/data ownership changes.

## Verification and approval boundary
[Requirements](../requirements.md), [architecture](../architecture.md), and [roadmap](../roadmap.md) define phase acceptance. No runtime, license, clinical validation, operational setting, or future-phase implementation is approved solely by this record. Changes to shared architecture require explicit approval and an ADR update/successor.
