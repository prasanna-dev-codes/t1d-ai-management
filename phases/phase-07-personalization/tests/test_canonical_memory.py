"""Feed production Phase 05 retrieval responses into the Phase 07 consumer."""

from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import cast
from uuid import UUID, uuid4

import pytest
from canonical_memory import summarize
from t1d_api import memory_service
from t1d_api.auth import Principal
from t1d_api.contracts import Role
from t1d_api.db.session import Database, Scope
from t1d_memory.contracts import ProfileName, RetrievalRequest, RetrievalResult
from t1d_memory.episodes import build_episodes, known_events
from t1d_memory.graph import GraphIndex
from t1d_memory.ranking import cosine, embed
from t1d_memory.synthetic import PATIENT, STUDY, cohort, meal


@pytest.mark.parametrize("profile", ("structured-v1", "vector-v1", "hybrid-v1"))
def test_confirmed_meal_retrieval_feeds_phase07_features(
    profile: ProfileName, monkeypatch: pytest.MonkeyPatch
) -> None:
    anchor = meal(8, carbs="30")
    cutoff = anchor.event_time
    events = cohort(9)
    events = [anchor if item.id == anchor.id else item for item in events]
    foreign = meal(7).model_copy(update={"patient_id": UUID(int=999), "id": uuid4()})
    events.append(foreign)
    episodes, _ = build_episodes(events, cutoff, STUDY, PATIENT)
    checks: list[Scope] = []
    audits: list[str] = []
    monkeypatch.setattr(
        memory_service, "authorize", lambda session, scope, write: checks.append(scope)
    )
    monkeypatch.setattr(memory_service, "audit", lambda *args, **kwargs: audits.append(args[2]))
    monkeypatch.setattr(
        memory_service,
        "canonical_events",
        lambda session, scope, at: known_events(events, at, scope.study_id, scope.patient_id),
    )
    monkeypatch.setattr(
        memory_service, "load_episodes", lambda session, scope, at: (episodes, cutoff)
    )
    monkeypatch.setattr(
        memory_service,
        "vector_scores",
        lambda session, scope, pool, foods, at: {
            str(item.id): cosine(embed(item.foods), embed(foods)) for item in pool
        },
    )
    graph = cast(
        GraphIndex,
        SimpleNamespace(
            similarities=lambda study, patient, ids, foods, at, watermark: {
                str(item.id): len(set(item.foods) & set(foods)) / len(set(item.foods) | set(foods))
                for item in episodes
                if str(item.id) in ids
            }
        ),
    )
    db = cast(
        Database,
        SimpleNamespace(
            check=lambda: None, sessions=SimpleNamespace(begin=lambda: nullcontext(object()))
        ),
    )
    principal = Principal(
        subject_id=uuid4(),
        roles=frozenset({Role.RESEARCHER}),
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    scope = Scope(principal.subject_id, STUDY, PATIENT)
    result = memory_service.MemoryService(db, graph).retrieve(
        scope,
        principal,
        RetrievalRequest(
            input_cutoff=cutoff, anchor_meal_id=anchor.id, retrieval_profile_version=profile
        ),
        uuid4(),
    )
    roundtrip = RetrievalResult.model_validate_json(result.model_dump_json())
    features = summarize(roundtrip, cutoff, anchor.id, anchor.event_time)
    assert features.evidence_count == 5
    assert features.mean_observed_change_mg_dl == pytest.approx(24)
    assert checks == [scope, scope]
    assert audits == ["memory_retrieval"]
    assert all(item.anchor_meal_id != foreign.id for item in roundtrip.episodes)
    late = roundtrip.episodes[0].model_copy(update={"available_at": cutoff + timedelta(seconds=1)})
    with pytest.raises(ValueError, match="unqualified"):
        summarize(
            roundtrip.model_copy(update={"episodes": [late]}), cutoff, anchor.id, anchor.event_time
        )
