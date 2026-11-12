"""Translate a trusted Phase 05 retrieval result into offline forecast evidence."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from t1d_memory.contracts import DEFINITION, RetrievalResult
from t1d_memory.episodes import definition_hash
from t1d_memory.ranking import EMBEDDING_VERSION


@dataclass(frozen=True)
class MemoryFeatures:
    evidence_count: int
    mean_observed_change_mg_dl: float | None
    episode_ids: tuple[UUID, ...]


def summarize(
    result: RetrievalResult, cutoff: datetime, anchor_id: UUID, anchor_time: datetime
) -> MemoryFeatures:
    """Summarize only earlier, completed meals in a service-authorized response."""
    expected_embedding = (
        None if result.retrieval_profile_version == "structured-v1" else EMBEDDING_VERSION
    )
    if (
        cutoff.utcoffset() is None
        or anchor_time.utcoffset() is None
        or anchor_time > cutoff
        or result.input_cutoff != cutoff
        or result.definition_version != DEFINITION.version
        or result.definition_hash != definition_hash(DEFINITION)
        or result.embedding_version != expected_embedding
        or len(result.episodes) > 20
        or len({item.episode_id for item in result.episodes}) != len(result.episodes)
        or (result.status == "evidence") != bool(result.episodes)
        or any(
            item.available_at > cutoff
            or item.available_at < item.event_time + timedelta(minutes=DEFINITION.response_minutes)
            or item.anchor_meal_id == anchor_id
            for item in result.episodes
        )
    ):
        raise ValueError("Incompatible or unqualified Phase 05 evidence")
    evidence = [
        item
        for item in result.episodes
        if item.event_time < anchor_time
        and "OVERLAPPING_MEAL" not in item.warnings
        and item.score > 0
    ]
    if not evidence:
        return MemoryFeatures(0, None, ())
    total = sum(item.score for item in evidence)
    change = sum(item.score * (item.response.last - item.response.first) for item in evidence)
    return MemoryFeatures(
        len(evidence), change / total, tuple(item.episode_id for item in evidence)
    )
