"""Deterministic validation and synthetic-data safety regressions, no database needed."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError
from t1d_api.data.datasets import ImportManifest, pseudonymize
from t1d_api.data.schemas import ActivityInput, CGMInput, InsulinInput, MealInput, glucose
from t1d_api.data.service import digest, valid_times
from t1d_api.data.synthetic import generate


def reading() -> dict[str, object]:
    return dict(generate()["readings"][0])


@pytest.mark.parametrize(
    "changes",
    [
        {"glucose_unit": "unknown"},
        {"glucose_value": "NaN"},
        {"glucose_value": "Infinity"},
        {"glucose_value": "-1"},
        {"glucose_value": "0"},
        {"glucose_value": None},
        {"event_time": "2020-01-01T00:00:00"},
        {"event_time": 1577836800},
        {"event_time": "1577836800"},
        {"revision": 2},
        {"unapproved_field": "secret"},
        {"provenance": {}},
        {"glucose_value": "1.1234567890123"},
    ],
)
def test_invalid_input_rejected(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        CGMInput.model_validate({**reading(), **changes})


def test_conversion_preserves_exact_forward_value_and_discloses_inverse_rounding() -> None:
    original = Decimal("110.123456789012")
    normalized = glucose(original, "mg/dL", "mmol/L")
    assert normalized.value == original * Decimal(".0555") and not normalized.rounded
    reverse = glucose(Decimal("1"), "mmol/L", "mg/dL")
    assert reverse.rounded and reverse.precision_digits == 64
    assert glucose(original, "mg/dL", "mg/dL").value == original
    with pytest.raises(ValueError):
        glucose(original, "unknown", "mg/dL")


def test_temporal_validation_and_digest_equivalence() -> None:
    a = CGMInput.model_validate(reading())
    valid_times(a, datetime.now(UTC))
    assert digest({"a": Decimal("110.0")}) == digest({"a": Decimal("110")})
    assert digest({"a": datetime(2020, 1, 1, tzinfo=UTC)}) == digest(
        {
            "a": datetime(
                2020,
                1,
                1,
                5,
                30,
                tzinfo=__import__("datetime").timezone(timedelta(hours=5, minutes=30)),
            )
        }
    )
    from t1d_api.data.errors import DataError

    with pytest.raises(DataError):
        valid_times(a, datetime(2019, 1, 1, tzinfo=UTC))


def test_all_synthetic_fixtures_are_reproducible_and_labelled() -> None:
    value = generate(42)
    assert value == generate(42) and value != generate(43)
    assert value["synthetic"] is True
    assert all(p["research_subject_ref"].startswith("synthetic-") for p in value["patients"])
    for item in value["readings"]:
        CGMInput.model_validate(item)
    for item in value["meals"]:
        MealInput.model_validate(item)
    for item in value["insulin_events"]:
        InsulinInput.model_validate(item)
    for item in value["activity_events"]:
        ActivityInput.model_validate(item)
    assert value["readings"][1]["glucose_value"] is None
    assert value["duplicates"][0] == value["readings"][0]


def test_model_cannot_self_confirm_meal_and_unknown_activity_is_not_zero() -> None:
    meal = generate()["meals"][0]
    meal["provenance"]["source_type"] = "model"
    with pytest.raises(ValidationError):
        MealInput.model_validate(meal)
    activity = generate()["activity_events"][0]
    activity["intensity_value"] = "0"
    with pytest.raises(ValidationError):
        ActivityInput.model_validate(activity)


def test_dataset_import_fails_without_verified_access_and_uses_keyed_ids() -> None:
    manifest = ImportManifest(
        dataset_id="unverified",
        version="1",
        source_ref="pending",
        license_reference="verification-required",
        schema_mapping_version="1",
        unit_mapping_version="1",
        timezone_mapping_version="1",
        pseudonymization_namespace="study-a",
        split_strategy="patient-disjoint",
        limitations=["No access verified"],
    )
    with pytest.raises(ValueError):
        manifest.require_acquisition_authority()
    key = b"synthetic-linkage-key-not-a-credential" * 2
    assert pseudonymize("synthetic-subject", "a", key) == pseudonymize(
        "synthetic-subject", "a", key
    )
    assert pseudonymize("synthetic-subject", "a", key) != pseudonymize(
        "synthetic-subject", "b", key
    )
    with pytest.raises(ValueError):
        pseudonymize("x", "a", b"short")


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://wrong:synthetic-private-marker@127.0.0.1/t1d_phase02",
        "postgresql+psycopg://t1d_runtime:synthetic-private-marker@external.invalid/t1d_phase02",
        "postgresql+psycopg://t1d_runtime:synthetic-private-marker@127.0.0.1/phase01",
        "postgresql://t1d_runtime:synthetic-private-marker@127.0.0.1/t1d_phase02",
        "postgresql+psycopg://t1d_runtime@127.0.0.1/t1d_phase02",
    ],
)
def test_runtime_configuration_rejects_unsafe_urls_without_disclosure(url: str) -> None:
    from t1d_api.config import Settings

    with pytest.raises(ValidationError) as error:
        Settings.model_validate({"database_url": url})
    assert "synthetic-private-marker" not in str(error.value)
    assert url not in str(error.value)


def test_dataset_validation_report_counts_and_safe_issue_fields() -> None:
    from t1d_api.data.datasets import AdapterValidationReport

    base = {
        "dataset_id": "synthetic-markers",
        "version": "1",
        "records_seen": 2,
        "accepted": 1,
        "rejected": 1,
        "quarantined": 0,
        "issues": [{"record_index": 1, "code": "INVALID_UNIT"}],
    }
    assert AdapterValidationReport.model_validate(base).records_seen == 2
    with pytest.raises(ValidationError):
        AdapterValidationReport.model_validate({**base, "accepted": 2})
    with pytest.raises(ValidationError):
        AdapterValidationReport.model_validate(
            {
                **base,
                "issues": [{"record_index": 1, "code": "INVALID_UNIT", "payload": "forbidden"}],
            }
        )
