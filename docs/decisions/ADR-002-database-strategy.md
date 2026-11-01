# ADR-002: Canonical and derived database responsibilities

- **Status:** Accepted direction in the Phase 00 project brief; implementation details remain proposed and require review.
- **Date:** 2026-11-01

## Context
Time-series events, structured patient records and similarity/graph retrieval require clear ownership to avoid conflicting clinical facts.

## Decision
PostgreSQL is authoritative; TimescaleDB manages PostgreSQL time series, pgvector stores derived embeddings, Neo4j stores derived graph relations, and object storage owns governed binary objects referenced by canonical metadata.

## Alternatives
PostgreSQL-only retrieval; independent authoritative graph/vector records; document store.

## Rationale
Transactions and constraints belong in the canonical store; specialized indexes support search and remain rebuildable.

## Consequences
Use revision-aware outbox/rebuild flows and canonical authorization/time checks after search. Extension/edition licenses and compatibility require verification before adoption; cross-store operations are not a single transaction.

## Conditions for reconsideration
Measured retrieval value fails to justify complexity, compatibility/license constraints block adoption, or scale evidence requires an approved alternative.

## Verification and approval boundary
[Requirements](../requirements.md), [architecture](../architecture.md), and [roadmap](../roadmap.md) define phase acceptance. No runtime, license, clinical validation, operational setting, or future-phase implementation is approved solely by this record. Changes to shared architecture require explicit approval and an ADR update/successor.

Phase 02 implementation details are specified by the explicitly approved [ADR-006](ADR-006-phase02-isolated-timescale-and-rls.md): separate pinned publisher database, new volume/port, revision registry and non-owner RLS. The authoritative-store direction above is retained.
