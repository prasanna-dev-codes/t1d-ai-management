# Software requirements specification

Status: Phase 00 design baseline, subject to review. Requirement priority is **Mandatory**, **Research extension**, or **Future enhancement**. Mandatory describes intended scope, not implemented functionality. Phase gates are in the [roadmap](roadmap.md).

## Scope, users, and roles
Research, simulation, and authorized retrospective evaluation of meal analysis, metabolic-history retrieval, and glucose forecasting. No autonomous insulin administration, clinical deployment, or unvalidated patient-facing dosing instructions. Phase 01 implements a health/auth-boundary backend and connectivity shell only; the clinical behavior specified below remains unimplemented.

Researchers operate approved synthetic/de-identified studies; qualified clinicians review investigational outputs and any later simulation protocol; participants may eventually correct meal inputs and view approved research displays under consent; administrators manage access and operations without routine health-record access. An individual can have multiple roles but explicit patient/study scope is always required. Authentication alone does not grant access to all patients. Direct participant use and identity-provider selection remain pending approval.

## Functional requirements
- **FR-001 — Mandatory:** Authenticate users and enforce role plus study/patient authorization on every record and object access. Acceptance: foreign identifiers fail without revealing existence; privileged actions are audited. Phases 01–02.
- **FR-002 — Mandatory:** Validate submitted meal images, provenance, size, content type, and safe decoding before analysis. Acceptance: malformed and unsupported images fail without persisting unsafe artifacts. Phases 03–04.
- **FR-003 — Mandatory:** Return food detections, candidate identities, portion estimates, confidence, and review flags. Acceptance: uncertain/unsupported foods require correction or abstention. Phases 03–04.
- **FR-004 — Mandatory:** Map confirmed components to versioned nutrition references and estimate carbohydrate, protein, fat in g and energy in kcal with uncertainty. Acceptance: missing portion/reference cannot become a confident zero. Phase 04.
- **FR-005 — Mandatory:** Record human corrections and immutable meal-confirmation revisions. Acceptance: downstream results reference the exact reviewed revision and are invalidated by later edits. Phases 04, 09.
- **FR-006 — Mandatory:** Ingest CGM, insulin-history, and activity events with explicit units, timestamps, source, deduplication, and validation. Acceptance: invalid batches roll back and corrections preserve lineage. Phase 02.
- **FR-007 — Mandatory:** Store canonical structured records in PostgreSQL; rebuild derived graph/vector indexes from authorized source revisions. Acceptance: index deletion cannot destroy authoritative history. Phases 02, 05.
- **FR-008 — Mandatory:** Retrieve similar within-patient historical episodes using structured, vector, and graph evidence. Acceptance: no other-patient or future-known data appears in retrieval or cached results. Phase 05.
- **FR-009 — Mandatory:** Forecast glucose at 30, 60, 90, and 120 minutes with model version, input cutoff, uncertainty, and applicability warnings. Acceptance: evaluate each horizon against a persistence baseline on held-out data. Phase 06.
- **FR-010 — Mandatory:** Evaluate deterministic eligibility and explicit abstention independently of prediction. Acceptance: unreliable/missing inputs cannot produce an eligible output through any endpoint. Phases 01–09 as features appear.
- **FR-011 — Research extension:** Evaluate a versioned clinician-defined dosing protocol only in restricted research simulation. Acceptance: independent protocol approval, synthetic/authorized retrospective scope, traceable assumptions, no patient-facing dose route, no actuation. Phase 08; conditional.
- **FR-012 — Mandatory:** Show corrections, history, experimental forecasts, uncertainty, evidence provenance, and abstention explanations in a human review UI. Acceptance: review workflows preserve authoritative revisions and cannot override deterministic checks. Phase 09.
- **FR-013 — Mandatory:** Maintain protected audit history and reproducible model/data manifests. Acceptance: an authorized reviewer can trace output to inputs, approvals, and model version without raw medical payloads in operational logs. Phases 02–11.
- **FR-014 — Research extension:** Investigate personalization, physiology-informed models, and experimental Fat/Protein Units. Acceptance: compare against simpler baselines with approved definitions; do not imply clinical validation. Phases 04, 07–08.
- **FR-015 — Future enhancement:** Evaluate React Native/Expo after the web workflow is evaluated. Acceptance: separate approved scope and ADR update; no Phase 00 mobile scaffolding.

## Non-functional requirements
- **NFR-001 — Mandatory:** Use typed boundaries, versioned contracts, modular domain logic, and structured failures. Acceptance: type/lint checks and contract tests pass for each implemented slice.
- **NFR-002 — Mandatory:** Minimize protected data; encrypt transport and storage, enforce least privilege, consent scope, and retention/deletion controls. Acceptance: threat-model and access-control tests pass before any real-world ingestion.
- **NFR-003 — Mandatory:** Reproduce experiments with seeds, code/data/model versions, preprocessing lineage, patient-disjoint splits, and temporal holdouts. Acceptance: saved manifests reproduce reported metrics within declared tolerance.
- **NFR-004 — Mandatory:** Expose safe liveness/readiness and privacy-preserving latency/error/abstention metrics. Acceptance: logs, traces, and errors contain no sensitive payloads in synthetic leak tests.
- **NFR-005 — Mandatory:** Bound uploads, query sizes, inference time, and worker concurrency. Acceptance: resource limits are measured on declared hardware; timeouts terminate safely.
- **NFR-006 — Mandatory:** Proposed performance experiment: measure p50/p95 API validation, meal analysis, retrieval, and forecast latency separately under a documented synthetic workload. Numeric targets and workload sizes are **Pending approval** after Phase 01 measurements; no real-time or uptime guarantee is claimed.
- **NFR-007 — Mandatory:** Support accessible human correction and clear units/uncertainty. Acceptance: keyboard navigation, readable error states, and review usability checks pass in Phase 09.
- **NFR-008 — Mandatory:** Prevent cross-patient leakage in training, retrieval, caches, and evaluation. Acceptance: adversarial patient/time-boundary fixtures and split-manifest audits pass.
- **NFR-009 — Mandatory:** Record dependency purpose/version/license, migration lineage, and recovery procedures. Acceptance: reproducible clean-environment installation and synthetic recovery test before deployment review.
- **NFR-010 — Mandatory:** Keep expensive ML and external services optional for local software tests. Acceptance: deterministic mocks exercise failures without network access or patient data.

## Safety requirements
- **SAFE-001 — Mandatory:** No autonomous insulin administration or integration that issues actuation commands. Acceptance: architecture and route review show no delivery path.
- **SAFE-002 — Mandatory:** No unvalidated patient-facing insulin dosing recommendations. Acceptance: forecast/UI contracts contain no recommended-dose fields.
- **SAFE-003 — Mandatory:** Require explicit units, amounts, provenance, timestamps, freshness, ranges, and missingness. Acceptance: missing, stale, future, conflicting, and invalid inputs fail closed; no default treatment parameters.
- **SAFE-004 — Mandatory:** Gate outputs through deterministic checks and explicit abstention; LLM/model output cannot bypass checks. Acceptance: safety regression fixtures test direct, worker, retry, and cached paths.
- **SAFE-005 — Mandatory:** Label predictions experimental and include uncertainty, assumptions, missing-data warnings, and review requirements. Acceptance: all displayable output envelopes include these fields.
- **SAFE-006 — Mandatory:** Keep forecasting and clinical simulation separate; any insulin-related estimate is investigational and requires qualified clinician review. Acceptance: separate role, study protocol, and revision checks, with no public treatment route.
- **SAFE-007 — Mandatory:** Never change clinical settings automatically. Acceptance: versioned approved settings with explicit qualified authorization; pending revisions are ineligible.
- **SAFE-008 — Mandatory:** Do not claim clipping guarantees safety or that the prototype is clinically validated/regulatorily compliant. Acceptance: documentation, UI, and output review use research-only language.
- **SAFE-009 — Mandatory:** Keep emergency guidance conservative and directed to established emergency services/clinical care; no AI-specific emergency treatment plans. Acceptance: wording requires qualified approval before UI implementation.
- **SAFE-010 — Mandatory:** Use synthetic fixtures and authorized de-identified research data only outside Git. Acceptance: provenance, consent/access/license review, and retention decision precede acquisition; no health records committed.

## Research constraints and acceptance
Three students, macOS development, finite compute, no assumed datasets, trained models, application, or clinical validation. Dataset permissions, exact software versions, clinical thresholds, evaluation targets, and study authorization remain unresolved. No architecture component establishes regulatory compliance by itself.

Each requirement is accepted only with traceable tests/evaluation or documentation evidence at its assigned phase. Phase 00 acceptance is documentary coverage, consistent contracts, explicit unresolved decisions, and passed local checks; it does not assert FR implementation. See [Phase 00 review](phase-00-review.md) for gate status and [ML plan](ml-research-plan.md) for scientific evaluation.
