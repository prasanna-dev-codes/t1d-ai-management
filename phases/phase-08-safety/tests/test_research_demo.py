"""Cross-tier synthetic display and abstention regression tests."""

from dataclasses import replace
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from research_demo import AuditEntry, Fixture, Scenario, fixture, paired_comparison, retrieve, run
from t1d_forecasting.contracts import HORIZONS
from t1d_memory.contracts import Event, RetrievalResult


def test_confirmed_meal_retrieval_forecast_and_personalization() -> None:
    data = fixture("warm")
    assert data.meal.revision == 2
    log: list[AuditEntry] = []
    result = run(data, retrieve, log.append)
    assert result.audit.outcome == "eligible"
    assert len(result.evidence_refs) == 5
    assert result.personalization == "warm"
    assert list(result.forecasts) == ["phase06", "phase07", "phase07_with_memory"]
    assert result.forecasts["phase06"] != result.forecasts["phase07"]
    assert result.forecasts["phase07"] != result.forecasts["phase07_with_memory"]
    for points in result.forecasts.values():
        assert tuple(point.horizon_minutes for point in points) == HORIZONS
        assert all(
            point.lower_mg_dl <= point.glucose_mg_dl <= point.upper_mg_dl for point in points
        )
    assert result.audit.snapshot_sha256 is not None
    assert log == [result.audit]
    assert result.payload()["review_required"] is True


def test_cold_history_is_an_explicit_base_model_fallback() -> None:
    result = run(fixture("cold"), retrieve, lambda entry: None)
    assert result.personalization == "cold"
    assert result.evidence_refs == ()
    assert result.forecasts["phase06"] == result.forecasts["phase07"]
    assert result.forecasts["phase06"] == result.forecasts["phase07_with_memory"]


def test_paired_comparison_scores_all_three_branches_on_the_same_cases() -> None:
    result = paired_comparison()
    assert result["cases"] == result["scored"] == 8
    errors = result["mae_mg_dl"]
    assert isinstance(errors, dict)
    assert set(errors) == {"phase06", "phase07", "phase07_with_memory"}
    assert all(len(values) == 4 for values in errors.values())


@pytest.mark.parametrize(
    ("scenario", "reason"),
    [
        ("stale", "STALE_CGM"),
        ("unconfirmed", "MEAL_UNCONFIRMED_OR_UNAVAILABLE"),
        ("memory-unavailable", "MEMORY_UNAVAILABLE"),
    ],
)
def test_unusable_inputs_publish_no_forecast(scenario: Scenario, reason: str) -> None:
    log: list[AuditEntry] = []
    result = run(
        fixture(scenario), None if scenario == "memory-unavailable" else retrieve, log.append
    )
    assert result.audit.outcome == reason
    assert result.payload()["data"] is None
    assert result.evidence_refs == ()
    assert log == [result.audit]


def test_retry_rechecks_audit_and_retrieval() -> None:
    data = fixture("warm")
    first = run(data, retrieve, lambda entry: None)

    def unavailable(entry: AuditEntry) -> None:
        raise OSError("Test store unavailable")

    failed = run(data, retrieve, unavailable)
    assert failed.payload()["data"] is None and failed.audit.outcome == "AUDIT_UNAVAILABLE"
    unavailable_memory = run(data, None, lambda entry: None)
    assert unavailable_memory.payload()["data"] is None
    recovered = run(data, retrieve, lambda entry: None)
    assert recovered.forecasts == first.forecasts
    assert (
        len(
            {
                result.audit.evaluation_id
                for result in (
                    first,
                    failed,
                    unavailable_memory,
                    recovered,
                )
            }
        )
        == 4
    )


@pytest.mark.parametrize("change", ("future", "foreign", "altered"))
def test_forged_retrieval_never_reaches_forecasting(change: str) -> None:
    data = fixture("warm")

    def corrupt(inputs: Fixture, anchor: Event) -> RetrievalResult:
        result = retrieve(inputs, anchor)
        item = result.episodes[0]
        if change == "future":
            item = item.model_copy(update={"available_at": inputs.cutoff + timedelta(seconds=1)})
        elif change == "foreign":
            item = item.model_copy(update={"episode_id": uuid4()})
        else:
            item = item.model_copy(
                update={"response": item.response.model_copy(update={"last": 999})}
            )
        return result.model_copy(update={"episodes": [item]})

    result = run(data, corrupt, lambda entry: None)
    assert result.audit.outcome == "MEMORY_EVIDENCE_INVALID"
    assert result.payload()["data"] is None


def test_late_or_foreign_observations_do_not_change_a_past_forecast() -> None:
    data = fixture("warm")
    original = run(data, retrieve, lambda entry: None)
    template = next(event for event in data.events if event.kind == "cgm")
    foreign = template.model_copy(
        update={"patient_id": UUID(int=999), "id": uuid4(), "source_chain": "foreign"}
    )
    late = template.model_copy(
        update={
            "id": uuid4(),
            "revision": 2,
            "available_at": data.cutoff + timedelta(seconds=1),
            "data": template.data | {"glucose_value": 999},
        }
    )
    altered = replace(data, events=data.events + (foreign, late))
    result = run(altered, retrieve, lambda entry: None)
    assert result.forecasts == original.forecasts
    assert result.audit.snapshot_sha256 == original.audit.snapshot_sha256
