# Phase 03 revised scope and decision record

Date: 2026-11-01. Baseline `6b8929087fdd8a336a753c93b0bebddaff0b3ebb`. Phase 03 is **PARTIAL**. The user approved the dataset-independent checkpoint commit/push and hosted CI verification; cloud execution/data acquisition/training and Phase 04 remain unauthorized.

## User decision and current authorization

The user approved dataset-independent infrastructure, the provisional taxonomy/grouped split methodology, candidate EfficientNet-B0/MobileNetV3-Small baselines, a **12-hour total maximum** and the bounded ephemeral API/testing UI. The two named official ImageNet weights are **conditionally** approved subject to provenance, license and checksum verification; those conditions are not recorded as satisfied. The class list stays provisional until verified dataset coverage.

The user revised acquisition to **cloud-first**. Food-101 is an optional general classification benchmark and pipeline check, not the Indian-food primary by default. No full corpus may be downloaded to this Mac, no external data directory is approved, and automatic cleanup is forbidden. No large download, cloud training or paid service may begin before explicit approval of the revised proposal. No such operation has started.

The reviewable proposal is [cloud workflow](vision-cloud-workflow.md), supported by the [10-source comparison](vision-dataset-assessment.json), [source evidence](vision-dataset-assessment.md), [provisional taxonomy](food-taxonomy.md) and [training/evaluation plan](vision-training.md). Indian80 stays blocked. No primary source or final model class list has been selected.

## Observed local resources and use

Apple M4 ARM64, 10 CPU cores, 16 GB unified RAM, macOS 26.6.2/Python 3.12.14; approximately 12 GiB free at initial inspection. Use this machine for lightweight synthetic tests and ONNX CPU inference. MPS training/throughput remains NOT RUN. Preserve at least 10 GiB local free space when considering later artifact transfers; measure again before transfer. No user files, caches or persistent volumes are deleted to meet it.

The base Pillow/NumPy/ONNX/ONNX Runtime/psutil dependencies are now pinned/installed for authorized software checks. Torch/Torchvision/onnxscript remain optional and uninstalled. Dependency purposes/versions and cloud compatibility limits are in [training](vision-training.md). Installing inference libraries is not dataset acquisition or empirical training.

## Implemented separation

`services/vision/src/t1d_vision` owns image validation/preprocessing, source manifests, duplicate/source grouping, split and annotation validation, metric/calibration calculations, artifact eligibility, process supervision and offline cloud-handoff integrity. API transport/scope/audits live in `apps/api/src/t1d_api/vision_router.py` and `vision_service.py`; shared response contracts are generated. `/vision` is the minimal web testing interface. No new patient tables/migrations or Compose/port changes are needed. Existing candidate-only `ModelVersion` is not silently promoted.

[ADR 007](decisions/007-ephemeral-vision-and-cloud-training.md) records the user-approved refinement of the older stored-image/job proposal. Authentication remains deny-all by default, with test-only identities used exclusively in tests. No login bypass, stored image/job/meal, nutritional calculation or treatment instruction is added.

## Verification and next decision

See [Phase 03 review](phase-03-review.md) for actual results, failures corrected and pending work. Synthetic image/ONNX/API/UI tests validate software behavior only. No actual food accuracy, calibrated reliability, multi-food detection/segmentation or PyTorch-to-ONNX parity is established.

Review the revised cloud proposal before any acquisition/training. A named provider/account, persistent destination, rights-cleared source/version and permitted sample size are still required; approval cannot grant missing third-party rights. Dataset-specific loaders, substantial training, cloud session execution, real-food evaluation and final serving artifacts remain gated. Phase 03 cannot be marked complete from these infrastructure checks.
