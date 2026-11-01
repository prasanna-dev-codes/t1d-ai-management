# Phase 03 review — revised cloud plan and dataset-independent infrastructure

Date: 2026-11-01. **PARTIAL — empirical acceptance BLOCKED.** Baseline/unchanged HEAD: `6b8929087fdd8a336a753c93b0bebddaff0b3ebb`. The user approved this infrastructure checkpoint for commit/push and hosted CI verification. At this pre-commit snapshot no Phase 03 commit/run exists; no cloud execution/training or Phase 04 is authorized. PASS below means only the named observed check, never whole-phase or clinical validation.

## A. Architecture

PASS — implemented importable `t1d_vision` domain package, separate API transport/scope/audits, generated response contracts and minimal `/vision` tester. [ADR 007](decisions/007-ephemeral-vision-and-cloud-training.md) records the explicitly approved ephemeral synchronous refinement. No stored-image/job/meal infrastructure, patient migration, clinical policy/dosage change, live auth bypass or deployment change. Offline data/training artifacts stay separate from API patient records. Details: [preflight](phase-03-preflight.md), [inference](vision-inference.md).

## B. Dataset and storage

PASS for research/proposal only — [assessment](vision-dataset-assessment.md) and [nine-axis matrix](vision-dataset-assessment.json) cover ten candidates, including RASOI, Indian Thali Dataset, IndianFoodNet30 and Khana. FoodLens/Datacluster access limitations are also noted. No Indian primary selected; no rights-cleared corpus inspected. Food-101 is optional general benchmark/pipeline validation, not the Indian primary by default. Indian80 stays BLOCKED by rights ambiguity. No full corpus is downloaded locally.

The user selected **Kaggle first as a planning preference only**, explicitly not execution approval. [Revised cloud workflow](vision-cloud-workflow.md) compares Kaggle/Colab storage, availability, checkpoint persistence, access and environment compatibility, proposes bounded sample/pilot stages and records illustrative compute calculations. No cloud session/store, account mount, upload, paid service or training has started. Approximately 12 GiB local free space remains at final filesystem inspection; no automatic cleanup or persistent volume deletion. Raw/processed vision data and artifact directories are absent. The earlier bounded 128 KiB in-memory Food-101 archive-prefix probe extracted/saved no images and did not reach license terms.

## C. Taxonomy and data infrastructure

PASS for structural/software tests — 18 provisional concepts, hierarchical IDs, explicit aliases/ambiguities and unsupported states; [taxonomy](food-taxonomy.md) remains nontrainable pending verified coverage/final class order. Implemented rights-metadata-gated indexing, corrupt/unsafe/unmapped/missing-group reporting, file/pixel/dHash fingerprints, source/duplicate components, exact-duplicate label-conflict rejection, sealed official test handling and deterministic group splitting. Boxes use normalized **left/top/width/height**, not YOLO center coordinates; masks require explicit integer IDs and height/width shape.

PARTIAL — no dataset-specific full-release adapter/audit or empirically reviewed source mapping. dHash is a conservative candidate grouping mechanism, not proof of complete source/semantic deduplication; dense buckets fail for review. Missing groups and unguaranteed class balance remain limitations. Train/validation/calibration class support needs review before any trainer.

## D. Training and cloud handoff

NOT RUN — Torch/Torchvision/onnxscript are optional and not installed locally. No model-architecture forward, weights, actual training, checkpoint, MPS/CUDA test or trusted resume qualification. The named official ImageNet weights are conditionally approved, but provenance/terms/full checksum conditions are not recorded as fulfilled. Dataset-specific trainer/resume/budget-loop implementation and cloud qualification remain pending the approved environment.

PASS for metadata/handoff software — metadata-only environment probe and flat allowlisted size/SHA-256 inventory/verification, without remote execution, extraction or checkpoint deserialization. Unknown files/directories/symlinks and changed bytes fail. Bundle checks do not prove rights, metrics or safe pickle contents. Future trusted loaders require weights-only and identity validation. Pins/purposes/licenses and protocol: [training](vision-training.md), [cloud workflow](vision-cloud-workflow.md). The 12-hour total is a maximum, not a duration request.

## E. Evaluation and uncertainty

PASS for mathematical software — hand-calculated top-k/F1/confusion/NLL/Brier/ECE checks, invalid-input rejection, dedicated-calibration-role fitting and risk/coverage implementation. Synthetic calculations are not food metrics.

NOT RUN — actual class-level/held-out/Indian/mixed/unknown/robustness evaluation, empirical calibration/operating-point selection, group-bootstrap intervals and real-food confidence reliability. No accuracy/F1/ECE/IoU/Dice/mAP from a trained food model exists. Softmax thresholds do not establish OOD detection. Trained detection/semantic/instance segmentation remain unavailable. [Evaluation protocol](vision-evaluation.md).

## F. ONNX

PASS for engineering graph only — native M4 CPU ONNX Runtime output on an authored tiny graph matches an independent NumPy reference at tested `atol=1e-6`. Loader tests check checksums, shape/type/order identity, path/symlink rules and refusal of engineering-only serving. External tensors, custom functions/domains and nested control-flow graphs are disallowed by the loader.

BLOCKED/NOT RUN — real selected PyTorch-to-ONNX export/parity, final model artifact, empirical artifact review and real-model latency/memory benchmarks. No random/synthetic graph is supplied as a serving food classifier. No serving artifact directory is configured by default.

## G. Backend

PASS for software/scoped database checks — authenticated scoped metadata/analysis routes retain default deny-all, role/write-grant/current-consent/RLS checks and final authorization recheck. Test-only provider/identity fixtures demonstrate safe response/audit behavior and discard predictions after grant revocation. Foreign scope, read-only/participant/revoked access, withdrawn consent represented by an appended `revoked` revision, missing identity/model and oversized/invalid uploads fail safely. No meal records are created.

PASS for resource software — 8 MiB byte/16 MP/dimension checks, streamed upload rejection, one admission/no queue, isolated five-second deadline, cancellation, sampled 1 GiB RSS guard, bounded JSON replies and suppressed native diagnostics. A maximum-sized input cannot block the large-byte transfer outside supervision. Timeout tests verify slot reuse afterward. These are local software checks, not instantaneous hard RSS/public sandbox or real-model throughput guarantees.

## H. Frontend

PASS for software — scoped model check, file validation/bounded dimension-header inspection before local preview/revocation, loading/error/unavailable states, returned-label review/calibration warnings and safe failure display. **32 frontend tests**, ESLint/typecheck and production build pass. `/vision` builds as a static route. No login/token bypass, stored image/history, fabricated overlay/nutrient output or meal-confirmation control.

BLOCKED — genuine food-model output end to end; positive UI fixtures are explicitly test-only. The normal app remains unauthenticated/model-unavailable until separately approved identity/artifact workflows exist.

## I. Exact local verification results

- PASS — `.tools/uv/bin/uv lock` resolved the pinned workspace; frozen offline noneditable base package sync/rebuild completed. Torch/weights/corpus were not installed/downloaded by base sync.
- PASS — `.venv/bin/ruff check .` and `.venv/bin/ruff format --check .`.
- PASS — `.venv/bin/mypy`: **50 source files**, strict application/domain contracts with scoped untyped-native-library boundaries.
- PASS — `scripts/export_contracts.py --check`: generated TypeScript/JSON match current response schemas.
- PASS — `scripts/validate_vision_proposal.py`: **18 concepts, 10 sources × 9 axes**, acquisition/training/cloud/paid/local-full-download gates closed, API design approved.
- PASS — `.venv/bin/pytest -q --ignore=tests/integration --tb=short`: **106 passed**; includes existing Phase 01/02 unit checks and authored vision fixtures.
- PASS — `.venv/bin/python scripts/run_database_tests.py --tb=short`: **40 passed** against a new RAM-backed TimescaleDB/pgvector database, no persistent volumes attached. Existing RLS chunk-access regressions remain included.
- PASS — `npm run lint`, `npm run typecheck`, `npm run test:web`: **32 passed**, and `NEXT_TELEMETRY_DISABLED=1 npm run build`.
- PASS — metadata probe confirms Python 3.12.14/ARM64 with Pillow 13.0.0, NumPy 2.5.4, ONNX 1.23.2, ORT 1.31.1 and psutil 7.2.2; Torch/Torchvision/onnxscript absent. GPU/rights/persistent-cloud/training flags remain false.
- PASS — whitespace checks and changed-text inventory review. No staged files, new environment/credential/image/model/dump artifacts or actual secrets found. A scanner's credential-URL hit was an unchanged baseline negative CORS-validation fixture, manually reviewed without printing its userinfo. This is a bounded source review, not a guarantee against every possible secret format.
- UNRELATED — tracked `.DS_Store` changed outside the implementation inventory; its binary contents were not inspected and it is left untouched/unstaged. Exclude it from any future reviewed commit.
- FAIL, RESOLVED — the new consent test first attempted an update of an append-only row, then used an unsupported status name. Corrected the fixture to append version 2 using the existing `revoked` enum. The final complete 40-test database run passes; no schema/policy weakening was made. No unresolved executed-check failure remains.

Infrastructure Compose, migrations, existing database/auth/clinical-safety modules and Phase 01/02 persistent volumes were not modified. Existing backend/web regressions pass. No fresh persistent-store restart/persistence exercise was needed/performed for this code-only phase checkpoint.

## J. CI and Git

Phase 03 hosted CI **NOT RUN**. No new commit SHA/run URL exists; HEAD remains the baseline above, all Phase 03 work is uncommitted and the index is empty. Existing backend/database/frontend jobs are retained; backend now also checks proposal gates and includes deterministic base vision tests. No job downloads data/weights or runs substantial training. Optional PyTorch architecture/training/export CI is not delivered/qualified yet. Prior Phase 02 hosted success in [its review](phase-02-review.md) is not relabeled as Phase 03 CI.

## K. Remaining blockers and limitations

1. Revised cloud execution/acquisition/training approval, approved Kaggle account and persistent destination, actual capacity/quota/GPU/driver/Python compatibility and checkpoint restore evidence.
2. Usable source image rights, exact accessible release/checksums, approved cloud sample, audited coverage/source lineage and finalized class map. Indian80 remains blocked; other candidates are not blanket-cleared.
3. Dataset-specific trainer/resume/shared-budget enforcement, two actual baseline runs, validation selection, calibration, held-out/challenge reports and defensible uncertainty estimates.
4. Genuine selected ONNX artifact, native PyTorch parity and measured M4 cold inference/RSS under the chosen limits; five seconds may be insufficient for a future cold artifact.
5. Real-food end-to-end API/UI evidence with an approved identity/testing workflow; no real patient workflow or public deployment is approved.
6. Trained multi-food detection/segmentation has neither approved annotations nor measured results. No nutrient/portion/treatment capability is implemented.

## L. Acceptance status

1. BLOCKED — final dataset rights/access/acquisition and actual release audit.
2. PARTIAL — provisional taxonomy/structural checks exist; coverage/final mapping pending.
3. PARTIAL — generic validation/group/split tools tested; real dataset adapters/audit not run.
4. NOT RUN — qualified dataset-specific trainer/resume loop and actual training.
5. BLOCKED — empirical EfficientNet/MobileNet baseline comparison.
6. NOT RUN — genuine class-level/calibration/robustness report.
7. PASS for truthful unavailable status only — no trained detection/segmentation claim.
8. PARTIAL — review/abstention/metric software; empirical reliability unverified.
9. BLOCKED — usable evaluated food ONNX artifact.
10. NOT RUN — actual PyTorch/ORT parity; tiny authored ONNX/NumPy software parity passes.
11. PARTIAL — scoped authenticated software flow tested; genuine food inference blocked.
12. PARTIAL — frontend tested/builds; genuine food output blocked.
13. PASS for local regressions/scope preservation — Phase 01/02 foundations remain intact.
14. PARTIAL — local deterministic checks pass; hosted CI and optional PyTorch job not run.
15. PASS for this checkpoint — explicit evidence, limitations and revised proposal recorded.

## M. Phase 04 readiness

**Not ready; do not begin Phase 04.** Phase 03 remains partial until approved data/environment, real baselines/evaluation/calibration, reviewed artifacts and genuine scoped output exist. Software fixtures and documents cannot substitute for these prerequisites. Checkpoint commit/push approval is explicit; no cloud execution/training or next-phase approval is inferred from it.
