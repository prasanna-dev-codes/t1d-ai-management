"""Offline, independently judged retrieval evaluation; no identity or clinical claims."""

import random
import statistics
from collections import defaultdict
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from t1d_memory.contracts import Contract, Episode, ExplicitTime, Nutrients, ProfileName, Version
from t1d_memory.episodes import canonical_hash
from t1d_memory.evaluation import metrics
from t1d_memory.ranking import cosine, embed, rank


class JudgedQuery(Contract):
    query_id: UUID
    study_id: UUID
    patient_id: UUID
    anchor_meal_id: UUID
    input_cutoff: ExplicitTime
    foods: tuple[str, ...] = Field(min_length=1, max_length=100)
    nutrients: Nutrients
    # Every eligible candidate must be judged, including explicit nonrelevance.
    judgments: dict[UUID, Literal[0, 1]] = Field(max_length=5000)


class Benchmark(Contract):
    dataset_version: Version
    data_kind: Literal["synthetic", "permitted-research"]
    judgment_method: Literal["synthetic-food-overlap", "independent-review"]
    protocol_version: Version
    episodes: tuple[Episode, ...] = Field(min_length=1, max_length=5000)
    queries: tuple[JudgedQuery, ...] = Field(min_length=1, max_length=1000)
    k: int = Field(default=5, ge=1, le=20)

    @model_validator(mode="after")
    def identities(self) -> "Benchmark":
        if len({e.id for e in self.episodes}) != len(self.episodes):
            raise ValueError("Duplicate episode identity")
        if len({q.query_id for q in self.queries}) != len(self.queries):
            raise ValueError("Duplicate query identity")
        if self.data_kind != "synthetic" and self.judgment_method != "independent-review":
            raise ValueError("Research evaluation requires independently supplied judgments")
        for query in self.queries:
            if set(query.judgments) != {e.id for e in eligible(self.episodes, query)}:
                raise ValueError("Judgments must cover exactly the eligible candidate pool")
        return self


def eligible(episodes: tuple[Episode, ...], query: JudgedQuery) -> list[Episode]:
    """Point-in-time replay filters, not a replacement for live canonical authorization."""
    return [
        e
        for e in episodes
        if e.study_id == query.study_id
        and e.patient_id == query.patient_id
        and e.anchor_id != query.anchor_meal_id
        and e.available_at <= query.input_cutoff
        and e.end_at <= query.input_cutoff
        and all(s.available_at <= query.input_cutoff for s in e.sources)
    ]


def clustered_interval(
    values: list[float], clusters: list[str], *, seed: int = 2026, repeats: int = 1000
) -> dict[str, object]:
    """Equal-patient macro mean and patient-cluster bootstrap, not query independence."""
    if not values or len(values) != len(clusters) or repeats < 100:
        raise ValueError("Matched nonempty observations and at least 100 resamples required")
    grouped: dict[str, list[float]] = defaultdict(list)
    for cluster, value in zip(clusters, values, strict=True):
        grouped[cluster].append(value)
    means = [statistics.mean(v) for _, v in sorted(grouped.items())]
    result: dict[str, object] = {
        "patient_macro_mean": statistics.mean(means),
        "patients": len(means),
        "ci95": None,
    }
    if len(means) > 1:
        rng = random.Random(seed)
        draws = sorted(statistics.mean(rng.choices(means, k=len(means))) for _ in range(repeats))
        result["ci95"] = [draws[int(0.025 * (repeats - 1))], draws[int(0.975 * (repeats - 1))]]
    return result


def evaluate_benchmark(benchmark: Benchmark) -> dict[str, object]:
    profiles: list[ProfileName] = ["structured-v1", "vector-v1", "hybrid-v1"]
    per_profile: dict[str, list[dict[str, float]]] = {p: [] for p in profiles}
    clusters = [f"{q.study_id}:{q.patient_id}" for q in benchmark.queries]
    # Feature reuse is local to this immutable offline benchmark, never a live cache.
    vectors = {e.id: embed(e.foods) for e in benchmark.episodes}
    foods = {e.id: set(e.foods) for e in benchmark.episodes}
    no_relevant = 0
    empty_history = 0
    for query in benchmark.queries:
        pool = eligible(benchmark.episodes, query)
        relevant = {str(identity) for identity, label in query.judgments.items() if label}
        no_relevant += not relevant
        empty_history += not pool
        query_vector, query_foods = embed(query.foods), set(query.foods)
        similarities = {str(e.id): cosine(vectors[e.id], query_vector) for e in pool}
        graph = {
            str(e.id): len(foods[e.id] & query_foods) / len(foods[e.id] | query_foods) for e in pool
        }
        for profile in profiles:
            result = rank(
                pool, query.foods, query.nutrients, profile, benchmark.k, similarities, graph
            )
            per_profile[profile].append(
                metrics([str(e.episode_id) for e in result], relevant, benchmark.k)
            )
    results: dict[str, object] = {}
    comparisons: dict[str, object] = {}
    for profile in profiles:
        results[profile] = {
            name: clustered_interval([r[name] for r in per_profile[profile]], clusters)
            for name in per_profile[profile][0]
        }
        if profile != "structured-v1":
            comparisons[profile + "_minus_structured"] = {
                name: clustered_interval(
                    [
                        row[name] - baseline[name]
                        for row, baseline in zip(
                            per_profile[profile], per_profile["structured-v1"], strict=True
                        )
                    ],
                    clusters,
                )
                for name in per_profile[profile][0]
            }
    return {
        "benchmark_version": "patient-clustered-retrieval-v1",
        "input_sha256": canonical_hash(benchmark.model_dump(mode="json")),
        "dataset_version": benchmark.dataset_version,
        "protocol_version": benchmark.protocol_version,
        "data_kind": benchmark.data_kind,
        "judgment_method": benchmark.judgment_method,
        "queries": len(benchmark.queries),
        "k": benchmark.k,
        "queries_without_relevant_history": no_relevant,
        "queries_without_eligible_history": empty_history,
        "profiles": results,
        "paired_differences": comparisons,
        "limitations": [
            "Offline frozen manifests; live authorization/canonical rechecks tested separately",
            "Judgment independence, permissions and correctness require external review",
            "Confidence intervals resample patients; unavailable with fewer than two patients",
            "Small cohorts have unreliable uncertainty estimates even with intervals",
            "Profiles share queries; paired differences do not imply clinical benefit",
            "Precision uses requested k even when fewer candidates exist",
            "No-relevant-history queries score zero; reported explicitly, not omitted",
            "No clinical validation or forecasting improvement established",
        ],
    }
