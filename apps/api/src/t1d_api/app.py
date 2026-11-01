"""Application factory with isolated configuration and deterministic boundaries."""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from time import perf_counter
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response

from t1d_api.auth import DenyAllAuthenticator, Principal, require_principal
from t1d_api.config import Settings
from t1d_api.contracts import (
    ErrorBody,
    ErrorDetail,
    ErrorResponse,
    LivenessResponse,
    ReadinessResponse,
    SessionResponse,
)
from t1d_api.data.errors import DataError
from t1d_api.data.router import router as data_router
from t1d_api.data.service import failure_audit
from t1d_api.db.session import Database
from t1d_api.observability import request_logger
from t1d_api.readiness import Runtime


def error_response(
    request: Request,
    status: int,
    code: str,
    message: str,
    details: list[ErrorDetail] | None = None,
) -> JSONResponse:
    body = ErrorResponse(
        error=ErrorBody(
            code=code,
            message=message,
            details=details or [],
            correlation_id=request.state.correlation_id,
        )
    )
    headers = {"WWW-Authenticate": "Bearer"} if status == 401 else None
    return JSONResponse(body.model_dump(mode="json"), status_code=status, headers=headers)


def create_app(
    settings: Settings | None = None,
    runtime: Runtime | None = None,
    database: Database | None = None,
) -> FastAPI:
    config = settings if settings is not None else Settings()
    state = runtime if runtime is not None else Runtime()
    db = (
        database
        if database is not None
        else Database(config.database_url.get_secret_value())
        if config.database_url is not None
        else None
    )
    if db is not None:

        async def database_probe() -> bool:
            return await asyncio.to_thread(db.check)

        state.probes = (*state.probes, database_probe)
    logger = request_logger()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        state.started = True
        try:
            yield
        finally:
            state.started = False
            if db is not None:
                db.close()

    app = FastAPI(
        title="T1D AI Research Foundation",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if config.environment == "development" else None,
        redoc_url=None,
        openapi_url="/openapi.json" if config.environment == "development" else None,
    )
    app.state.database = db
    app.state.settings = config
    app.state.runtime = state
    app.state.authenticator = DenyAllAuthenticator()

    @app.exception_handler(DataError)
    async def data_error(request: Request, exc: DataError) -> JSONResponse:
        # Services audit transactional failures. Parsing/transport failures are separate.
        if db is not None and exc.code in {"INVALID_INPUT", "PAYLOAD_TOO_LARGE"}:
            await asyncio.to_thread(
                failure_audit,
                db,
                getattr(request.state, "principal_id", None),
                "validation",
                exc.code,
                request.state.correlation_id,
            )
        return error_response(
            request,
            exc.status,
            exc.code,
            "Research data operation unavailable" if exc.status >= 500 else "Request rejected",
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        codes = {
            401: ("UNAUTHENTICATED", "Authentication required"),
            403: ("FORBIDDEN", "Access denied"),
            404: ("NOT_FOUND", "Resource unavailable"),
            405: ("METHOD_NOT_ALLOWED", "Method not allowed"),
            503: ("NOT_READY", "Service unavailable"),
        }
        code, message = codes.get(exc.status_code, ("REQUEST_FAILED", "Request failed"))
        if db is not None and exc.status_code == 401:
            await asyncio.to_thread(
                failure_audit, db, None, "auth", "UNAUTHENTICATED", request.state.correlation_id
            )
        return error_response(request, exc.status_code, code, message)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Do not echo input, context, path values, or custom validator messages.
        errors = exc.errors()
        if any(e["loc"][-1] in {"glucose_unit", "amount_unit", "portion_unit"} for e in errors):
            code = "INVALID_UNIT"
        elif any(e["type"] == "missing" and "provenance" in e["loc"] for e in errors):
            code = "MISSING_PROVENANCE"
        elif any(
            e["loc"][-1]
            in {
                "event_time",
                "recorded_at",
                "start_at",
                "end_at",
                "delivery_start",
                "delivery_end",
                "cutoff",
            }
            for e in errors
        ):
            code = "INVALID_TIMESTAMP"
        else:
            code = "VALIDATION_ERROR"
        if db is not None:
            await asyncio.to_thread(
                failure_audit,
                db,
                getattr(request.state, "principal_id", None),
                "validation",
                "INVALID_UNIT" if code == "INVALID_UNIT" else "INVALID_INPUT",
                request.state.correlation_id,
            )
        details = []
        for error in exc.errors()[:20]:
            indices = [v for v in error["loc"] if isinstance(v, int)]
            if indices:
                details.append(
                    ErrorDetail(field=f"body.records[{indices[0]}]", reason="invalid_record")
                )
        return error_response(request, 422, code, "Request validation failed", details)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "X-Request-ID", "X-Study-ID", "Idempotency-Key"],
        expose_headers=["X-Request-ID"],
    )

    @app.middleware("http")
    async def request_context(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        incoming = request.headers.get("X-Request-ID", "")
        try:
            parsed = UUID(incoming)
            request.state.correlation_id = parsed if parsed.version == 4 else uuid4()
        except ValueError:
            request.state.correlation_id = uuid4()
        started = perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            response = error_response(request, 500, "INTERNAL_ERROR", "Internal server error")
            # This response is outside CORSMiddleware's exception path; preserve CORS
            # only for the exact configured origin, including unexpected failures.
            origin = request.headers.get("origin")
            if origin in config.cors_origins:
                response.headers["Access-Control-Allow-Origin"] = origin
                response.headers["Access-Control-Expose-Headers"] = "X-Request-ID"
                response.headers["Vary"] = "Origin"
        if request.method == "OPTIONS" and response.status_code == 400:
            cors_headers = {
                key: value
                for key, value in response.headers.items()
                if key.startswith("access-control-") or key == "vary"
            }
            response = error_response(
                request, 400, "CORS_REJECTED", "Cross-origin request rejected"
            )
            response.headers.update(cors_headers)
        response.headers["X-Request-ID"] = str(request.state.correlation_id)
        response.headers["Cache-Control"] = "no-store"
        logger.info(
            "request_completed",
            extra={
                "correlation_id": str(request.state.correlation_id),
                "status_code": response.status_code,
                "duration_ms": round((perf_counter() - started) * 1000, 3),
            },
        )
        return response

    router = APIRouter(
        prefix="/api/v1",
        responses={
            401: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
            500: {"model": ErrorResponse},
            503: {"model": ErrorResponse},
        },
    )

    @router.get("/health/live", response_model=LivenessResponse, tags=["health"])
    async def live() -> LivenessResponse:
        return LivenessResponse()

    @router.get("/health/ready", response_model=ReadinessResponse, tags=["health"])
    async def ready() -> ReadinessResponse:
        if not await state.is_ready(config.readiness_timeout_seconds):
            raise HTTPException(status_code=503)
        return ReadinessResponse()

    @router.get("/auth/session", response_model=SessionResponse, tags=["auth"])
    async def session(
        principal: Annotated[Principal, Depends(require_principal)],
    ) -> SessionResponse:
        return SessionResponse(
            subject_id=principal.subject_id,
            roles=sorted(principal.roles),
            expires_at=principal.expires_at,
        )

    app.include_router(router)
    app.include_router(data_router)
    return app
