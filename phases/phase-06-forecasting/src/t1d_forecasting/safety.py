"""Final output checks for the existing synthetic forecast research policy."""

from collections.abc import Sequence
from datetime import datetime, timedelta

from pydantic import ValidationError

from t1d_forecasting.contracts import ForecastPoint, Horizon
from t1d_forecasting.engine import Abstain


def validate_forecast_points(
    points: Sequence[ForecastPoint], cutoff: datetime, horizons: tuple[Horizon, ...]
) -> list[ForecastPoint]:
    """Revalidate point payloads after computation and before any research display."""
    if (
        cutoff.utcoffset() is None
        or not horizons
        or len(set(horizons)) != len(horizons)
        or not isinstance(points, Sequence)
        or len(points) != len(horizons)
        or any(not isinstance(point, ForecastPoint) for point in points)
    ):
        raise Abstain("INVALID_FORECAST_OUTPUT")
    try:
        checked = [
            ForecastPoint.model_validate(point.model_dump(warnings=False)) for point in points
        ]
    except (AttributeError, TypeError, ValidationError) as exc:
        raise Abstain("INVALID_FORECAST_OUTPUT") from exc
    if tuple(point.horizon_minutes for point in checked) != tuple(sorted(horizons)):
        raise Abstain("INVALID_FORECAST_OUTPUT")
    if any(
        point.target_time != cutoff + timedelta(minutes=point.horizon_minutes) for point in checked
    ):
        raise Abstain("INVALID_FORECAST_OUTPUT")
    return checked
