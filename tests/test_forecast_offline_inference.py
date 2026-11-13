"""Inference must work with only observed history and preserve causal features."""

import hashlib
from dataclasses import replace
from datetime import datetime, timedelta

import numpy as np
import pytest
from t1d_forecasting.datasets import OfflineEvent, SourceData
from t1d_forecasting.offline_inference import observed_features
from t1d_forecasting.windows import FEATURE_VERSION, make_windows


def observations(count: int) -> tuple[OfflineEvent, ...]:
    return tuple(
        OfflineEvent(
            "ohio",
            "fictional",
            "training",
            "glucose",
            datetime(2020, 1, 1) + timedelta(minutes=5 * i),
            "local",
            100.0 + i,
            "mg/dL",
            "fictional-source",
            i,
        )
        for i in range(count)
    )


def test_inference_needs_no_future_targets_and_matches_training_transform() -> None:
    events = observations(40)
    training, _ = make_windows(
        (SourceData(events, 0, "fictional-source"),), allow_event_time_replay=True
    )
    history = events[:12]
    x, lineage = observed_features(
        (SourceData(history, 0, "fictional-source"),), "ohio", "fictional", True
    )
    assert x[0] == pytest.approx(training[0].features)
    assert lineage["timezone"] == "unknown"
    assert np.isfinite(x).all()
    expected = hashlib.sha256(
        repr(
            (
                [(e.source_sha256, e.source_row) for e in history],
                [float(v) for v in x[0]],
                FEATURE_VERSION,
                True,
            )
        ).encode()
    ).hexdigest()
    assert training[0].input_ref == expected


def test_foreign_context_is_not_consumed() -> None:
    events = observations(12)
    foreign = replace(events[-1], dataset="azt1d", kind="carbohydrate", value=1000.0)
    a, _ = observed_features((SourceData(events, 0, "source"),), "ohio", "fictional", True)
    b, _ = observed_features(
        (SourceData(events + (foreign,), 0, "source"),), "ohio", "fictional", True
    )
    np.testing.assert_array_equal(a, b)


def test_gaps_conflicts_and_short_history_fail_closed() -> None:
    events = observations(12)
    for changed in (
        events[:11],
        events + (replace(events[-1], value=999.0),),
        events[:5] + events[6:],
    ):
        with pytest.raises(ValueError):
            observed_features((SourceData(changed, 0, "source"),), "ohio", "fictional", True)
