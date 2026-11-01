# Dataset-independent vision package

Research software only. No evaluated food model, image corpus, clinical output or training entrypoint is shipped. The default API authenticator denies access and the default vision runtime reports model unavailable.

Base dependencies provide image validation, deterministic preprocessing, source manifests/group splitting/annotation validation, classification/calibration calculations, strict ONNX artifact loading, supervised ephemeral inference and offline cloud-handoff integrity. Optional training dependencies are resolved separately, not installed by normal backend/database checks. Real data rights, final class coverage, native trainer/export and empirical evaluation remain gated.

From the repository root:

```sh
uv sync --frozen --all-packages
uv run --frozen --no-sync python scripts/validate_vision_proposal.py
uv run --frozen --no-sync pytest -q --ignore=tests/integration
uv run --frozen --no-sync python scripts/run_database_tests.py
```

The database runner uses disposable RAM-backed test storage. Vision tests use authored pixels, reference arrays and explicit test-only providers; they are not food-accuracy evidence. No data/weight download or cloud execution is part of these commands.

See [inference](../../docs/vision-inference.md), [cloud proposal](../../docs/vision-cloud-workflow.md), [training/dependencies](../../docs/vision-training.md) and [current review](../../docs/phase-03-review.md). Local corpus/artifact paths and all model binaries are ignored; never commit credentials, private images or patient data. No Phase 04 capability is present.
