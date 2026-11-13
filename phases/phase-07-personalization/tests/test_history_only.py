"""History-only inference, immutable model recipes, and independent source normalization."""

from datetime import timedelta
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import pytest
from adaptation import WARMUP, ForecastQuery, replay
from artifact import InferenceArtifact, write_artifact
from personal_intervals import PersonalIntervals
from test_adaptation import START, row
from uom import read_uom


def test_query_without_target_matches_the_same_replay_cutoff() -> None:
    history = [row(hour) for hour in range(24)]
    current = row(168, glucose=900)
    baseline = np.full((25, 4), 100.0)
    query = ForecastQuery(current.scope, current.cutoff, current.features)
    live = replay(history, baseline, START + WARMUP, [True] * 24, query=query)
    labelled = replay(history + [current], baseline, START + WARMUP, [True] * 25)
    for profile in live.predictions:
        np.testing.assert_array_equal(
            live.predictions[profile][-1], labelled.predictions[profile][-1]
        )
    cold = replay([], baseline[:1], current.cutoff + WARMUP, [], query=query)
    np.testing.assert_array_equal(cold.predictions["context-offset"], baseline[:1])
    assert not cold.rolling_support[0]


def test_profile_must_match_frozen_models_and_horizon_recipe(tmp_path: Path) -> None:
    path = tmp_path / "profile.json"
    recipe = ["v4", "v4", "v4-analogue-blend", "v4-analogue-blend"]
    hashes = {"v4": "a" * 64, "analogue-huber": "b" * 64}
    local = PersonalIntervals(np.full(4, 25.0), np.ones(4), 3)
    write_artifact(path, ["context-offset"] * 4, recipe, hashes, local)
    artifact, identity = InferenceArtifact.read(path)
    assert len(identity) == 64
    artifact.verify_models(hashes, recipe)
    with pytest.raises(ValueError, match="does not match"):
        artifact.verify_models(hashes, list(reversed(recipe)))
    with pytest.raises(ValueError, match="does not match"):
        artifact.verify_models({"v4": "c" * 64}, recipe)


def test_uom_day_first_clock_units_and_ambiguous_context(tmp_path: Path) -> None:
    path = tmp_path / "source.zip"
    with ZipFile(path, "w") as archive:
        archive.writestr(
            "release/Glucose Data/UoMGlucose0001.csv",
            "bg_ts,value\n13/01/2024 12:00,5.55\n13/01/2024 12:05,6.105\n",
        )
        archive.writestr(
            "release/Insulin Data/Bolus Data/UoMBolus0001.csv",
            "bolus_ts,bolus_dose\n13/01/2024 12:00,2\n13/01/2024 12:00,1\n",
        )
        archive.writestr(
            "release/Nutrition Data/UoMNutrition0001.csv",
            "meal_ts,carbs_g\n13/01/2024 12:00,30\n",
        )
    sources, counts = read_uom(path)
    records = sources[0].events
    assert records[0].time.day == 13 and records[0].time.tzinfo is None
    assert records[1].time - records[0].time == timedelta(minutes=5)
    assert [record.kind for record in records] == ["glucose", "glucose", "carbohydrate"]
    assert records[0].value == pytest.approx(100.0)
    assert counts["ambiguous_context_rows_excluded"] == 2
