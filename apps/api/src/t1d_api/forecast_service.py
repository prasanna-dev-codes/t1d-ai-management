"""Current authorization, point-in-time canonical CGM and audited synthetic forecasts."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import and_, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from t1d_forecasting.contracts import ForecastData, ForecastRequest, ForecastResult, Reading
from t1d_forecasting.engine import Abstain, digest, load_bundle, predict, snapshot

from t1d_api.auth import Principal
from t1d_api.data.errors import DataError
from t1d_api.data.service import audit, failure_audit
from t1d_api.db.models import CGMReading, DataSource, EventRevision
from t1d_api.db.session import Database, Scope, authorize
from t1d_api.memory_service import principal_check


def canonical_cgm(session: Session, scope: Scope, cutoff: datetime) -> tuple[list[Reading], bool]:
    # Resolve revisions before event-time and quality filters. Quarantine is kept
    # as an abstention signal, never replaced by an older acceptable revision.
    ranked = (
        select(
            EventRevision.id,
            func.row_number()
            .over(
                partition_by=(
                    EventRevision.source_ref,
                    EventRevision.stream_ref,
                    EventRevision.source_event_ref,
                ),
                order_by=EventRevision.revision.desc(),
            )
            .label("rank"),
        )
        .where(
            EventRevision.study_id == scope.study_id,
            EventRevision.patient_id == scope.patient_id,
            EventRevision.kind == "cgm",
            EventRevision.available_at <= cutoff,
        )
        .subquery()
    )
    rows = session.execute(
        select(EventRevision, CGMReading, DataSource)
        .select_from(EventRevision)
        .join(
            ranked,
            and_(ranked.c.id == EventRevision.id, ranked.c.rank == 1),
        )
        .join(
            CGMReading,
            and_(
                CGMReading.id == EventRevision.id, CGMReading.event_time == EventRevision.event_time
            ),
        )
        .join(
            DataSource,
            and_(
                DataSource.study_id == EventRevision.study_id,
                DataSource.source_ref == EventRevision.source_ref,
                DataSource.source_version == EventRevision.source_version,
            ),
        )
        .where(
            EventRevision.event_time >= cutoff - timedelta(minutes=65),
            EventRevision.event_time <= cutoff,
        )
        .order_by(EventRevision.event_time, EventRevision.id)
        .limit(501)
        .execution_options(populate_existing=True)
    ).all()
    if len(rows) > 500:
        raise DataError(503, "FORECAST_HISTORY_LIMIT")
    readings = []
    synthetic = True
    for revision, value, source in rows:
        synthetic = synthetic and source.source_type == "synthetic"
        if not source.approved:
            raise Abstain("SOURCE_APPROVAL_WITHDRAWN")
        readings.append(
            Reading(
                id=revision.id,
                event_time=revision.event_time,
                available_at=revision.available_at,
                value=float(value.glucose_value) if value.glucose_value is not None else None,
                unit=value.glucose_unit,
                quality=revision.quality_state,
                valid_sensor=value.sensor_status == "valid",
            )
        )
    return readings, synthetic


class ForecastService:
    def __init__(self, database: Database | None) -> None:
        self.db = database

    def forecast(
        self, scope: Scope, principal: Principal, query: ForecastRequest, correlation: UUID
    ) -> ForecastResult:
        try:
            principal_check(scope, principal)
            if query.input_cutoff > datetime.now(UTC):
                raise DataError(422, "INVALID_TIMESTAMP")
            if self.db is None:
                raise DataError(503, "DATABASE_UNAVAILABLE")
            self.db.check()
            prediction_id, evaluation_id = uuid4(), uuid4()
            with self.db.sessions.begin() as session:
                authorize(session, scope, False)
                data, reason = None, None
                fingerprint = None
                try:
                    readings, synthetic = canonical_cgm(session, scope, query.input_cutoff)
                    fingerprint = digest([r.model_dump(mode="json") for r in readings])
                    if not synthetic:
                        raise Abstain("MODEL_NOT_QUALIFIED_FOR_NONSYNTHETIC_DATA")
                    state = snapshot(readings, query.input_cutoff)
                    bundle, artifact_sha, model_id = load_bundle()
                    model = next(m for m in bundle.models if m.profile == query.model_profile)
                    data = ForecastData(
                        prediction_id=prediction_id,
                        model_version_id=model_id,
                        artifact_sha256=artifact_sha,
                        input_snapshot_ref=state.sha256,
                        source_revision_refs=[r.id for r in state.readings],
                        points=predict(state, model, query.horizons_minutes),
                    )
                    final, final_synthetic = canonical_cgm(session, scope, query.input_cutoff)
                    if (
                        not final_synthetic
                        or digest([r.model_dump(mode="json") for r in final]) != fingerprint
                    ):
                        raise DataError(503, "FORECAST_SNAPSHOT_CHANGED")
                except Abstain as exc:
                    data, reason = None, str(exc)
                principal_check(scope, principal)
                authorize(session, scope, False)
                audit(
                    session,
                    scope,
                    "forecast_" + query.model_profile,
                    "forecast",
                    prediction_id,
                    correlation,
                    source_ref=(data.input_snapshot_ref if data else reason),
                )
                return ForecastResult(
                    status="eligible" if data else "abstained",
                    input_cutoff=query.input_cutoff,
                    safety_evaluation_id=evaluation_id,
                    model_profile=query.model_profile,
                    reason_codes=[] if data else [reason or "FORECAST_UNAVAILABLE"],
                    assumptions=[
                        "CGM_ONLY",
                        "12_OBSERVED_SAMPLES_ON_EXACT_5_MINUTE_GRID",
                        "LATEST_OBSERVATION_AT_MOST_5_MINUTES_OLD",
                        "INTERVALS_CALIBRATED_ON_FICTIONAL_PATIENTS_ONLY",
                    ],
                    missing_data=[
                        "MEAL_CONTEXT_NOT_MODELED",
                        "INSULIN_CONTEXT_NOT_MODELED",
                        "ACTIVITY_CONTEXT_NOT_MODELED",
                    ],
                    warnings=[
                        "RESEARCH_ONLY",
                        "SYNTHETIC_QUALIFICATION_ONLY",
                        "NOT_FOR_TREATMENT_DECISIONS",
                        "NOMINAL_COVERAGE_NOT_A_GUARANTEE",
                    ],
                    data=data,
                )
        except (DataError, SQLAlchemyError, ValueError, OSError, ValidationError) as exc:
            code = exc.code if isinstance(exc, DataError) else "FORECAST_UNAVAILABLE"
            if self.db is not None:
                failure_audit(
                    self.db,
                    scope.actor_id,
                    "history",
                    "RESOURCE_UNAVAILABLE"
                    if code == "RESOURCE_UNAVAILABLE"
                    else "DATABASE_UNAVAILABLE",
                    correlation,
                )
            if isinstance(exc, DataError):
                raise
            raise DataError(503, "FORECAST_UNAVAILABLE") from None
