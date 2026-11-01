"""Fail-closed identity boundary; no credential parser or development bypass."""

from datetime import UTC, datetime
from typing import Annotated, Protocol
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from pydantic import AwareDatetime

from t1d_api.contracts import Contract, Role


class Principal(Contract):
    subject_id: UUID
    roles: frozenset[Role]
    expires_at: AwareDatetime


class Authenticator(Protocol):
    async def authenticate(self, request: Request) -> Principal | None: ...


class DenyAllAuthenticator:
    async def authenticate(self, request: Request) -> Principal | None:
        return None


def get_authenticator(request: Request) -> Authenticator:
    return request.app.state.authenticator  # type: ignore[no-any-return]


async def require_principal(
    request: Request,
    authenticator: Annotated[Authenticator, Depends(get_authenticator)],
) -> Principal:
    principal = await authenticator.authenticate(request)
    if principal is None or principal.expires_at <= datetime.now(UTC):
        raise HTTPException(status_code=401)
    request.state.principal_id = principal.subject_id
    return principal
