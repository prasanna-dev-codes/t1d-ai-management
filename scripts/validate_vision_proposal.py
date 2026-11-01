"""Validate the Phase 03 decision artifacts; does not acquire data or train a model."""

import json
import re
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def load(path: str) -> dict[str, Any]:
    value: Any = json.loads((ROOT / path).read_text())
    require(isinstance(value, dict), "Expected a JSON object")
    return dict(value)


def normalized(label: str) -> str:
    return re.sub(r"[\s_-]+", " ", label.strip().casefold())


def validate_taxonomy(taxonomy: dict[str, Any]) -> None:
    require(taxonomy["approval_status"] == "proposed", "Proposal approval state changed")
    require(taxonomy["trainable"] is False, "Unapproved taxonomy must not be trainable")
    categories = {item["id"]: item["parent_id"] for item in taxonomy["categories"]}
    require(len(categories) == len(taxonomy["categories"]), "Duplicate category ID")
    require(categories.get("category.food", "missing") is None, "Expected the food root")
    for identity in categories:
        seen: set[str] = set()
        current: str | None = identity
        while current is not None:
            require(current in categories, "Unknown taxonomy parent")
            require(current not in seen, "Taxonomy parent cycle")
            seen.add(current)
            current = categories[current]
        require("category.food" in seen, "Disconnected taxonomy category")
    classes: set[str] = set()
    labels: dict[str, str] = {}
    for item in taxonomy["classes"]:
        identity = item["id"]
        require(bool(re.fullmatch(r"food\.[a-z][a-z0-9_]*", identity)), "Invalid class ID")
        require(identity not in classes, "Duplicate class ID")
        require(item["parent_id"] in categories, "Unknown class parent")
        require(item["support_status"] == "not_empirically_validated", "Unverified support claim")
        classes.add(identity)
        for raw in [item["label"], *item["aliases"]]:
            key = normalized(raw)
            require(bool(key), "Empty taxonomy label")
            require(key not in labels or labels[key] == identity, "Ambiguous direct alias")
            labels[key] = identity
    for raw, targets in taxonomy["ambiguous_aliases"].items():
        require(normalized(raw) not in labels, "Ambiguous alias must not map directly")
        require(len(targets) >= 2, "Ambiguity requires distinct alternatives")
        require(len(set(targets)) == len(targets), "Duplicate ambiguity target")
        require(
            all(target in classes or target.startswith("unresolved_") for target in targets),
            "Unknown ambiguity target",
        )
    require(set(taxonomy["decision_states"]).isdisjoint(classes), "State used as food class")
    require(
        taxonomy["mapping_policy"]["nutrition_equivalence_asserted"] is False,
        "No nutritional equivalence is established",
    )


def main() -> None:
    taxonomy = load("services/vision/taxonomy/food-taxonomy.v0.1.0.proposed.json")
    matrix = load("docs/vision-dataset-assessment.json")
    plan = load("ml/experiments/vision/phase03-plan.proposed.json")
    validate_taxonomy(taxonomy)
    require(len(matrix["axes"]) == 9 and len(set(matrix["axes"])) == 9, "Expected nine axes")
    identities: set[str] = set()
    for dataset in matrix["datasets"]:
        require(dataset["id"] not in identities, "Duplicate dataset identity")
        identities.add(dataset["id"])
        require(set(dataset["comparison"]) == set(matrix["axes"]), "Incomplete dataset matrix")
        require(all(dataset["comparison"].values()), "Empty dataset assessment")
        require(
            not dataset["approved_for_acquisition"] and not dataset["approved_for_training"],
            "Dataset approval must be explicit and is still pending",
        )
    for flag in [
        "acquisition_authorized",
        "pretrained_weights_authorized",
        "training_authorized",
        "cloud_execution_authorized",
        "paid_services_authorized",
        "local_full_dataset_download_authorized",
    ]:
        require(plan[flag] is False, "Acquisition/training/cloud gate remains closed")
    require(plan["api_design_authorized"] is True, "User approved ephemeral API design")
    require(
        plan["pretrained_weights_conditionally_approved"] is True,
        "Conditional weights approval missing",
    )
    require(plan["primary_dataset_candidate"] is None, "Primary dataset awaits coverage audit")
    require(set(plan["indian_dataset_audit_candidates"]) <= identities, "Unknown audit candidate")
    require(plan["training"]["total_initial_hours_cap"] <= 12, "Training cap exceeded")
    fractions = plan["split"]["official_train_group_fractions"]
    require(set(fractions) == {"train", "validation", "calibration"}, "Split roles missing")
    require(all(Decimal(value) > 0 for value in fractions.values()), "Nonpositive split fraction")
    require(
        sum(Decimal(value) for value in fractions.values()) == Decimal(1), "Invalid split total"
    )
    require(plan["storage"]["strategy"].startswith("cloud-first"), "Cloud-first storage required")
    require(plan["storage"]["automatic_cleanup_authorized"] is False, "No cleanup authorized")
    print(
        f"PASS: {len(taxonomy['classes'])} proposed food concepts; "
        f"{len(matrix['datasets'])} datasets × 9 assessment axes; "
        "acquisition/training/cloud gates closed; ephemeral API approved"
    )


if __name__ == "__main__":
    main()
