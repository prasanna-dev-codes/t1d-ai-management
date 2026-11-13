"""Filter canonical episode snapshots before any experimental similarity ranking.

Inputs must be constructed by a trusted, authorized canonical-store adapter.
These checks do not authenticate a caller or replace consent, grants, RLS or audit.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


def _aware(value: datetime) -> None:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError("Timezone-aware datetime required")


@dataclass(frozen=True)
class Scope:
    study_id: UUID
    patient_id: UUID


@dataclass(frozen=True)
class SourceRevision:
    revision_id: UUID
    scope: Scope
    event_time: datetime
    available_at: datetime
    # Latest visible revision at the requested cutoff, not today's latest revision.
    latest_at_cutoff: bool
    usable: bool

    def __post_init__(self) -> None:
        _aware(self.event_time)
        _aware(self.available_at)
        if self.available_at < self.event_time:
            raise ValueError("Source availability precedes event")


@dataclass(frozen=True)
class EpisodeSnapshot:
    episode_id: UUID
    anchor_revision_id: UUID
    scope: Scope
    starts_at: datetime
    ends_at: datetime
    derived_at: datetime
    human_confirmed: bool
    withdrawn: bool
    sources: tuple[SourceRevision, ...]

    def __post_init__(self) -> None:
        for value in (self.starts_at, self.ends_at, self.derived_at):
            _aware(value)
        if self.ends_at < self.starts_at or self.derived_at < self.ends_at:
            raise ValueError("Episode time order invalid")
        if not isinstance(self.sources, tuple) or not self.sources:
            raise ValueError("Immutable nonempty source lineage required")
        ids = [source.revision_id for source in self.sources]
        if len(ids) != len(set(ids)) or self.anchor_revision_id not in ids:
            raise ValueError("Unique source lineage including anchor required")


@dataclass(frozen=True)
class RetrievalQuery:
    scope: Scope
    cutoff: datetime
    target_anchor_revision_id: UUID
    # Server-controlled time, supplied by the future integration adapter.
    evaluated_at: datetime

    def __post_init__(self) -> None:
        _aware(self.cutoff)
        _aware(self.evaluated_at)
        if self.cutoff > self.evaluated_at:
            raise ValueError("Future cutoff forbidden")


def eligible(query: RetrievalQuery, episode: EpisodeSnapshot) -> bool:
    """Return eligibility only; never return foreign IDs, counts or explanations.

    Confirmation timestamps, annotations, response samples and contextual events
    must all appear in sources. Episode duration is supplied, never guessed here.
    No graph/vector fallback, relevance score, dose or clinical threshold exists.
    """
    if (
        episode.scope != query.scope
        or episode.anchor_revision_id == query.target_anchor_revision_id
        or not episode.human_confirmed
        or episode.withdrawn
        or episode.ends_at > query.cutoff
        or episode.derived_at > query.cutoff
    ):
        return False
    return all(
        source.scope == query.scope
        and source.event_time <= query.cutoff
        and source.available_at <= query.cutoff
        and source.available_at <= episode.derived_at
        and source.latest_at_cutoff
        and source.usable
        for source in episode.sources
    )
