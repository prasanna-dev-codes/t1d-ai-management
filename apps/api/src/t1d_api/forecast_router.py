"""Additive protected research forecast endpoint."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request
from t1d_forecasting.contracts import ForecastRequest, ForecastResult

from t1d_api.auth import Principal, require_principal
from t1d_api.data.router import BoundedExactRoute
from t1d_api.db.session import Scope
from t1d_api.forecast_service import ForecastService

router = APIRouter(
    prefix="/api/v1/patients/{patient_id}",
    route_class=BoundedExactRoute,
    tags=["experimental-forecasting"],
)


@router.post("/forecasts", response_model=ForecastResult)
def forecast(
    request: Request,
    patient_id: UUID,
    study: Annotated[UUID, Header(alias="X-Study-ID")],
    principal: Annotated[Principal, Depends(require_principal)],
    body: ForecastRequest,
) -> ForecastResult:
    service: ForecastService = request.app.state.forecast_service
    return service.forecast(
        Scope(principal.subject_id, study, patient_id),
        principal,
        body,
        request.state.correlation_id,
    )
