# Phase 03 review — revised cloud plan and dataset-independent infrastructure

Date: 2026-11-02. Checkpoint evidence below is dated 2026-11-01; the preparation addendum records 2026-11-02 results. **PARTIAL — empirical acceptance BLOCKED.** Infrastructure checkpoint committed/pushed as `a3f4a80e442c4aeeec775e3518404252a6aafa6a`, based on `6b8929087fdd8a336a753c93b0bebddaff0b3ebb`. The user explicitly approved this checkpoint commit and hosted verification, not cloud execution/data acquisition/training or Phase 04. PASS below means only the named observed check, never whole-phase or clinical validation.

Sections A–K record the committed 2026-11-01 infrastructure checkpoint. Section L records the later, uncommitted 2026-11-02 preparation results.

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

**PASS — actual hosted run completed successfully**, not inferred from local checks:

- Commit: `a3f4a80e442c4aeeec775e3518404252a6aafa6a`.
- Message: `Implement Phase 03 vision infrastructure and cloud training preparation`.
- Private repository: `prasanna-dev-codes/t1d-ai-management`, `origin/main`; 52 reviewed text files committed, `.DS_Store` excluded. Staged blobs were compared against the reviewed SHA-256 inventory before committing; `git diff --cached --check` passed.
- Workflow: [Research foundation / run 41334223799](https://github.com/prasanna-dev-codes/t1d-ai-management/actions/runs/41334223799), event `push`, exact `headSha` verified, final `status=completed`, `conclusion=success`.
- Completed **2026-11-01 23:30:04 IST** (provider `updatedAt=2026-11-01T18:00:04Z`).
- Backend PASS: **106 tests**, Ruff/format, strict mypy, shared-contract and proposal-gate checks.
- Database PASS: **40 tests** on hosted disposable TimescaleDB/pgvector; chunk-access regression included.
- Frontend PASS: **32 tests**, lint, typecheck and production build.
- Hosted job conclusions and test totals were checked in GitHub CLI/logs. No CI failure or corrective commit/push occurred.

No hosted job downloads a food corpus/ImageNet weights or runs substantial training. Optional PyTorch architecture/training/export CI remains NOT RUN. Phase 03 remains PARTIAL despite infrastructure CI success. Earlier Phase 02 evidence is preserved separately.

Post-CI changes: this evidence/README status update, the [execution-approval proposal](phase-03-execution-approval.md) and its public-source metadata-only Commons sample are local/uncommitted, outside the tested checkpoint. No further push is authorized/inferred. The unrelated tracked `.DS_Store` remains untouched/unstaged; the working tree is not claimed clean.

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
14. PARTIAL — local and hosted infrastructure checks pass; optional PyTorch job and empirical checks not run.
15. PASS for this checkpoint — explicit evidence, limitations and revised proposal recorded.

## M. Phase 04 readiness

**Not ready; do not begin Phase 04.** Phase 03 remains partial until approved data/environment, real baselines/evaluation/calibration, reviewed artifacts and genuine scoped output exist. Software fixtures and documents cannot substitute for these prerequisites. Checkpoint commit/push approval is explicit; no cloud execution/training or next-phase approval is inferred from it.


## Post-CI execution proposal — no execution approval

[Concrete proposal](phase-03-execution-approval.md): acquire only 40 named Commons candidates, eight each for biryani/chapati/dosa/idli/samosa, with per-file own-work/CC BY-SA 4.0 metadata and declared total **70,401,436 bytes (67.140041 MiB)**. No image pixels/weights were fetched; labels remain unreviewed. Metadata records are public attribution/source information, not clinical data. The proposed first approval is CPU-only acquisition/environment/persistence audit; a 30-minute MobileNet GPU pilot and later two-baseline research run require separate approvals and qualified trainer/weight evidence. RASOI's original linked public Kaggle page returned HTTP 404; no mirrored replacement or guessed size/class list is used. The five-class development sample is not a validated primary dataset, final test set or Phase 03 completion.


## L. Bounded pilot preparation — 2026-11-02

**Authorization:** local dataset-specific implementation and authored synthetic CPU checks, public source verification and temporary low-resolution visual-review previews only. The user has not approved original acquisition, pretrained-weight acquisition, Kaggle execution/training, paid services or Phase 04. Phase 03 remains **PARTIAL**. These working-tree additions are not covered by hosted CI for `a3f4a80e442c4aeeec775e3518404252a6aafa6a`.

**PASS — metadata evidence:** all 40 proposed MediaWiki file identities, per-file own-work/CC BY-SA 4.0 declarations, required attribution and lack of detected warning/restriction flags match the pinned metadata proposal. This is publisher evidence, not independently guaranteed ownership. Preserve source URL, creator credit, license link and changes. The local manifest SHA-256 remains `065a6dd368350f2a4814027f4e55210facab7962e915a654bc286e205a6bc9ae`.

**BLOCKED — complete URL verification:** initial HEAD checks verified 6/40 originals. A later HEAD-only recheck verified 5/40 and received HTTP 429 on 35. No original GET was performed; further source requests stopped. The local audit script now defers subsequent HEAD requests after rate limiting. HEAD and declared SHA-1/size never establish actual checksum/decode integrity.

**PASS — bounded visual-review process; BLOCKED — usable cohort:** 32 previews decoded and visually reviewed; a smaller-preview retry did not recover the other eight. Fourteen provisional candidates require independent human adjudication; 18 were excluded pending label, quality or authorship clarification; eight remain unreviewed. Candidate counts: biryani 1, chapati 3, dosa 3, idli 2, samosa 5. All three task-created preview directories, including raw temporary thumbnails and contact sheets, were deleted. Metadata-only local evidence preserves individual URLs, attribution/license, transformation notes and decisions. No original-resolution image was acquired. The five-class taxonomy remains provisional; the eight-per-class proposal is not executable. See [the revised execution proposal](phase-03-execution-approval.md) for exact manifest positions and manual checks.

**PASS — local pilot software qualification:** typed MobileNetV3-Small head-training loop, epoch-boundary resume with optimizer/scheduler/RNG state and identity/hash checks, validation reporting, atomic checkpoints, locked cumulative 12-hour ledger, prelaunch reservation and process watchdog. The actual native model completed an authored synthetic CPU epoch and ONNX export/parity/integrity checks; the engineering-only artifact remained unavailable to the serving loader. A separate supervised CLI fixture completed within its 60-second CPU reservation and settled the ledger. These are software tests, not food accuracy, calibrated confidence, GPU performance or clinical validation. A stalled epoch resumes from the last completed checkpoint; there is no promise of mid-epoch or two-minute checkpoint recovery. Cloud ledger/output persistence is still unverified.

Executed checks:

- **PASS:** `TORCH_DEVICE_BACKEND_AUTOLOAD=0 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest -q tests/test_pilot_budget.py tests/test_pilot_training.py --tb=short` — **10 passed in 7.60s**. Authored random pixels and random initial weights only; no food dataset or ImageNet weights.
- **PASS:** `TORCH_DEVICE_BACKEND_AUTOLOAD=0 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /tmp/t1d-phase03-clean-env/bin/pytest -q -m 'not integration' --tb=short` — **116 passed, 11 skipped, 29 deselected in 120.20s**. Database integration was not exercised; the skips explicitly direct operators to the isolated database test runner.
- **PASS:** Ruff lint and formatting, **101 files**; strict mypy, **55 source files**. No frontend files changed; frontend checks were not rerun in this preparation task and the earlier hosted results remain separately scoped.
- Local native import initially stalled in optional device-backend discovery; the documented `TORCH_DEVICE_BACKEND_AUTOLOAD=0` setting restricts qualification to built-in CPU/CUDA. An installed ONNX module also stalled on a file read; reinstalling the **same pinned 1.23.2** package restored the focused export checks. A diagnostic run was aborted and is not counted as a passing test. A separate clean temporary environment resolved the existing lockfile without dependency changes. All package downloads were software dependencies, not model weights.

**BLOCKED — account/environment readiness:** public Kaggle username pending; no browser/account session or credentials are available. Private dataset/output handling, actual free quotas, Python/package compatibility, GPU availability/CUDA execution and durable checkpoint restoration are unverified. The prepared local CPU-only preflight notebook has empty outputs and parsed code cells; it has not run on Kaggle. The execution proposal gives explicit Private/accelerator-None/CREATE/new-session-RESTORE instructions. Do not request passwords/tokens/login codes. A CPU-only check cannot prove GPU allocation.

**NOT RUN:** original-file checksum/decode/duplicate verification, original-data or weight acquisition, cloud training, real held-out food evaluation/calibration, actual GPU budget measurements, new hosted CI for these local additions or any Phase 04 work. No real health data, clinical policy, schema, infrastructure/volume or serving authentication change was made. Actual GPU training usage in this task is zero.

**Documentation-only review scope:** prepare only `docs/phase-03-review.md` and `docs/phase-03-execution-approval.md` for the next reviewed commit. Exclude `.DS_Store`, README, the local metadata/evidence, source audit, trainer, tests and notebook. No commit or push is authorized by preparation alone; request human approval for the concrete two-file checkpoint. Existing hosted CI success remains scoped to the earlier exact commit.
