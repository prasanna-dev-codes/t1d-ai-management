"""Bounded raw-image transport; no stored images, jobs or meal mutations."""

import asyncio
import threading
from typing import Annotated, Protocol
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request
from t1d_vision.contracts import Task, VisionAvailability, VisionFault, VisionResult
from t1d_vision.images import MAX_BYTES

from t1d_api.auth import Principal, require_principal
from t1d_api.db.session import Scope
from t1d_api.vision_service import VisionAccess


class VisionProvider(Protocol):
    def status(self) -> VisionAvailability: ...
    def analyze(
        self, data: bytes, mime: str, task: Task, cancel: threading.Event | None = None
    ) -> VisionResult: ...


router = APIRouter(prefix="/api/v1/patients/{patient_id}/vision")
PrincipalDep = Annotated[Principal, Depends(require_principal)]
Study = Annotated[UUID, Header(alias="X-Study-ID")]


def resources(request: Request) -> tuple[VisionAccess, VisionProvider, threading.BoundedSemaphore]:
    return (
        VisionAccess(request.app.state.database),
        request.app.state.vision_provider,
        request.app.state.vision_admission,
    )


@router.get("/model", response_model=VisionAvailability)
async def status(
    request: Request, patient_id: UUID, study: Study, principal: PrincipalDep
) -> VisionAvailability:
    access, provider, admission = resources(request)
    scope = Scope(principal.subject_id, study, patient_id)
    cid = request.state.correlation_id
    await asyncio.to_thread(access.check, scope, principal, False, cid)
    if not admission.acquire(blocking=False):
        raise VisionFault(503, "VISION_BUSY")
    try:
        result = await asyncio.to_thread(provider.status)
        await asyncio.to_thread(
            access.record,
            scope,
            principal,
            False,
            cid,
            "vision_model_status",
            result.model.model_id if result.model else None,
            result.reason_code,
            result.model.model_id if result.model else None,
        )
        return result
    finally:
        admission.release()


@router.post("/analyses", response_model=VisionResult)
async def analyze(
    request: Request,
    patient_id: UUID,
    study: Study,
    principal: PrincipalDep,
    task: Annotated[Task, Query()] = "single_label_classification",
) -> VisionResult:
    access, provider, admission = resources(request)
    scope = Scope(principal.subject_id, study, patient_id)
    cid = request.state.correlation_id
    await asyncio.to_thread(access.check, scope, principal, True, cid)
    if not admission.acquire(blocking=False):
        raise VisionFault(503, "VISION_BUSY")
    cancel = threading.Event()
    try:
        raw_length = request.headers.get("content-length")
        if raw_length is not None:
            try:
                length = int(raw_length)
            except ValueError:
                raise VisionFault(422, "INVALID_UPLOAD_METADATA") from None
            if length < 0:
                raise VisionFault(422, "INVALID_UPLOAD_METADATA")
            if length > MAX_BYTES:
                raise VisionFault(413, "PAYLOAD_TOO_LARGE")
        mime = request.headers.get("content-type", "").split(";", 1)[0].lower()
        if mime not in {"image/jpeg", "image/png"}:
            raise VisionFault(415, "UNSUPPORTED_IMAGE_FORMAT")
        body = bytearray()
        try:
            async with asyncio.timeout(10):
                async for chunk in request.stream():
                    if len(body) + len(chunk) > MAX_BYTES:
                        raise VisionFault(413, "PAYLOAD_TOO_LARGE")
                    body.extend(chunk)
        except TimeoutError:
            raise VisionFault(408, "UPLOAD_TIMEOUT") from None
        if not body:
            raise VisionFault(422, "INVALID_IMAGE")
        work = asyncio.create_task(
            asyncio.to_thread(provider.analyze, bytes(body), mime, task, cancel)
        )
        try:
            result = await asyncio.shield(work)
        except asyncio.CancelledError:
            cancel.set()
            try:
                await asyncio.shield(work)
            except (VisionFault, asyncio.CancelledError):
                pass
            raise
        await asyncio.to_thread(
            access.record,
            scope,
            principal,
            True,
            cid,
            "vision_analysis",
            result.prediction_id,
            ",".join(result.reason_codes)[:128],
            result.model.model_id,
        )
        return result
    except VisionFault as exc:
        await asyncio.to_thread(
            access.record, scope, principal, True, cid, "vision_rejected", None, exc.code
        )
        raise
    finally:
        cancel.set()
        admission.release()
