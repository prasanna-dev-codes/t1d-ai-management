"""Additional observed-history features for offline forecast comparisons."""

import math
from bisect import bisect_left, bisect_right
from datetime import datetime, timedelta

from t1d_forecasting.datasets import OfflineEvent

HISTORY_LOOKBACK = timedelta(days=2)
CONTEXT_LOOKBACK = timedelta(hours=24)
HISTORY_CGM_FEATURES = (
    (
        "cgm_change_5",
        "cgm_change_15",
        "cgm_change_30",
        "cgm_change_60",
        "cgm_change_120",
        "cgm_change_180",
        "cgm_history_60_present",
        "cgm_history_120_present",
        "cgm_history_180_present",
        "cgm_mean_180",
        "cgm_range_180",
        "cgm_summary_180_present",
        "recorded_clock_sine",
        "recorded_clock_cosine",
    )
    + tuple(
        f"cgm_clock_day_{day}_{suffix}"
        for day in (1, 2)
        for suffix in ("level", "change_120", "present")
    )
    + (
        "prior_morning_change_0400_0600",
        "prior_morning_pair_present",
    )
)
HISTORY_CONTEXT_FEATURES = (
    "recorded_carbs_240",
    "recorded_carbs_240_present",
    "recorded_carbs_age_240",
    "recorded_bolus_240",
    "recorded_bolus_240_present",
    "recorded_bolus_age_240",
    "reported_sleep_hours_24",
    "reported_sleep_hours_24_present",
    "reported_sleep_end_age_24",
    "sensor_sleep_hours_24",
    "sensor_sleep_hours_24_present",
    "sensor_sleep_end_age_24",
    "reported_exercise_intensity_240",
    "reported_exercise_intensity_240_present",
    "reported_exercise_after_bolus_minutes_240",
    "reported_exercise_after_bolus_present",
    "reported_work_hours_24",
    "reported_work_hours_24_present",
    "recorded_insulin_type_humalog",
    "recorded_insulin_type_humalog_200",
    "recorded_insulin_type_novalog",
    "recorded_insulin_type_present",
)


def extended_cgm(segment: list[OfflineEvent], index: int) -> tuple[float, ...]:
    anchor = segment[index]
    cutoff = anchor.time

    def observed(lag: int) -> float | None:
        if lag > index:
            return None
        row = segment[index - lag]
        if row.available_at is not None and row.available_at > cutoff:
            return None
        if abs((cutoff - row.time).total_seconds() - lag * 300) > 5:
            return None
        return row.value

    assert anchor.value is not None
    lags = [observed(step) for step in (1, 3, 6, 12, 24, 36)]
    features = [(anchor.value - value) / 100 if value is not None else 0.0 for value in lags]
    features.extend(float(value is not None) for value in lags[3:])
    sample = [observed(step) for step in range(0, 37, 3)]
    usable = [value for value in sample if value is not None]
    complete = len(usable) == len(sample)
    features.extend(
        (sum(usable) / len(usable) / 100, (max(usable) - min(usable)) / 100)
        if complete
        else (0.0, 0.0)
    )
    features.append(float(complete))
    # Clock features describe the source clock, without assigning a UTC offset.
    angle = math.tau * (cutoff.hour * 60 + cutoff.minute) / 1440
    features.extend((math.sin(angle), math.cos(angle)))
    for steps in (288, 576):
        previous, later = observed(steps), observed(steps - 24)
        features.extend(
            (previous / 100, (later - previous) / 100, 1.0)
            if previous is not None and later is not None
            else (0.0, 0.0, 0.0)
        )
    # Ohio documents that its de-identification preserves the local time of day.
    morning_end = cutoff.replace(hour=6, minute=0, second=0, microsecond=0)
    if morning_end > cutoff:
        morning_end -= timedelta(days=1)
    morning_lag = round((cutoff - morning_end).total_seconds() / 300)
    before, after = (
        (observed(morning_lag + 24), observed(morning_lag))
        if anchor.dataset == "ohio"
        else (None, None)
    )
    features.extend(
        ((after - before) / 100, 1.0) if before is not None and after is not None else (0.0, 0.0)
    )
    return tuple(features)


def _completed(event: OfflineEvent, cutoff: datetime) -> datetime | None:
    end = event.end_time
    if end is None and event.kind == "exercise" and event.value is not None:
        if not 0 < event.value <= 1440:
            return None
        end = event.time + timedelta(minutes=event.value)
    if event.kind in {"sleep", "sensor_sleep", "exercise", "work"} and (
        end is None or end <= event.time
    ):
        return None
    end = end or event.time
    return end if event.time <= end <= cutoff else None


def _reported_hours(rows: list[tuple[OfflineEvent, datetime]], start: datetime) -> float:
    covered = 0.0
    right = start
    for event, end in rows:
        left = max(right, event.time)
        if end > left:
            covered += (end - left).total_seconds() / 3600
            right = end
    return covered


def extended_context(
    context: list[OfflineEvent],
    times: list[datetime],
    cutoff: datetime,
    replay: bool,
) -> tuple[float, ...]:
    past_day = cutoff - CONTEXT_LOOKBACK
    # Include intervals that started the prior day but ended inside the window.
    left = bisect_left(times, cutoff - HISTORY_LOOKBACK)
    right = bisect_right(times, cutoff)
    recent = cutoff - timedelta(hours=4)
    sleep, sensor_sleep, work, carbs, boluses, exercises = [], [], [], [], [], []
    insulin_types = set()
    for event in context[left:right]:
        if event.available_at is None:
            if not replay:
                continue
        elif event.available_at > cutoff:
            continue
        end = _completed(event, cutoff)
        if end is None:
            continue
        if event.kind == "sleep" and end > past_day:
            sleep.append((event, end))
        elif event.kind == "sensor_sleep" and end > past_day:
            sensor_sleep.append((event, end))
        elif event.kind == "work" and end > past_day:
            work.append((event, end))
        elif event.kind == "bolus" and event.unit == "U" and event.value is not None:
            if event.insulin_type and end >= past_day:
                insulin_types.add(event.insulin_type.strip().casefold())
            if event.time >= recent:
                boluses.append((event, end))
        elif (
            event.kind == "carbohydrate"
            and event.unit == "g"
            and event.value is not None
            and event.time >= recent
        ):
            carbs.append((event, end))
        elif (
            event.kind == "exercise"
            and event.unit == "minutes"
            and event.value is not None
            and event.time >= recent
        ):
            exercises.append(event)

    def age(end: datetime, hours: int) -> float:
        return (cutoff - end).total_seconds() / (hours * 3600)

    output: list[float] = []
    for observations, scale in ((carbs, 100), (boluses, 10)):
        output.extend(
            (
                sum(event.value or 0.0 for event, _ in observations) / scale,
                float(bool(observations)),
                age(max(end for _, end in observations), 4) if observations else 0.0,
            )
        )
    for records in (sleep, sensor_sleep):
        output.extend(
            (
                _reported_hours(records, past_day) / 24,
                float(bool(records)),
                age(max(end for _, end in records), 24) if records else 0.0,
            )
        )
    intensities = [event.intensity for event in exercises if event.intensity is not None]
    after_bolus = [
        event
        for event in exercises
        if any(end < event.time and (bolus.value or 0) > 0 for bolus, end in boluses)
    ]
    output.extend(
        (
            max(intensities, default=0.0) / 10,
            float(bool(intensities)),
            sum(event.value or 0.0 for event in after_bolus) / 60,
            float(bool(after_bolus)),
            _reported_hours(work, past_day) / 24,
            float(bool(work)),
        )
    )
    insulin_type = next(iter(insulin_types)) if len(insulin_types) == 1 else ""
    output.extend(float(insulin_type == value) for value in ("humalog", "humalog 200", "novalog"))
    output.append(float(bool(insulin_type)))
    return tuple(output)
