"""Evaluation integrity, independent labels and honest uncertainty handling."""

from datetime import timedelta
from uuid import UUID

import pytest
from pydantic import ValidationError
from t1d_memory.benchmark import (
    Benchmark,
    JudgedQuery,
    clustered_interval,
    eligible,
    evaluate_benchmark,
)
from t1d_memory.episodes import build_episodes
from t1d_memory.synthetic import PATIENT, START, STUDY, cohort


def fixture() -> Benchmark:
    episodes, _ = build_episodes(cohort(4), START + timedelta(days=2), STUDY, PATIENT)
    query = JudgedQuery(
        query_id=UUID(int=50),
        study_id=STUDY,
        patient_id=PATIENT,
        anchor_meal_id=UUID(int=51),
        input_cutoff=START + timedelta(days=3),
        foods=episodes[0].foods,
        nutrients=episodes[0].nutrients,
        judgments={e.id: 1 if i == 0 else 0 for i, e in enumerate(episodes)},
    )
    return Benchmark(
        dataset_version="test-v1",
        data_kind="synthetic",
        judgment_method="synthetic-food-overlap",
        protocol_version="test-v1",
        episodes=tuple(episodes),
        queries=(query,),
        k=3,
    )


def test_bootstrap_patient_weighting_and_reproducibility() -> None:
    # Three correlated queries for A must not outweigh B's single query.
    result = clustered_interval([1, 1, 1, 0], ["a", "a", "a", "b"])
    assert result["patient_macro_mean"] == 0.5
    assert result["patients"] == 2
    assert result["ci95"] == [0, 1]
    assert result == clustered_interval([1, 1, 1, 0], ["a", "a", "a", "b"])
    assert clustered_interval([0.2, 0.8], ["a", "a"])["ci95"] is None
    with pytest.raises(ValueError):
        clustered_interval([], [])


def test_evaluation_uses_supplied_labels_not_food_derived_relevance() -> None:
    benchmark = fixture()
    changed = benchmark.queries[0].model_copy(
        update={"judgments": {e.id: 1 if i == 2 else 0 for i, e in enumerate(benchmark.episodes)}}
    )
    first = evaluate_benchmark(benchmark)
    second = evaluate_benchmark(benchmark.model_copy(update={"queries": (changed,)}))
    assert first["input_sha256"] != second["input_sha256"]
    assert first["profiles"] != second["profiles"]
    assert first["queries_without_relevant_history"] == 0


@pytest.mark.parametrize("change", ["foreign", "late", "future", "anchor"])
def test_offline_scope_time_and_anchor_exclusion(change: str) -> None:
    benchmark = fixture()
    query = benchmark.queries[0]
    original = benchmark.episodes[0]
    variations: dict[str, dict[str, object]] = {
        "foreign": {"patient_id": UUID(int=999)},
        "late": {"available_at": query.input_cutoff + timedelta(seconds=1)},
        "future": {"end_at": query.input_cutoff + timedelta(seconds=1)},
        "anchor": {"anchor_id": query.anchor_meal_id},
    }
    poisoned = original.model_copy(update=variations[change])
    assert original.id not in {e.id for e in eligible((poisoned,), query)}


@pytest.mark.parametrize("change", ["missing", "extra", "duplicate", "research"])
def test_invalid_benchmark_refused(change: str) -> None:
    data = fixture().model_dump(mode="json")
    if change == "missing":
        data["queries"][0]["judgments"] = {}
    elif change == "extra":
        data["queries"][0]["judgments"][str(UUID(int=999))] = 1
    elif change == "duplicate":
        data["episodes"].append(data["episodes"][0])
    else:
        data["data_kind"] = "permitted-research"
    with pytest.raises(ValidationError):
        Benchmark.model_validate(data)


def test_unanswerable_cases_reported_without_manufactured_confidence() -> None:
    benchmark = fixture()
    query = benchmark.queries[0].model_copy(
        update={"judgments": {e.id: 0 for e in benchmark.episodes}}
    )
    report = evaluate_benchmark(benchmark.model_copy(update={"queries": (query,)}))
    assert report["queries_without_relevant_history"] == 1
    assert '"ci95": null' in __import__("json").dumps(report)
