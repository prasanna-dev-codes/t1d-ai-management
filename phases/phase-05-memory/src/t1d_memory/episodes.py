"""Deterministic episode assembly from canonical, point-in-time histories."""

import hashlib
import json
import unicodedata
from bisect import bisect_left, bisect_right
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import ValidationError

from t1d_memory.contracts import (
    DEFINITION,
    Episode,
    EpisodeDefinition,
    Event,
    GlucoseResponse,
    Nutrients,
    Source,
)


def canonical_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def definition_hash(definition: EpisodeDefinition) -> str:
    return canonical_hash(definition.model_dump(mode="json"))


def foods_and_nutrients(meal: Event) -> tuple[tuple[str, ...], Nutrients] | None:
    if (
        meal.kind != "meal"
        or meal.quality == "quarantined"
        or meal.data.get("status") != "confirmed"
    ):
        return None
    components = meal.data.get("components")
    totals = meal.data.get("nutrition_records")
    if not isinstance(components, list) or not components or not isinstance(totals, list):
        return None
    foods: set[str] = set()
    for component in components:
        if not isinstance(component, dict) or component.get("status") != "confirmed":
            return None
        label = component.get("food_reference_id") or component.get("food_label")
        if not isinstance(label, str) or not label.strip():
            return None
        foods.add(" ".join(unicodedata.normalize("NFKC", label).casefold().split()))
    aggregate = [
        row for row in totals if isinstance(row, dict) and row.get("scope") == "meal_total"
    ]
    if len(aggregate) != 1:
        return None
    try:
        nutrients = Nutrients.model_validate(
            {key: aggregate[0][key] for key in Nutrients.model_fields}
        )
    except (KeyError, ValidationError):
        return None
    return tuple(sorted(foods)), nutrients


def known_events(events: list[Event], cutoff: datetime, study: UUID, patient: UUID) -> list[Event]:
    """Resolve revisions before excluding quarantine; never resurrect a predecessor."""
    latest: dict[tuple[str, str], Event] = {}
    for event in events:
        if event.study_id != study or event.patient_id != patient or event.available_at > cutoff:
            continue
        key = event.kind, event.source_chain
        previous = latest.get(key)
        if previous is not None and previous.revision == event.revision and previous != event:
            raise ValueError("Conflicting canonical source revision")
        if previous is None or event.revision > previous.revision:
            latest[key] = event
    return sorted(
        (e for e in latest.values() if e.event_time <= cutoff and e.quality != "quarantined"),
        key=lambda e: (e.event_time, e.id.int),
    )


def build_episodes(
    events: list[Event],
    cutoff: datetime,
    study: UUID,
    patient: UUID,
    definition: EpisodeDefinition = DEFINITION,
) -> tuple[list[Episode], int]:
    if cutoff.utcoffset() is None:
        raise ValueError("Explicit cutoff timezone required")
    pool = known_events(events, cutoff, study, patient)
    times_in_pool = [e.event_time for e in pool]
    meals = [e for e in pool if e.kind == "meal"]
    meal_times = [e.event_time for e in meals]
    result: list[Episode] = []
    skipped = 0
    for meal in meals:
        content = foods_and_nutrients(meal)
        end = meal.event_time + timedelta(minutes=definition.response_minutes)
        if content is None or end > cutoff:
            skipped += 1
            continue
        context_start = meal.event_time - timedelta(minutes=definition.context_minutes)
        # Overlapping meals are retained with a warning, not attributed causally.
        sources = [meal]
        samples: dict[datetime, list[tuple[Event, Decimal]]] = {}
        # Binary-search only the relevant interval of the sorted canonical pool.
        left = bisect_left(times_in_pool, context_start)
        right = bisect_right(times_in_pool, end)
        for event in pool[left:right]:
            if event.kind == "cgm" and meal.event_time <= event.event_time <= end:
                if event.data.get("sensor_status") != "valid":
                    continue
                value = event.data.get("glucose_value")
                unit = event.data.get("glucose_unit")
                if value is None or unit not in {"mg/dL", "mmol/L"}:
                    continue
                number = Decimal(str(value))
                if not number.is_finite() or number <= 0:
                    continue
                number = number if unit == "mg/dL" else number / Decimal("0.0555")
                samples.setdefault(event.event_time, []).append((event, number))
            elif event.kind in {"insulin", "activity"} and context_start <= event.event_time <= end:
                # Full recorded interval must be known, never infer completion.
                raw_end = event.data.get("end_at") or event.data.get("delivery_end")
                if raw_end is not None and datetime.fromisoformat(str(raw_end)) > end:
                    continue
                sources.append(event)
        if len(samples) < definition.min_cgm_samples:
            skipped += 1
            continue
        # Multiple sensors disagreeing at one instant are ambiguous; do not average.
        if any(len({number for _, number in group}) != 1 for group in samples.values()):
            skipped += 1
            continue
        times = sorted(samples)
        values = [float(samples[t][0][1]) for t in times]
        for group in samples.values():
            sources.extend(event for event, _ in group)
        span = (times[-1] - times[0]).total_seconds() / (definition.response_minutes * 60)
        boundaries = [meal.event_time, *times, end]
        gap = max(
            (b - a).total_seconds() / 60 for a, b in zip(boundaries, boundaries[1:], strict=False)
        )
        if span < definition.min_span_fraction or gap > definition.max_gap_minutes:
            skipped += 1
            continue
        warnings = ["HISTORICAL_ASSOCIATION_NOT_CAUSATION", "NUTRIENT_UNCERTAINTY_PRESERVED"]
        for kind in ("insulin", "activity"):
            if not any(e.kind == kind for e in sources):
                warnings.append("UNKNOWN_" + kind.upper() + "_HISTORY")
        meal_left = bisect_left(meal_times, meal.event_time)
        meal_right = bisect_right(meal_times, end)
        if any(m.id != meal.id for m in meals[meal_left:meal_right]):
            warnings.append("OVERLAPPING_MEAL")
        if any(e.quality == "warning" for e in sources):
            warnings.append("SOURCE_QUALITY_WARNING")
        lineage = tuple(
            Source(
                id=e.id,
                kind=e.kind,
                event_time=e.event_time,
                available_at=e.available_at,
                revision=e.revision,
                source_chain=e.source_chain,
            )
            for e in sorted(sources, key=lambda e: e.id.int)
        )
        response = GlucoseResponse(
            minimum=min(values),
            maximum=max(values),
            first=values[0],
            last=values[-1],
            samples=len(times),
            observed_span_fraction=span,
            maximum_gap_minutes=gap,
        )
        foods, nutrients = content
        identity = canonical_hash(
            {
                "sources": [s.model_dump(mode="json") for s in lineage],
                "definition": definition.model_dump(mode="json"),
                "foods": foods,
                "nutrients": nutrients.model_dump(mode="json"),
                "response": response.model_dump(),
                "warnings": sorted(warnings),
                "summary": "structured-summary-v1",
                "embedding": "food-hash64-v1",
            }
        )
        result.append(
            Episode(
                id=uuid5(NAMESPACE_URL, f"t1d:{study}:{patient}:{identity}"),
                study_id=study,
                patient_id=patient,
                anchor_id=meal.id,
                start_at=meal.event_time.astimezone(UTC),
                end_at=end.astimezone(UTC),
                available_at=cutoff,
                definition_version=definition.version,
                definition_hash=definition_hash(definition),
                content_hash=identity,
                sources=lineage,
                foods=foods,
                nutrients=nutrients,
                response=response,
                warnings=tuple(sorted(warnings)),
            )
        )
    return result, skipped
