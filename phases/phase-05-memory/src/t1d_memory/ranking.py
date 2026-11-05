"""Inspectable experimental profiles; similarity is not clinical confidence."""

import hashlib
import math

from t1d_memory.contracts import Episode, Evidence, Nutrients, ProfileName

EMBEDDING_VERSION = "food-hash64-v1"
DIMENSIONS = 64


def embed(foods: tuple[str, ...]) -> tuple[float, ...]:
    """Local deterministic food-ID feature hashing, not pretrained semantics.

    No learned weights, external data, network call, patient ID or outcome input.
    SHA-256 hash collisions are possible and disclosed; graph exact-match evidence
    remains separate. Frozen dimension/normalization is part of the version.
    """
    vector = [0.0] * DIMENSIONS
    for food in sorted(set(foods)):
        index = int.from_bytes(hashlib.sha256(food.encode()).digest()[:8], "big") % DIMENSIONS
        vector[index] += 1
    norm = math.sqrt(sum(v * v for v in vector))
    if norm == 0:
        raise ValueError("At least one food concept required")
    return tuple(v / norm for v in vector)


def cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if len(left) != DIMENSIONS or len(right) != DIMENSIONS:
        raise ValueError("Embedding dimension mismatch")
    if not all(math.isfinite(v) for v in (*left, *right)):
        raise ValueError("Finite vectors required")
    denominator = math.sqrt(sum(v * v for v in left) * sum(v * v for v in right))
    if denominator == 0:
        raise ValueError("Nonzero vectors required")
    return min(1.0, max(0.0, sum(a * b for a, b in zip(left, right, strict=True)) / denominator))


def nutrient_similarity(left: Nutrients, right: Nutrients) -> float:
    # Dimensionless relative differences; each macronutrient has equal influence.
    distances = []
    for name in ("carbohydrate_g", "protein_g", "fat_g"):
        a, b = float(getattr(left, name)), float(getattr(right, name))
        distances.append(abs(a - b) / max(1.0, a, b))
    return 1.0 - sum(distances) / 3


def rank(
    episodes: list[Episode],
    foods: tuple[str, ...],
    nutrients: Nutrients,
    profile: ProfileName,
    limit: int,
    vector_scores: dict[str, float] | None = None,
    graph_scores: dict[str, float] | None = None,
) -> list[Evidence]:
    if profile not in {"structured-v1", "vector-v1", "hybrid-v1"} or not 1 <= limit <= 20:
        raise ValueError("Unsupported bounded retrieval profile")
    output = []
    for episode in episodes:
        nutrient = nutrient_similarity(nutrients, episode.nutrients)
        vector = None if profile == "structured-v1" else (vector_scores or {}).get(str(episode.id))
        graph = None if profile != "hybrid-v1" else (graph_scores or {}).get(str(episode.id), 0.0)
        if profile != "structured-v1" and vector is None:
            raise ValueError("Vector evidence unavailable; no silent fallback")
        if profile == "hybrid-v1" and (graph_scores is None or str(episode.id) not in graph_scores):
            raise ValueError("Graph evidence unavailable; no silent fallback")
        score = nutrient
        if profile == "vector-v1":
            score = 0.5 * nutrient + 0.5 * float(vector)  # type: ignore[arg-type]
        elif profile == "hybrid-v1":
            score = 0.5 * nutrient + 0.3 * float(vector) + 0.2 * float(graph)  # type: ignore[arg-type]
        reasons = ["CONFIRMED_MEAL", "SAME_PATIENT_STUDY", "KNOWN_BY_CUTOFF", "NUTRIENT_SIMILARITY"]
        if vector is not None:
            reasons.append("LOCAL_FOOD_VECTOR_SIMILARITY")
        if graph:
            reasons.append("EXACT_FOOD_GRAPH_OVERLAP")
        output.append(
            Evidence(
                episode_id=episode.id,
                anchor_meal_id=episode.anchor_id,
                source_revision_refs=[s.id for s in episode.sources],
                event_time=episode.start_at,
                available_at=episode.available_at,
                score=score,
                nutrient_similarity=nutrient,
                vector_similarity=vector,
                graph_similarity=graph,
                evidence_reasons=reasons,
                warnings=list(episode.warnings),
                response=episode.response,
            )
        )
    return sorted(output, key=lambda e: (-e.score, -e.event_time.timestamp(), e.episode_id.int))[
        :limit
    ]
