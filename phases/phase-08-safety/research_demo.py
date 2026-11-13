"""Local Phase 08 exercise of the Phase 02, 05, 06 and 07 research interfaces."""

import argparse
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID, uuid4

import numpy as np
from adaptation import WARMUP, ForecastQuery, replay
from canonical_memory import summarize
from meal_memory import METHOD as MEAL_MEMORY
from meal_memory import MealAnchor
from t1d_api.data.schemas import MealInput
from t1d_forecasting.contracts import HORIZONS, ForecastModel, ForecastPoint, Reading
from t1d_forecasting.engine import Abstain, digest, load_bundle, predict, snapshot
from t1d_forecasting.experiment import Example, examples
from t1d_forecasting.safety import validate_forecast_points
from t1d_forecasting.windows import HISTORY_FEATURE_NAMES, Window
from t1d_memory.contracts import DEFINITION, Event, RetrievalResult
from t1d_memory.episodes import build_episodes, definition_hash, foods_and_nutrients, known_events
from t1d_memory.ranking import rank
from t1d_memory.synthetic import STUDY

Scenario = Literal[
    "warm", "cold", "unconfirmed", "stale", "memory-unavailable", "audit-unavailable"
]
SCENARIOS: tuple[Scenario, ...] = (
    "warm",
    "cold",
    "unconfirmed",
    "stale",
    "memory-unavailable",
    "audit-unavailable",
)
_CORRECTIONS = ("context-offset", MEAL_MEMORY)


@dataclass(frozen=True)
class Fixture:
    cutoff: datetime
    patient: UUID
    meal: Event
    events: tuple[Event, ...]
    readings: tuple[Reading, ...]
    past: tuple[Example, ...]


@dataclass(frozen=True)
class AuditEntry:
    evaluation_id: UUID
    cutoff: datetime
    model_sha256: str | None
    snapshot_sha256: str | None
    outcome: str


@dataclass(frozen=True)
class Outcome:
    audit: AuditEntry
    forecasts: dict[str, list[ForecastPoint]]
    evidence_refs: tuple[UUID, ...] = ()
    personalization: str = "unavailable"

    def payload(self) -> dict[str, object]:
        return {
            "status": "eligible" if self.forecasts else "abstained",
            "reason_codes": [] if self.forecasts else [self.audit.outcome],
            "experimental": True,
            "review_required": True,
            "input_cutoff": self.audit.cutoff.isoformat(),
            "safety_evaluation_id": str(self.audit.evaluation_id),
            "model_sha256": self.audit.model_sha256,
            "input_snapshot_sha256": self.audit.snapshot_sha256,
            "evidence_refs": [str(reference) for reference in self.evidence_refs],
            "personalization": self.personalization,
            "assumptions": [
                "AUTHORED_SYNTHETIC_FIXTURE",
                "PHASE06_SYNTHETIC_CGM_POLICY",
                "PERSONALIZED_INTERVALS_ILLUSTRATIVE",
            ],
            "missing_data": ["INSULIN_AND_ACTIVITY_CONTEXT_UNAVAILABLE"]
            + (["PERSONAL_HISTORY_UNAVAILABLE"] if self.personalization == "cold" else []),
            "warnings": ["OFFLINE_RESEARCH_ONLY", "HUMAN_REVIEW_REQUIRED"],
            "data": {
                name: [point.model_dump(mode="json") for point in points]
                for name, points in self.forecasts.items()
            }
            if self.forecasts
            else None,
        }


def _confirmed_meal(
    example: Example, index: int, confirmed: bool, draft: Event | None = None
) -> Event:
    totals = {
        "carbohydrate_g": "35",
        "protein_g": "5",
        "fat_g": "2",
        "energy_kcal": "178",
        "reference_ref": "fixture:food-reference",
        "method_version": "fixture:reviewed-v1",
        "uncertainty_status": "source_reported",
    }
    meal = MealInput.model_validate(
        {
            "source_event_ref": f"fixture:meal-{index}",
            "event_time": example.cutoff,
            "revision": 2 if draft is not None else 1,
            "supersedes_id": draft.id if draft is not None else None,
            "provenance": {
                "source_type": "synthetic",
                "source_ref": "fixture:meal-review",
                "source_version": "1",
                "recorded_at": example.cutoff,
            },
            "status": "confirmed" if confirmed else "draft",
            "components": [
                {
                    "food_label": "Fictional breakfast",
                    "food_reference_id": "fixture:breakfast",
                    "portion_value": "100",
                    "portion_unit": "g",
                    "status": "confirmed" if confirmed else "proposed",
                    "nutrition": totals,
                }
            ],
            "nutrition": totals,
        }
    )
    return Event(
        id=UUID(int=(2000 if draft is not None else 1000) + index),
        study_id=STUDY,
        patient_id=example.patient,
        kind="meal",
        event_time=meal.event_time,
        available_at=meal.provenance.recorded_at,
        quality="accepted",
        revision=meal.revision,
        source_chain=meal.source_event_ref,
        data={
            "status": meal.status,
            "components": [component.model_dump(mode="json") for component in meal.components],
            "nutrition_records": [{"scope": "meal_total", **meal.nutrition.model_dump(mode="json")}]
            if meal.nutrition
            else [],
        },
    )


def fixture(scenario: Scenario, windows: int = 80) -> Fixture:
    series = examples(range(60, 61), windows=windows)
    current = series[-1]
    past = tuple(series[:-1]) if scenario != "cold" else ()
    events: list[Event] = []
    for index, item in enumerate(past):
        meal = _confirmed_meal(item, index, True)
        events.append(meal)
        for horizon, value in zip(HORIZONS, item.targets, strict=True):
            time = item.cutoff + timedelta(minutes=horizon)
            events.append(
                Event(
                    id=UUID(int=10000 + index * 4 + horizon // 30),
                    study_id=STUDY,
                    patient_id=item.patient,
                    kind="cgm",
                    event_time=time,
                    available_at=time,
                    quality="accepted",
                    revision=1,
                    source_chain=f"fixture:outcome-{index}-{horizon}",
                    data={
                        "glucose_value": value,
                        "glucose_unit": "mg/dL",
                        "sensor_status": "valid",
                    },
                )
            )
    draft = _confirmed_meal(current, len(past), False)
    anchor = (
        draft if scenario == "unconfirmed" else _confirmed_meal(current, len(past), True, draft)
    )
    events.append(draft)
    if anchor.id != draft.id:
        events.append(anchor)
    readings = current.readings
    if scenario == "stale":
        readings = tuple(
            Reading.model_validate(
                reading.model_dump()
                | {
                    "event_time": reading.event_time - timedelta(minutes=6),
                    "available_at": reading.available_at - timedelta(minutes=6),
                }
            )
            for reading in readings
        )
    return Fixture(current.cutoff, current.patient, anchor, tuple(events), readings, past)


def retrieve(data: Fixture, anchor: Event) -> RetrievalResult:
    content = foods_and_nutrients(anchor)
    if content is None:
        raise Abstain("MEAL_UNCONFIRMED")
    foods, nutrients = content
    episodes, _ = build_episodes(list(data.events), data.cutoff, STUDY, data.patient)
    selected = rank(
        [episode for episode in episodes if episode.anchor_id != anchor.id],
        foods,
        nutrients,
        "structured-v1",
        5,
    )
    return RetrievalResult(
        retrieval_id=uuid4(),
        status="evidence" if selected else "abstained",
        input_cutoff=data.cutoff,
        retrieval_profile_version="structured-v1",
        definition_version=DEFINITION.version,
        definition_hash=definition_hash(DEFINITION),
        embedding_version=None,
        index_watermark=None,
        episodes=selected,
        reason_codes=[] if selected else ["NO_ELIGIBLE_HISTORY"],
        warnings=["AUTHORED_SYNTHETIC_FIXTURE"],
        audit_reference=uuid4(),
    )


def _features(readings: tuple[Reading, ...]) -> tuple[float, ...]:
    first, last = readings[-4].value, readings[-1].value
    assert first is not None and last is not None
    values = {
        "cgm_change_15": (last - first) / 100,
        "recorded_carbs_240_present": 1.0,
    }
    return tuple(values.get(key, 0.0) for key in HISTORY_FEATURE_NAMES)


def _prediction_history(
    data: Fixture, model: ForecastModel, evidence: dict[UUID, Event], visible: list[Event]
) -> tuple[list[Window], list[list[float]], list[MealAnchor | None]]:
    history: list[Window] = []
    predictions: list[list[float]] = []
    meals: list[MealAnchor | None] = []
    observed = {event.id: event for event in visible if event.kind == "cgm"}
    for index, item in enumerate(data.past):
        end = item.cutoff + timedelta(minutes=120)
        if item.patient != data.patient or end > data.cutoff:
            continue
        targets: list[float] = []
        available = end
        for horizon in HORIZONS:
            measurement = observed.get(UUID(int=10000 + index * 4 + horizon // 30))
            if (
                measurement is None
                or measurement.event_time != item.cutoff + timedelta(minutes=horizon)
                or measurement.quality != "accepted"
                or measurement.data.get("glucose_unit") != "mg/dL"
                or measurement.data.get("sensor_status") != "valid"
            ):
                break
            value = measurement.data.get("glucose_value")
            if not isinstance(value, int | float) or isinstance(value, bool):
                break
            targets.append(float(value))
            available = max(available, measurement.available_at)
        if len(targets) != len(HORIZONS):
            continue
        state = snapshot(list(item.readings), item.cutoff)
        history.append(
            Window(
                "synthetic-demo",
                str(data.patient),
                "fixture",
                item.readings[0].event_time,
                item.cutoff,
                end,
                _features(state.readings),
                tuple(targets),
                state.sha256,
                label_available_at=available,
            )
        )
        predictions.append([point.glucose_mg_dl for point in predict(state, model, HORIZONS)])
        anchor = evidence.get(UUID(int=1000 + index))
        content = foods_and_nutrients(anchor) if anchor else None
        meals.append(
            MealAnchor(
                ("fixture:meal", anchor.id.int),
                anchor.event_time,
                0,
                float(content[1].carbohydrate_g),
            )
            if anchor is not None and content is not None
            else None
        )
    return history, predictions, meals


def run(
    data: Fixture,
    memory: Callable[[Fixture, Event], RetrievalResult] | None,
    audit: Callable[[AuditEntry], None],
) -> Outcome:
    evaluation = uuid4()
    model_sha = snapshot_sha = None
    outcome = "eligible"
    forecasts: dict[str, list[ForecastPoint]] = {}
    ids: tuple[UUID, ...] = ()
    personal = "unavailable"
    try:
        visible = known_events(list(data.events), data.cutoff, STUDY, data.patient)
        anchor = next((event for event in visible if event.id == data.meal.id), None)
        if anchor is None or (content := foods_and_nutrients(anchor)) is None:
            raise Abstain("MEAL_UNCONFIRMED_OR_UNAVAILABLE")
        state = snapshot(list(data.readings), data.cutoff)
        if memory is None:
            raise Abstain("MEMORY_UNAVAILABLE")
        try:
            retrieved = memory(data, anchor)
        except OSError as exc:
            raise Abstain("MEMORY_UNAVAILABLE") from exc
        if retrieved.status == "abstained" and retrieved.reason_codes != ["NO_ELIGIBLE_HISTORY"]:
            raise Abstain("MEMORY_UNAVAILABLE")
        try:
            evidence = summarize(retrieved, data.cutoff, anchor.id, anchor.event_time)
            episodes, _ = build_episodes(list(data.events), data.cutoff, STUDY, data.patient)
            canonical = {item.id: item for item in episodes}
            for item in retrieved.episodes:
                trusted = canonical.get(item.episode_id)
                if (
                    trusted is None
                    or trusted.anchor_id != item.anchor_meal_id
                    or trusted.start_at != item.event_time
                    or trusted.response != item.response
                    or trusted.available_at > item.available_at
                    or set(item.source_revision_refs) != {source.id for source in trusted.sources}
                ):
                    raise ValueError("Evidence differs from the same-scope canonical episode")
        except ValueError as exc:
            raise Abstain("MEMORY_EVIDENCE_INVALID") from exc
        ids = evidence.episode_ids
        available_meals = {
            event.id: event
            for event in visible
            if event.id in {canonical[episode_id].anchor_id for episode_id in ids}
        }
        bundle, model_sha, _ = load_bundle()
        model = next(item for item in bundle.models if item.profile == "ridge-v1")
        base = validate_forecast_points(predict(state, model, HORIZONS), data.cutoff, HORIZONS)
        history, prior, meals = _prediction_history(data, model, available_meals, visible)
        meal = MealAnchor(
            ("fixture:meal", anchor.id.int), anchor.event_time, 0, float(content[1].carbohydrate_g)
        )
        first = history[0].cutoff if history else data.cutoff
        result = replay(
            history,
            np.asarray(prior + [[point.glucose_mg_dl for point in base]]),
            first + WARMUP,
            [True] * len(history),
            meals + [meal],
            query=ForecastQuery(
                f"synthetic-demo:{data.patient}", data.cutoff, _features(state.readings)
            ),
        )
        forecasts = {"phase06": base}
        for name, method in zip(("phase07", "phase07_with_memory"), _CORRECTIONS, strict=True):
            adjusted = [
                point.model_copy(
                    update={
                        field: getattr(point, field)
                        + float(result.predictions[method][-1, i] - point.glucose_mg_dl)
                        for field in ("glucose_mg_dl", "lower_mg_dl", "upper_mg_dl")
                    }
                )
                for i, point in enumerate(base)
            ]
            forecasts[name] = validate_forecast_points(adjusted, data.cutoff, HORIZONS)
        personal = "warm" if result.rolling_support[-1] else "cold"
        snapshot_sha = digest(
            {
                "cgm": state.sha256,
                "anchor": anchor.id,
                "memory": ids,
                "feedback": [
                    (row.input_ref, row.label_available_at, row.targets) for row in history
                ],
            }
        )
    except Abstain as exc:
        forecasts, ids, outcome = {}, (), str(exc)
    except (OSError, ValueError):
        forecasts, ids, outcome = {}, (), "RESEARCH_DEPENDENCY_UNAVAILABLE"
    record = AuditEntry(evaluation, data.cutoff, model_sha, snapshot_sha, outcome)
    try:
        audit(record)
    except OSError:
        record = AuditEntry(evaluation, data.cutoff, model_sha, snapshot_sha, "AUDIT_UNAVAILABLE")
        return Outcome(record, {})
    return Outcome(record, forecasts, ids, personal)


def paired_comparison() -> dict[str, object]:
    """Score all three branches on the same fictional forecast cutoffs."""
    cases = range(73, 81)
    targets = examples(range(60, 61), windows=max(cases))
    errors: dict[str, list[list[float]]] = {}
    trail: list[AuditEntry] = []
    for count in cases:
        result = run(fixture("warm", count), retrieve, trail.append)
        if not result.forecasts:
            continue
        for model, points in result.forecasts.items():
            errors.setdefault(model, []).append(
                [
                    abs(point.glucose_mg_dl - observed)
                    for point, observed in zip(points, targets[count - 1].targets, strict=True)
                ]
            )
    return {
        "experimental": True,
        "data_kind": "authored-synthetic-only",
        "cases": len(cases),
        "scored": len(errors.get("phase06", [])),
        "mae_mg_dl": {model: np.mean(values, axis=0).tolist() for model, values in errors.items()},
    }


def unavailable_audit(entry: AuditEntry) -> None:
    raise OSError("Fixture audit store unavailable")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=(*SCENARIOS, "all"), default="all")
    parser.add_argument("--comparison", action="store_true")
    args = parser.parse_args()
    if args.comparison:
        print(json.dumps(paired_comparison(), allow_nan=False))
        return
    cases = SCENARIOS if args.scenario == "all" else (args.scenario,)
    for case in cases:
        trail: list[AuditEntry] = []

        output = run(
            fixture(case),
            None if case == "memory-unavailable" else retrieve,
            unavailable_audit if case == "audit-unavailable" else trail.append,
        )
        print(json.dumps({"scenario": case, **output.payload()}, allow_nan=False))


if __name__ == "__main__":
    main()
