"""Proposal invariants only; these are not food-model validation results."""

import json
import runpy
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest

ROOT = Path(__file__).resolve().parents[1]
VALIDATE = cast(
    Callable[[dict[str, Any]], None],
    runpy.run_path(str(ROOT / "scripts/validate_vision_proposal.py"))["validate_taxonomy"],
)


def taxonomy() -> dict[str, Any]:
    value = json.loads(
        (ROOT / "services/vision/taxonomy/food-taxonomy.v0.1.0.proposed.json").read_text()
    )
    assert isinstance(value, dict)
    return value


def test_proposed_taxonomy_structure_is_valid_without_claiming_training() -> None:
    value = taxonomy()
    VALIDATE(value)
    assert value["trainable"] is False
    assert len(value["classes"]) == 18


@pytest.mark.parametrize(
    ("scenario", "reason"),
    [
        ("duplicate", "Duplicate class ID"),
        ("cycle", "Taxonomy parent cycle"),
        ("alias", "Ambiguous direct alias"),
        ("dangling", "Unknown class parent"),
        ("trainable", "Unapproved taxonomy"),
        ("unsupported_claim", "Unverified support claim"),
    ],
)
def test_rejects_identity_ambiguity_and_unearned_support(scenario: str, reason: str) -> None:
    value = taxonomy()
    if scenario == "duplicate":
        value["classes"][1]["id"] = value["classes"][0]["id"]
    elif scenario == "cycle":
        value["categories"][1]["parent_id"] = value["categories"][1]["id"]
    elif scenario == "alias":
        value["classes"][1]["aliases"].append("chapati")
    elif scenario == "dangling":
        value["classes"][0]["parent_id"] = "category.missing"
    elif scenario == "trainable":
        value["trainable"] = True
    else:
        value["classes"][0]["support_status"] = "validated"
    with pytest.raises(ValueError, match=reason):
        VALIDATE(value)
