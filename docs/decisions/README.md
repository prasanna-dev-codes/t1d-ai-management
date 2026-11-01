# Architecture decision records

The attached Phase 00 brief specifies these five high-level directions. “Accepted direction” records that instruction; it does not mean clinical review, implementation validation, or deployment approval. Unspecified implementation choices remain **Pending approval** in the relevant document. The naming scheme below replaces the provisional numeric-only template; no existing decision record is removed.

- [ADR-001: Modular monolith](ADR-001-modular-monolith.md)
- [ADR-002: Database strategy](ADR-002-database-strategy.md)
- [ADR-003: Evidence-based ML model selection](ADR-003-ml-model-selection.md)
- [ADR-004: Safety separation](ADR-004-safety-separation.md)
- [ADR-005: Web-first development](ADR-005-web-first-development.md)

## Template for future records
Use `ADR-NNN-short-title.md`, retaining old records when superseded. Include date and these sections: Status (Proposed, Accepted, Superseded, Rejected), Context, Decision, Alternatives, Rationale, Consequences, Conditions for reconsideration, and verification/approval evidence. Link superseding records in both directions. Shared-architecture changes require explicit approval; record who approved and the relevant evidence without fabricating sign-off.
