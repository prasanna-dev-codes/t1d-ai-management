"""Additive authenticated Phase 05 routes, reusing existing identity and errors."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request
from t1d_memory.contracts import RebuildRequest, RebuildResult, RetrievalRequest, RetrievalResult

from t1d_api.auth import Principal, require_principal
from t1d_api.data.router import BoundedExactRoute
from t1d_api.db.session import Scope
from t1d_api.memory_service import MemoryService

router = APIRouter(
    prefix="/api/v1/patients/{patient_id}",
    route_class=BoundedExactRoute,
    tags=["experimental-memory"],
)
PrincipalDep = Annotated[Principal, Depends(require_principal)]
Study = Annotated[UUID, Header(alias="X-Study-ID")]


@router.post("/memory/rebuild", response_model=RebuildResult)
def rebuild(
    request: Request, patient_id: UUID, study: Study, principal: PrincipalDep, body: RebuildRequest
) -> RebuildResult:
    service: MemoryService = request.app.state.memory_service
    return service.rebuild(
        Scope(principal.subject_id, study, patient_id), principal, request.state.correlation_id
    )


@router.post("/historical-retrievals", response_model=RetrievalResult)
def retrieve(
    request: Request,
    patient_id: UUID,
    study: Study,
    principal: PrincipalDep,
    body: RetrievalRequest,
) -> RetrievalResult:
    service: MemoryService = request.app.state.memory_service
    return service.retrieve(
        Scope(principal.subject_id, study, patient_id),
        principal,
        body,
        request.state.correlation_id,
    )
