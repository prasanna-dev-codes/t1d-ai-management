"""Preserve Phase 02 scope/consent and audit boundaries for ephemeral analysis."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError

from t1d_api.auth import Principal
from t1d_api.contracts import Role
from t1d_api.data.errors import DataError
from t1d_api.data.service import failure_audit
from t1d_api.db.models import AuditEvent
from t1d_api.db.session import Database, Scope, authorize


class VisionAccess:
    def __init__(self, database: Database | None) -> None:
        self.database = database

    def check(self, scope: Scope, principal: Principal, write: bool, correlation: UUID) -> None:
        self.record(scope, principal, write, correlation, None, None, None)

    def record(
        self,
        scope: Scope,
        principal: Principal,
        write: bool,
        correlation: UUID,
        action: str | None,
        identity: UUID | None,
        reason: str | None,
        model: UUID | None = None,
    ) -> None:
        db = self.database
        if db is None:
            raise DataError(503, "DATABASE_UNAVAILABLE")
        try:
            db.check()
            if principal.expires_at <= datetime.now(UTC):
                raise DataError(401, "AUTHENTICATION_REQUIRED")
            if write and not principal.roles.intersection({Role.RESEARCHER, Role.CLINICIAN}):
                raise DataError(404, "RESOURCE_UNAVAILABLE")
            with db.sessions.begin() as session:
                authorize(session, scope, write)
                if action is not None:
                    session.add(
                        AuditEvent(
                            study_id=scope.study_id,
                            patient_id=scope.patient_id,
                            actor_ref=str(scope.actor_id),
                            action=action,
                            resource_type="vision",
                            resource_id=identity,
                            outcome="rejected" if action == "vision_rejected" else "recorded",
                            reason_code=reason,
                            correlation_id=correlation,
                            source_ref=str(model) if model else None,
                        )
                    )
        except DataError as exc:
            failure_audit(
                db,
                scope.actor_id,
                "validation",
                "UNAUTHENTICATED"
                if exc.status == 401
                else "RESOURCE_UNAVAILABLE"
                if exc.status == 404
                else "DATABASE_UNAVAILABLE",
                correlation,
            )
            raise
        except SQLAlchemyError:
            failure_audit(db, scope.actor_id, "validation", "DATABASE_UNAVAILABLE", correlation)
            raise DataError(503, "DATABASE_UNAVAILABLE") from None
