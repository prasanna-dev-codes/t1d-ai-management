# Phase 01 local development

Research engineering foundation only. No clinical inference, patient ingestion, real sessions, datasets or deployment. The user approved a minimal connectivity shell and optional local stores in Phase 01 on 2026-11-01; full clinical UI and data work remain at their original phases.

## Prerequisites and first-time setup
Use Python 3.12 (tested 3.12.14), Node.js 24 (tested 24.11.1), npm 11 (tested 11.6.2), Git, and uv 0.13.6. Python 3.14 is not the selected project interpreter. `.python-version`, `.nvmrc`, package engines and manifests document the chosen families. Docker Engine with the Compose plugin is optional; Docker 29.9.2/Compose v5.6.1 and ARM64 stores were subsequently verified. No large ML packages are needed.

If uv is already on PATH, use it directly. Otherwise bootstrap an isolated repository-local copy from the standard package registry, without changing system Python:

```sh
python3.12 -m venv .tools/uv
.tools/uv/bin/python -m pip install uv==0.13.6
export PATH="$PWD/.tools/uv/bin:$PATH"
```

From the repository root:

```sh
uv sync --frozen --all-packages --cache-dir .uv-cache
npm ci
cp apps/api/.env.example apps/api/.env
cp apps/web/.env.example apps/web/.env.local
```

Templates contain no actual credentials. `.env` files are ignored. uv is invoked with an explicit env file when desired; Pydantic Settings does not implicitly load arbitrary working-directory `.env` files. Next.js reads `apps/web/.env.local`. `NEXT_PUBLIC_` values are visible in browser bundles, and must never contain credentials. Frontend API-origin changes require restarting dev and rebuilding the production bundle.

## Start and stop
Use separate terminals from the repository root:

```sh
uv run --cache-dir .uv-cache --frozen --all-packages --no-sync --env-file apps/api/.env python -m t1d_api
npm run dev:web
```

Or `make api` and `make web` with default environment values. `make api` does not load `apps/api/.env`; use the explicit command above for that file. If using the local uv bootstrap without exporting PATH, `make api UV=.tools/uv/bin/uv` works. Stop each foreground server with Ctrl-C. Local defaults bind to loopback only; no service is publicly exposed. No startup command creates tables or enables external clinical processing.

Visit `http://127.0.0.1:3000` or `http://localhost:3000`. API is at `http://127.0.0.1:8001`, development docs at `/docs` and schema at `/openapi.json`. The UI checks the real readiness endpoint with a five-second timeout, loading/success/failure states and manual retry. It contains no fabricated patient readings or clinical metrics. Webpack is used explicitly because this execution environment blocked Turbopack's internal compiler socket; it is a supported Next.js CLI build mode. Production-shaped frontend build/serve does not authorize production use:

```sh
NEXT_TELEMETRY_DISABLED=1 npm run build
NEXT_TELEMETRY_DISABLED=1 npm run start --workspace @t1d/web
```

## Configuration
- `T1D_ENVIRONMENT`: `development` by default; `test` disables docs/OpenAPI; `production` is deliberately rejected until an approved production design exists.
- `T1D_API_HOST`: loopback literal, default `127.0.0.1`; public host values fail validation.
- `T1D_API_PORT`: default 8001, integer 1024–65535.
- `T1D_CORS_ORIGINS`: JSON array of exact loopback HTTP(S) origins; defaults `http://localhost:3000` and `http://127.0.0.1:3000`. Wildcards, credentials, paths, query strings and external origins are rejected. CORS allows GET and the required headers only, without credentials.
- `T1D_READINESS_TIMEOUT_SECONDS`: positive float at most 10, default 1.0; operational probe bound, not a clinical freshness threshold.
- `NEXT_PUBLIC_API_BASE_URL`: browser-visible loopback API origin, default `http://127.0.0.1:8001`; no credentials/path/query accepted.
- `NEXT_TELEMETRY_DISABLED=1`: disables Next.js usage telemetry; Makefile and CI set it. No Sentry/OpenTelemetry exporter is configured.
- Optional database passwords/ports are documented separately in [local infrastructure](../infrastructure/docker/README.md). They are not API settings or readiness dependencies in Phase 01.

## Health and authentication
Routes use the approved `/api/v1` prefix:

```sh
curl --fail http://127.0.0.1:8001/api/v1/health/live
curl --fail http://127.0.0.1:8001/api/v1/health/ready
curl -i http://127.0.0.1:8001/api/v1/auth/session
```

Liveness is `200 {"status":"alive"}` independent of optional stores. Readiness is `200 {"status":"ready"}` after lifespan startup and enabled probes succeed; failed/throwing/timed-out probes yield `503` with the standard redacted error envelope. Phase 01 has no external-store-backed capabilities, so no store is implicitly declared available. Later wiring an external dependency requires registering and testing a real probe before enabling that capability.

Session GET always returns `401` with `UNAUTHENTICATED` under the default deny-all authenticator, including arbitrary Bearer headers. It does not establish real sessions. `Principal`, roles and authenticator protocol define the replaceable boundary; synthetic principals exist in tests only through dependency overrides, with expiry checked. There is no runtime test-user flag, credential bypass, session mutation route, or patient authorization implementation. Roles alone will never suffice for future patient access.

Responses carry UUIDv4 `X-Request-ID` and `Cache-Control: no-store`. Valid incoming UUIDv4 IDs propagate; malformed IDs are replaced. Errors correlate through `error.correlation_id` and do not echo inputs or exception strings. Application operational logs allowlist timing/status/correlation metadata; Uvicorn access logging is disabled so paths/query strings do not enter access logs.

## Checks and shared contracts
```sh
make check-api
make check-web
# Or run all checks:
make check
```

Use `UV=.tools/uv/bin/uv` when needed. Exact component commands are visible in Makefile. Backend checks are Ruff lint and format, strict mypy, generated-contract drift, and pytest. Web checks are ESLint with zero warnings allowed, strict TypeScript, Vitest/Testing Library UI/client tests, and a production-shaped Next.js build. Tests use synthetic infrastructure inputs and no patient/health dataset fixtures.

```sh
uv run --cache-dir .uv-cache --frozen --all-packages --no-sync python scripts/export_contracts.py
uv run --cache-dir .uv-cache --frozen --all-packages --no-sync python scripts/export_contracts.py --check
```

The Python response models are authoritative. Generated JSON Schema and TypeScript live in `packages/shared-contracts`; do not hand-edit the generated files. The focused generator fails on unsupported schema constructs. Full OpenAPI generation is deferred until expanding API scope justifies it. See [shared contract README](../packages/shared-contracts/README.md).

CI is defined in `.github/workflows/ci.yml` with read-only permissions, backend/frontend jobs, lockfile installation and cache support. Action major versions are pinned. No hosted CI run has occurred; local test success is not remote CI evidence.

## Optional Docker stores
Follow [infrastructure setup](../infrastructure/docker/README.md). Compose uses local-only bindings, profiles, named volumes, required unique local passwords, and health checks. Plain PostgreSQL is an explicit fallback; TimescaleDB/pgvector support and immutable image digests are unverified. Neo4j is optional; Redis is omitted because no feature requires it. Docker config/startup/health/authentication and restart persistence checks subsequently passed; see the latest Phase 01 review for evidence. Never use real health data in this local configuration.

## Troubleshooting and limitations
- **Address already in use:** do not kill an unknown process. Change backend `T1D_API_PORT` and frontend API origin together. For a different web port, run `npm exec --workspace @t1d/web -- next dev --webpack --hostname 127.0.0.1 --port 3001` and explicitly update both allowed origins. Ports do not auto-increment silently.
- **Backend indicator unavailable:** request readiness directly, check that the API is running, confirm configured origin/port, and inspect redacted logs. A 503 is not a usable result. Reload/rebuild after public env changes.
- **Import failure:** run workspace-wide `uv sync --frozen --all-packages`, not a root-only sync that omits `t1d-api`; keep commands at repository root.
- **Dependency drift:** use `npm ci` and frozen uv sync. Record every intentional version change in manifests, lockfiles and [dependency register](technology-stack.md). Do not blindly run `npm audit fix --force`.
- **Lint advisories:** current npm audit reports a moderate minimatch glob-amplification advisory propagated through 16 development-tool packages; runtime-only audit reports zero advisories. Avoid untrusted arbitrary glob patterns and track upstream fixes. A breaking downgrade/override is not applied to conceal findings. The transitive ESLint 9 copy and whatwg-encoding also emit deprecation notices; direct ESLint is 10.14.0.
- **Browser unavailable:** UI state/client behavior are covered by DOM tests and served HTML checks; visual/mobile/browser integration and accessibility beyond semantic checks still require real-browser review.
- **No Docker:** backend and frontend run independently. Do not report container health or extension support as verified.
- **Clinical/data boundaries:** no patient accounts, clinical tables, ingestion, ML, retrieval, forecasting, doses, treatment protocols or production deployment exist. Identity provider, data governance and clinical policies remain for later approved work.
