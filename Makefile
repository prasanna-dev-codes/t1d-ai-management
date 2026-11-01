UV ?= uv
export UV_CACHE_DIR := $(CURDIR)/.uv-cache
export NEXT_TELEMETRY_DISABLED := 1

.PHONY: install api web check check-api check-web contracts
install:
	$(UV) sync --frozen --all-packages
	npm ci
api:
	$(UV) run --frozen --all-packages --no-sync python -m t1d_api
web:
	npm run dev:web
contracts:
	$(UV) run --frozen --all-packages --no-sync python scripts/export_contracts.py --check
check-api:
	$(UV) run --frozen --all-packages --no-sync ruff check .
	$(UV) run --frozen --all-packages --no-sync ruff format --check .
	$(UV) run --frozen --all-packages --no-sync mypy
	$(UV) run --frozen --all-packages --no-sync python scripts/export_contracts.py --check
	$(UV) run --frozen --all-packages --no-sync pytest -q
check-web:
	npm run lint
	npm run typecheck
	npm run test:web
	npm run build
check: check-api check-web
