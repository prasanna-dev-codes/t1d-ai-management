"""Thin authenticated ingestion/history routers with exact JSON decoding."""

import json
from collections.abc import Callable, Coroutine
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.routing import APIRoute
from starlette.responses import Response

from t1d_api.auth import Principal, require_principal
from t1d_api.data.errors import DataError
from t1d_api.data.schemas import (
    ActivityBatch,
    AuditPage,
    CGMBatch,
    CGMReceipt,
    EventReceipt,
    ExplicitTime,
    HistoryPage,
    InsulinBatch,
    Kind,
    MealBatch,
    MealReceipt,
)
from t1d_api.data.service import DataService
from t1d_api.db.session import Database, Scope


class ExactRequest(Request):
    async def json(self) -> Any:
        if not hasattr(self, "_json"):
            try:
                self._json = json.loads(
                    await self.body(),
                    parse_float=Decimal,
                    parse_constant=lambda value: (_ for _ in ()).throw(ValueError()),
                )
            except (ValueError, UnicodeError) as exc:
                raise DataError(422, "INVALID_INPUT") from exc
        return self._json


class BoundedExactRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original = super().get_route_handler()

        async def handle(request: Request) -> Response:
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > 1_048_576:
                    raise DataError(413, "PAYLOAD_TOO_LARGE")
            exact = ExactRequest(request.scope, request.receive)
            exact._body = bytes(body)
            content_type = request.headers.get("content-type", "application/json").split(";", 1)[0]
            if body and (content_type == "application/json" or content_type.endswith("+json")):
                await exact.json()
            return await original(exact)

        return handle


router = APIRouter(
    prefix="/api/v1/patients/{patient_id}",
    route_class=BoundedExactRoute,
    responses={
        401: {"description": "Unauthenticated"},
        404: {"description": "Unavailable scope"},
        409: {"description": "Idempotency/revision conflict"},
        422: {"description": "Invalid input"},
        503: {"description": "Database unavailable"},
    },
)
PrincipalDep = Annotated[Principal, Depends(require_principal)]
StudyHeader = Annotated[UUID, Header(alias="X-Study-ID")]
KeyHeader = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)]


def database(request: Request) -> Database:
    value: Database | None = request.app.state.database
    if value is None:
        raise DataError(503, "DATABASE_UNAVAILABLE")
    return value


def ingest(
    request: Request,
    patient_id: UUID,
    study: UUID,
    principal: Principal,
    kind: Kind,
    key: str,
    items: list[Any],
) -> dict[str, Any]:
    return DataService(database(request)).ingest(
        Scope(principal.subject_id, study, patient_id),
        principal,
        kind,
        items,
        key,
        request.state.correlation_id,
    )


@router.post("/cgm-readings", response_model=CGMReceipt, status_code=201)
def cgm(
    request: Request,
    patient_id: UUID,
    principal: PrincipalDep,
    study: StudyHeader,
    key: KeyHeader,
    body: CGMBatch,
) -> dict[str, Any]:
    return ingest(request, patient_id, study, principal, "cgm", key, body.readings)


@router.post("/meals", response_model=MealReceipt, status_code=201)
def meals(
    request: Request,
    patient_id: UUID,
    principal: PrincipalDep,
    study: StudyHeader,
    key: KeyHeader,
    body: MealBatch,
) -> dict[str, Any]:
    return ingest(request, patient_id, study, principal, "meal", key, body.meals)


@router.post("/insulin-events", response_model=EventReceipt, status_code=201)
def insulin(
    request: Request,
    patient_id: UUID,
    principal: PrincipalDep,
    study: StudyHeader,
    key: KeyHeader,
    body: InsulinBatch,
) -> dict[str, Any]:
    return ingest(request, patient_id, study, principal, "insulin", key, body.events)


@router.post("/activity-events", response_model=EventReceipt, status_code=201)
def activity(
    request: Request,
    patient_id: UUID,
    principal: PrincipalDep,
    study: StudyHeader,
    key: KeyHeader,
    body: ActivityBatch,
) -> dict[str, Any]:
    return ingest(request, patient_id, study, principal, "activity", key, body.events)


history_paths: list[tuple[str, Kind]] = [
    ("cgm-readings", "cgm"),
    ("meals", "meal"),
    ("insulin-events", "insulin"),
    ("activity-events", "activity"),
]
for path, kind in history_paths:

    def history_handler(selected: Kind) -> Callable[..., dict[str, Any]]:
        def history(
            request: Request,
            patient_id: UUID,
            principal: PrincipalDep,
            study: StudyHeader,
            cutoff: Annotated[ExplicitTime, Query()],
            limit: Annotated[int, Query(ge=1, le=200)] = 100,
            cursor: Annotated[str | None, Query(max_length=512)] = None,
        ) -> dict[str, Any]:
            return DataService(database(request)).history(
                Scope(principal.subject_id, study, patient_id),
                selected,
                cutoff,
                limit,
                cursor,
                request.state.correlation_id,
            )

        return history

    router.add_api_route(
        "/" + path,
        history_handler(kind),
        methods=["GET"],
        response_model=HistoryPage,
        name="history_" + kind,
    )


@router.get("/audit-events", response_model=AuditPage)
def audits(
    request: Request,
    patient_id: UUID,
    principal: PrincipalDep,
    study: StudyHeader,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
) -> dict[str, Any]:
    return DataService(database(request)).audit_history(
        Scope(principal.subject_id, study, patient_id),
        principal,
        limit,
        cursor,
        request.state.correlation_id,
    )
