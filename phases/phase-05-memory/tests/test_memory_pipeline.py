"""Synthetic episode, lineage, ranking and adversarial regression tests."""

from datetime import timedelta
from uuid import UUID

import pytest
from pydantic import ValidationError
from t1d_memory.contracts import DEFINITION, Nutrients, RetrievalRequest
from t1d_memory.episodes import build_episodes, foods_and_nutrients, known_events
from t1d_memory.evaluation import metrics
from t1d_memory.ranking import cosine, embed, nutrient_similarity, rank
from t1d_memory.synthetic import PATIENT, START, STUDY, cohort, meal

CUTOFF = START + timedelta(days=60)


def test_deterministic_build_and_explicit_missingness() -> None:
    events = cohort()
    first, skipped = build_episodes(events, CUTOFF, STUDY, PATIENT)
    second, _ = build_episodes(list(reversed(events)), CUTOFF, STUDY, PATIENT)
    assert skipped == 0 and len(first) == 12
    assert first == second
    assert first[0].response.samples == 25
    assert first[0].response.minimum == 100 and first[0].response.maximum == 124
    assert "UNKNOWN_INSULIN_HISTORY" in first[0].warnings
    assert "UNKNOWN_ACTIVITY_HISTORY" in first[0].warnings
    assert all(source.available_at <= first[0].available_at for source in first[0].sources)


def test_incomplete_future_and_bad_quality_are_excluded() -> None:
    events = cohort(1)
    for data in ([events[0]], events[:2], events):
        result, _ = build_episodes(data, START + timedelta(minutes=119), STUDY, PATIENT)
        assert result == []
    events[0] = events[0].model_copy(update={"quality": "quarantined"})
    assert build_episodes(events, CUTOFF, STUDY, PATIENT)[0] == []


def test_revision_selection_precedes_quarantine() -> None:
    events = cohort(1)
    correction = events[0].model_copy(
        update={
            "id": UUID(int=999),
            "revision": 2,
            "quality": "quarantined",
            "available_at": START + timedelta(days=3),
        }
    )
    assert (
        len(build_episodes(events + [correction], START + timedelta(days=2), STUDY, PATIENT)[0])
        == 1
    )
    assert build_episodes(events + [correction], CUTOFF, STUDY, PATIENT)[0] == []


def test_late_arrival_changes_identity_only_when_known() -> None:
    events = cohort(1)
    original = build_episodes(events, CUTOFF, STUDY, PATIENT)[0][0]
    late = events[1].model_copy(
        update={
            "id": UUID(int=777),
            "revision": 2,
            "available_at": CUTOFF + timedelta(seconds=1),
            "data": {**events[1].data, "glucose_value": "150"},
        }
    )
    assert build_episodes(events + [late], CUTOFF, STUDY, PATIENT)[0][0].id == original.id
    assert (
        build_episodes(events + [late], CUTOFF + timedelta(seconds=2), STUDY, PATIENT)[0][0].id
        != original.id
    )


@pytest.mark.parametrize("field", ["study_id", "patient_id"])
def test_foreign_records_do_not_change_episode(field: str) -> None:
    events = cohort(1)
    foreign = [e.model_copy(update={field: UUID(int=999999)}) for e in cohort(2)]
    assert build_episodes(events + foreign, CUTOFF, STUDY, PATIENT) == build_episodes(
        events, CUTOFF, STUDY, PATIENT
    )


def test_conflicting_source_revisions_fail_closed() -> None:
    original = meal(1)
    with pytest.raises(ValueError, match="Conflicting"):
        known_events(
            [original, original.model_copy(update={"id": UUID(int=9)})], CUTOFF, STUDY, PATIENT
        )


def test_ambiguous_simultaneous_sensors_not_averaged() -> None:
    events = cohort(1)
    conflict = events[1].model_copy(
        update={
            "id": UUID(int=9),
            "source_chain": "other-sensor",
            "data": {**events[1].data, "glucose_value": "200"},
        }
    )
    assert build_episodes(events + [conflict], CUTOFF, STUDY, PATIENT)[0] == []


def test_sensor_gap_rejected_and_definition_changes_identity() -> None:
    events = cohort(1)
    sparse = [e for i, e in enumerate(events) if i < 5 or i > 18]
    assert build_episodes(sparse, CUTOFF, STUDY, PATIENT)[0] == []
    first = build_episodes(events, CUTOFF, STUDY, PATIENT)[0][0]
    changed = DEFINITION.model_copy(update={"version": "research-custom-v2", "max_gap_minutes": 20})
    assert build_episodes(events, CUTOFF, STUDY, PATIENT, changed)[0][0].id != first.id


def test_explicit_unit_conversion_and_no_unit_guess() -> None:
    events = cohort(1)
    for index in range(1, len(events)):
        events[index] = events[index].model_copy(
            update={
                "data": {
                    "glucose_value": "5.55",
                    "glucose_unit": "mmol/L",
                    "sensor_status": "valid",
                }
            }
        )
    assert build_episodes(events, CUTOFF, STUDY, PATIENT)[0][0].response.first == 100
    for index in range(1, len(events)):
        events[index] = events[index].model_copy(
            update={"data": {"glucose_value": "100", "sensor_status": "valid"}}
        )
    assert build_episodes(events, CUTOFF, STUDY, PATIENT)[0] == []


def test_unconfirmed_or_missing_nutrition_cannot_enter_memory() -> None:
    for data in ({"status": "draft"}, {"status": "confirmed", "components": []}):
        assert foods_and_nutrients(meal(1).model_copy(update={"data": data})) is None
    with pytest.raises(ValidationError):
        Nutrients.model_validate(
            dict(carbohydrate_g="NaN", protein_g="1", fat_g="1", energy_kcal="1")
        )


def test_embedding_stability_and_nonclinical_ranking() -> None:
    assert embed(("a", "b")) == embed(("b", "a", "a"))
    assert cosine(embed(("a",)), embed(("a",))) == pytest.approx(1)
    episodes = build_episodes(cohort(6), CUTOFF, STUDY, PATIENT)[0]
    anchor = episodes[0]
    scores = {str(e.id): cosine(embed(anchor.foods), embed(e.foods)) for e in episodes}
    graphs = {
        str(e.id): len(set(anchor.foods) & set(e.foods)) / len(set(anchor.foods) | set(e.foods))
        for e in episodes
    }
    for profile in ("structured-v1", "vector-v1", "hybrid-v1"):
        result = rank(episodes, anchor.foods, anchor.nutrients, profile, 3, scores, graphs)
        assert len(result) == 3 and all(0 <= e.score <= 1 for e in result)
    assert nutrient_similarity(anchor.nutrients, anchor.nutrients) == 1
    with pytest.raises(ValueError, match="no silent fallback"):
        rank(episodes, anchor.foods, anchor.nutrients, "vector-v1", 3)


@pytest.mark.parametrize("bad", [0, 21])
def test_ranking_limits(bad: int) -> None:
    nutrients = Nutrients.model_validate(
        dict(carbohydrate_g="0", protein_g="0", fat_g="0", energy_kcal="0")
    )
    with pytest.raises(ValueError):
        rank([], ("a",), nutrients, "structured-v1", bad)


@pytest.mark.parametrize("when", [1234567890, "1234567890", "2020-01-01", "2020-01-01T12:00:00"])
def test_query_requires_explicit_timezone(when: object) -> None:
    with pytest.raises(ValidationError):
        RetrievalRequest.model_validate({"input_cutoff": when, "anchor_meal_id": str(UUID(int=1))})


def test_hand_calculated_ranking_metrics() -> None:
    result = metrics(["a", "b", "c"], {"a", "c", "d"}, 3)
    assert result["precision_at_k"] == pytest.approx(2 / 3)
    assert result["recall_at_k"] == pytest.approx(2 / 3)
    assert result["ndcg_at_k"] == pytest.approx(1.5 / (1 + 1 / 1.584962500721156 + 0.5))
    assert result["reciprocal_rank"] == 1
    assert metrics([], set(), 3)["ndcg_at_k"] == 0
    with pytest.raises(ValueError):
        metrics(["a", "a"], {"a"}, 3)


def test_optimized_window_keeps_inclusive_context_boundaries() -> None:
    events = cohort(1)
    anchor = events[0]
    added = []
    for i, minutes in enumerate((-121, -120, 120, 121)):
        added.append(
            anchor.model_copy(
                update={
                    "id": UUID(int=800 + i),
                    "kind": "insulin",
                    "source_chain": f"boundary-{i}",
                    "event_time": anchor.event_time + timedelta(minutes=minutes),
                    "available_at": anchor.event_time + timedelta(minutes=minutes),
                    "data": {},
                }
            )
        )
    assembled, _ = build_episodes(events + added, CUTOFF, STUDY, PATIENT)
    identities = {source.id for source in assembled[0].sources}
    assert added[1].id in identities and added[2].id in identities
    assert added[0].id not in identities and added[3].id not in identities
    assert assembled == build_episodes(list(reversed(events + added)), CUTOFF, STUDY, PATIENT)[0]
