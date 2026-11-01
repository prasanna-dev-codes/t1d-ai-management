"""Phase 01 response source of truth; TypeScript is generated from these models."""

from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class LivenessResponse(Contract):
    status: Literal["alive"] = "alive"


class ReadinessResponse(Contract):
    status: Literal["ready"] = "ready"


class ErrorDetail(Contract):
    field: str
    reason: str


class ErrorBody(Contract):
    code: str
    message: str
    details: list[ErrorDetail]
    correlation_id: UUID


class ErrorResponse(Contract):
    error: ErrorBody


class Role(StrEnum):
    RESEARCHER = "researcher"
    CLINICIAN = "clinician"
    PARTICIPANT = "participant"
    ADMINISTRATOR = "administrator"


class SessionResponse(Contract):
    subject_id: UUID
    roles: list[Role]
    expires_at: datetime
