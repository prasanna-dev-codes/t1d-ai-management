# Development roadmap — T1D AI Management

Each phase must include documentation, automated tests, a review checkpoint, and an explicit acceptance criterion.

| Phase | Deliverable | Exit criterion |
|---|---|---|
| 0 | Repository scaffold, scope, safety policy, ADR process | Documentation reviewed and CI plan approved |
| 1 | Requirements, clinical boundaries, data contracts, threat model | Schemas and hazards reviewed |
| 2 | Backend/frontend skeleton, authentication and test infrastructure | End-to-end synthetic-data smoke test passes |
| 3 | Nutrition data layer and food image inference | Reproducible evaluation and confidence handling |
| 4 | Portion confirmation and carbohydrate estimation | Error bounds and manual override tested |
| 5 | Glucose/context integration with provenance and freshness checks | Invalid/stale inputs safely rejected |
| 6 | Clinician-supervised decision-support rules | Safety tests and independent expert review |
| 7 | Explainability, auditability, user feedback | Every result traceable to inputs and model versions |
| 8 | Security, privacy, performance, usability testing | Threat model mitigations and validation report |
| 9 | Demonstration and documentation | Synthetic-data demo; no claims of clinical approval |

## Working agreement
Work phase by phase with Codex. Never advance a phase on the basis of generated code alone: require tests, manual review, and a written decision for safety-critical changes.
