# Repository instructions — T1D AI Management

## Mission and scope
Build a research/educational Type 1 Diabetes management and clinical decision-support prototype. This repository is not a certified medical device. Do not represent outputs as medical advice or autonomous treatment instructions.

## Engineering rules
- Implement one roadmap phase at a time; keep pull requests small and reviewable.
- Use typed Python, explicit input validation, deterministic tests, and structured error handling.
- Keep frontend, API, domain logic, data, and model inference separated.
- Record major architectural decisions as ADRs in `docs/decisions/`.
- Do not add dependencies without documenting their purpose and version.
- Never commit secrets, credentials, patient identifiers, medical records, or real health datasets.
- Use synthetic/de-identified test fixtures; document dataset provenance and licensing.
- Require unit, integration, and safety regression tests for changes to clinical features.
- Log operational events without sensitive medical payloads.

## Clinical safety boundaries
- Do not implement autonomous insulin administration or present calculated doses as prescriptions.
- Any insulin-related estimate must be explicitly labeled investigational, require qualified clinician review, and include uncertainty, assumptions, and missing-data warnings.
- Never silently assume glucose units, carbohydrate amounts, insulin sensitivity, insulin-to-carb ratios, active insulin, or target glucose.
- Validate units, timestamps, ranges, stale readings, and missing data; fail closed on invalid inputs.
- Keep emergency advice conservative: direct users to established emergency services/clinical care when appropriate.
- AI/LLM outputs must never bypass deterministic safety validation or change treatment parameters without explicit clinician-approved workflow.
- Protect health information with least privilege, encryption, access controls, and retention limits; assess applicable privacy and medical-device regulations before real-world use.
- Document model limitations, evaluation datasets, performance by subgroup, and human oversight requirements.

## Agent workflow
1. Read `docs/architecture.md` and `docs/roadmap.md` before editing.
2. Propose files and tests for the selected phase.
3. Implement with minimal changes and run relevant checks.
4. Summarize changes, tests, risks, and unresolved questions.
5. Ask for human approval before modifying clinical safety policies, dosage logic, or deployment settings.


## Phase 00 foundation and authoritative references
- Project identity: T1D AI, a research-grade AI-powered Type 1 diabetes management prototype.
- The five tiers in `docs/architecture.md` and 12 phases in `docs/roadmap.md` are authoritative for future work. Phase 00 is documentation only; do not begin Phase 01 without user approval.
- Read relevant requirements, contracts, and ADRs before changes; do not modify shared architecture without explicit approval.
- Prefer small, modular, testable changes. Use Python type hints and Pydantic models and strict TypeScript typing when implementation begins.
- Preserve backward compatibility with approved contracts; update documentation whenever implementation contracts change.
- Avoid unnecessary dependencies; record purpose, exact resolved version, licensing review, and compatibility evidence before adoption.

## Testing integrity
- Add tests for implemented behavior; run relevant checks after changes and report exact commands and outcomes.
- Never claim tests passed unless executed successfully; report failures and checks not run.
- Never hide failing tests or silently weaken assertions to make them pass.

## Additional research safety requirements
- Do not produce unvalidated patient-facing insulin dosing recommendations.
- Keep forecasting separate from clinical decision logic; treat all AI predictions as experimental.
- Implement explicit abstention for unreliable information and preserve traceability and auditability.
- Do not claim clinical safety or regulatory compliance without evidence.
- The Phase 00 safety specification documents existing boundaries and proposed verification controls. It does not approve clinical thresholds, dosage algorithms, or deployment settings.

## Repository management
- Never delete user data without explicit permission or overwrite unrelated work.
- Do not commit, push, or modify Git remotes without explicit instruction.
- Summarize modified files, verification results, risks, and unresolved questions after every task.

## Phase completion gate
A phase is complete only when required deliverables exist, acceptance criteria are satisfied, relevant tests or documentation checks pass, limitations are documented, and no blocking issue remains. The user must approve progression to the next phase. File creation alone does not establish completion.

## Current authorized phase
The user authorized Phase 01 on 2026-11-01, including the minimal web connectivity shell and optional local PostgreSQL/Neo4j configuration. Follow `docs/local-development.md` and the Phase 01 evidence register. This authorization does not extend to Phase 02, clinical schemas/features, production identity, clinical safety-policy changes or production deployment. Preserve all existing safety rules above.
