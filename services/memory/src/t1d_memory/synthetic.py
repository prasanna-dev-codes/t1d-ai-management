"""Authored deterministic fixtures. All values are fictional, not research data."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from t1d_memory.contracts import Event

STUDY = UUID(int=101)
PATIENT = UUID(int=102)
START = datetime(2020, 1, 1, tzinfo=UTC)


def meal(number: int, food: str = "food.idli", carbs: str = "30") -> Event:
    nutrients = {"carbohydrate_g": carbs, "protein_g": "5", "fat_g": "2", "energy_kcal": "158"}
    when = START + timedelta(hours=4 * number)
    return Event(
        id=UUID(int=1000 + number),
        study_id=STUDY,
        patient_id=PATIENT,
        kind="meal",
        event_time=when,
        available_at=when,
        quality="accepted",
        revision=1,
        source_chain=f"synthetic-meal-{number}",
        data={
            "status": "confirmed",
            "components": [
                {
                    "status": "confirmed",
                    "food_reference_id": food,
                    "food_label": food,
                    "portion_value": "100",
                    "portion_unit": "g",
                }
            ],
            "nutrition_records": [{"scope": "meal_total", **nutrients}],
        },
    )


def cohort(count: int = 12) -> list[Event]:
    events = []
    labels = ["food.idli", "food.chapati", "food.dal", "food.samosa"]
    for number in range(count):
        anchor = meal(number, labels[number % len(labels)], str(25 + number % 9))
        events.append(anchor)
        for sample in range(25):
            when = anchor.event_time + timedelta(minutes=sample * 5)
            events.append(
                Event(
                    id=UUID(int=10000 + number * 100 + sample),
                    study_id=STUDY,
                    patient_id=PATIENT,
                    kind="cgm",
                    event_time=when,
                    available_at=when + timedelta(seconds=1),
                    quality="accepted",
                    revision=1,
                    source_chain=f"synthetic-cgm-{number}-{sample}",
                    data={
                        "glucose_value": str(100 + sample),
                        "glucose_unit": "mg/dL",
                        "sensor_status": "valid",
                    },
                )
            )
    return events
