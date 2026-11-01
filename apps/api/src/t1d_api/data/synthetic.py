"""Deterministic engineering fixtures; no physiological realism or clinical evidence."""

import random
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import NAMESPACE_URL, uuid5


def generate(seed: int = 42, count: int = 12) -> dict[str, Any]:
    if not 3 <= count <= 100:
        raise ValueError("Synthetic fixture count must be between 3 and 100")
    rng = random.Random(seed)
    start = datetime(2020, 1, 1, tzinfo=UTC)

    def event(ref: str, index: int = 0) -> dict[str, Any]:
        when = start + timedelta(minutes=5 * index)
        return {
            "source_event_ref": ref,
            "event_time": when.isoformat(),
            "provenance": {
                "source_type": "synthetic",
                "source_ref": "synthetic:fixture",
                "source_version": "1",
                "recorded_at": (when + timedelta(hours=1)).isoformat(),
            },
        }

    readings = []
    for i in range(count):
        readings.append(
            {
                **event(f"synthetic-cgm-{i}", i),
                "glucose_value": None if i == 1 else str(rng.randint(1, 200)),
                "glucose_unit": "mg/dL",
                "device_ref": "synthetic-device",
                "sensor_status": "missing" if i == 1 else "valid",
            }
        )
    nutrition = {
        "carbohydrate_g": "12",
        "protein_g": "3",
        "fat_g": "2",
        "energy_kcal": "78",
        "reference_ref": "synthetic-food",
        "method_version": "synthetic-v1",
        "uncertainty_status": "unknown",
    }
    return {
        "synthetic": True,
        "seed": seed,
        "disclaimer": "Engineering fixtures only; no physiological realism, forecast accuracy or "
        "clinical evidence",
        "patients": [
            {
                "id": str(uuid5(NAMESPACE_URL, f"t1d-synthetic-{seed}-{i}")),
                "research_subject_ref": f"synthetic-{seed}-{i}",
            }
            for i in range(2)
        ],
        "readings": readings,
        "duplicates": [readings[0].copy()],
        "correction": {
            "corrects_source_event_ref": readings[0]["source_event_ref"],
            "requires_server_predecessor_id": True,
            "changed_glucose_value": "111",
        },
        "meals": [
            {
                **event("synthetic-meal"),
                "status": "confirmed",
                "nutrition": nutrition,
                "components": [
                    {
                        "food_label": "synthetic-food",
                        "portion_value": "80",
                        "portion_unit": "g",
                        "status": "confirmed",
                        "nutrition": nutrition,
                    }
                ],
            }
        ],
        "insulin_events": [
            {
                **event("synthetic-planned-history"),
                "event_kind": "planned",
                "amount_value": "1.5",
                "amount_unit": "U",
                "insulin_type_ref": "synthetic-marker",
            }
        ],
        "activity_events": [
            {
                **event("synthetic-activity"),
                "activity_type": "synthetic-motion",
                "start_at": start.isoformat(),
                "end_at": (start + timedelta(minutes=1)).isoformat(),
                "intensity_status": "unknown",
            }
        ],
    }
