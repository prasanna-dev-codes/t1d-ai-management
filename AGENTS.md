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
