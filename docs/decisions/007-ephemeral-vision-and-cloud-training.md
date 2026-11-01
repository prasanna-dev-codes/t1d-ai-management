# ADR 007: Ephemeral vision transport and cloud-first training

Date: 2026-11-01. Status: **Accepted for dataset-independent implementation**, following explicit user approval. Acquisition/cloud execution/training approvals remain separate.

## Context

The earlier API proposal stored uploads and queued jobs, but Phase 03 has no approved image retention workflow. The local M4 has limited free disk. The user approved a bounded synchronous interface and revised substantial training/data storage to cloud-first, with no full corpus on the Mac or automatic cleanup.

## Decision

Add scoped raw JPEG/PNG POST `/api/v1/patients/{patient_id}/vision/analyses` and GET `/api/v1/patients/{patient_id}/vision/model`. Keep existing deny-all authentication, principal roles, patient/study grants, consent and runtime RLS. Authenticate/authorize before reading media; reauthorize before audited result return. Identity adapters exist only in tests. No stored images/jobs/meals, patient migrations, schema grants, clinical policies or treatment calculations are added.

Share versioned preprocessing/artifact contracts in `t1d_vision`. Admit one request per app process without a waiting queue, cap byte/pixel/dimension/time budgets and run decoding/ONNX in a killable subprocess. Apply a sampled RSS guard; do not pretend this is a hard macOS RSS reservation or a public multi-tenant sandbox. IPC back to the parent is bounded JSON, not pickle deserialization. Persist only protected reference/code/correlation audits; strip EXIF from derived buffers and emit no raw-media/path diagnostics. No application-level image/result cache. Cold process/model load counts toward the deadline; future async execution requires measured evidence and a separate lifecycle decision.

Serve only explicitly configured eligible evaluated artifacts with bound model/data/split/class/preprocessing/calibration/evaluation metadata and checksums. Engineering-only/random artifacts cannot be the default food model. No fallback download. Unsupported localization modes are unavailable/abstained, not invented masks. Scores always require human review, and do not demonstrate OOD or clinical reliability.

Cloud workflow planning is documented separately; no provisioning, paid service, dataset/weight download or training starts from these changes. Food-101 remains optional general-benchmark data; final Indian taxonomy/primary dataset await coverage and rights evidence. The approved 12-hour ceiling includes failed/restarted work and is not a runtime target.

## Consequences

Inference is intentionally conservative and may be unavailable/timeout on cold load until actual artifacts are measured. The current UI has no configured live identity provider or evaluated food model; positive mocks validate software only. CLI handoff checks integrity without asserting trustworthy metrics/rights or executing checkpoints. Real food evaluation, native PyTorch/export compatibility, GPU environment/persistence and trained multi-food capabilities remain unresolved. No Phase 04 or deployment change follows from this ADR.
