# ADR-005: Web-first versus native mobile development

- **Status:** Accepted direction in the Phase 00 project brief; implementation details remain proposed and require review.
- **Date:** 2026-11-01

## Context
Three students need an accessible review workflow for research; native mobile functionality is not an initial requirement.

## Decision
Use Next.js, TypeScript, Tailwind CSS and shadcn/ui for Tier 5 after stable backend/safety contracts. Treat React Native/Expo as a future enhancement.

## Alternatives
Native-first React Native/Expo; parallel native and web apps; desktop-only app.

## Rationale
A single web workflow reduces duplicated implementation and supports supervisor/research review across development machines.

## Consequences
Browser image capture/offline capabilities vary; accessibility, session handling and experimental labels still require tests. No frontend scaffold in Phase 00.

## Conditions for reconsideration
Evaluated workflows show a necessary native/device integration or offline requirement and resources plus a new approved scope justify mobile development.

## Verification and approval boundary
[Requirements](../requirements.md), [architecture](../architecture.md), and [roadmap](../roadmap.md) define phase acceptance. No runtime, license, clinical validation, operational setting, or future-phase implementation is approved solely by this record. Changes to shared architecture require explicit approval and an ADR update/successor.
