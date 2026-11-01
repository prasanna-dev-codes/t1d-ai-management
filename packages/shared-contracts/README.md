# Phase 01 shared contracts

Python models in `apps/api/src/t1d_api/contracts.py` are the source of truth. Run `uv run --package t1d-api python scripts/export_contracts.py` from the repository root to generate `schema.json` and `index.ts`; add `--check` to verify drift without writing. CI and pytest run the check. Health responses are tested against the same schemas; TypeScript uses the generated types and runtime-validates the health payload's literal status.

This small generator supports only the JSON Schema constructs used here and fails on unsupported nodes. It is not a general OpenAPI code generator. Future API expansion should replace it with a reviewed OpenAPI generation strategy when the contract scope warrants it. These files define health, errors and the fail-closed session boundary only; no clinical schemas exist.
