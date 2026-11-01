# Documentation index

Status: Phase 00 design baseline plus Phase 01 engineering foundation. Only health/auth-boundary infrastructure and a minimal connectivity shell are implemented. No clinical functionality, validation, dataset access or deployment is implied.

## Read first
- [Local development](local-development.md): prerequisites, setup, ports, configuration, checks and troubleshooting.
- [Phase 01 review](phase-01-review.md): implementation evidence, outstanding blockers and Phase 02 gates.
- [Repository overview](../README.md) and [agent instructions](../AGENTS.md): current state, workflow and invariant boundaries.
- [Requirements](requirements.md): FR/NFR/SAFE identifiers, acceptance and roles.
- [Architecture](architecture.md): five tiers, trust boundaries, orchestration and sequence diagrams.
- [Roadmap](roadmap.md): authoritative 12 phases and approval gates.
- [Phase 00 review](phase-00-review.md): validation evidence, unresolved decisions and readiness assessment.

## Design and research specifications
- [Technology stack](technology-stack.md): selected/candidate tools, alternatives, costs and verification register.
- [Data model](data-model.md): canonical entities, provenance, units and knowledge-time semantics.
- [API contracts](api-contracts.md): proposed routes, schemas, errors and operation-specific gates.
- [Datasets](datasets.md): research leads, acquisition/license gate and leakage risks.
- [ML research plan](ml-research-plan.md): baselines, splits, metrics, uncertainty and model selection.
- [Memory architecture](memory-architecture.md): graph/vector retrieval, temporal safety and update policies.
- [Safety and privacy](safety-and-privacy.md): risk register, abstention, oversight and governance questions.
- [Development standards](development-standards.md): coding/testing, migration, dependency, logging and PR practices.
- [Architecture decision records](decisions/README.md): five high-level decisions and future ADR template.

## Status vocabulary
“Selected” records the baseline direction from the brief, not a compatible installed version. “Candidate” needs empirical evaluation. “Pending approval” is an unresolved proposal requiring review. “Verification required” identifies an unverified external assumption, source or term. “Eligible” is limited to a named research operation and never certifies clinical safety. Human approval to proceed to a phase is separate from approval of any clinical policy, dosage algorithm, real-data processing or deployment setting.
