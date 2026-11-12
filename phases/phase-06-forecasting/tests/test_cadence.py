"""Verify native and decimated research windows use measured, available inputs."""

from dataclasses import replace
from datetime import datetime, timedelta

from t1d_forecasting.cadence import CGM_COLUMNS, make_cadence_windows
from t1d_forecasting.datasets import OfflineEvent, SourceData

START = datetime(2020, 1, 1)


def readings(minutes: int, count: int) -> tuple[OfflineEvent, ...]:
    return tuple(
        OfflineEvent(
            "uom",
            "fictional",
            "unsplit",
            "glucose",
            START + timedelta(minutes=i * minutes),
            "",
            100.0 + minutes * i,
            "mg/dL",
            "fictional-source",
            i,
        )
        for i in range(count)
    )


def test_native_windows_match_decimated_observations_and_exclude_late_context() -> None:
    native = readings(15, 16)
    dense = readings(5, 46)
    cutoff = native[7].time
    meal = replace(
        native[7],
        kind="carbohydrate",
        value=40,
        unit="g",
        available_at=cutoff + timedelta(seconds=1),
    )
    sparse_rows, _ = make_cadence_windows((SourceData((*native, meal), 0, ""),), native=True)
    dense_rows, _ = make_cadence_windows((SourceData(dense, 0, ""),), native=False)
    assert len(sparse_rows) == len(dense_rows) == 1
    sparse, observed = sparse_rows[0], dense_rows[0]
    assert sparse.features == observed.features
    assert sparse.cutoff == cutoff
    assert sparse.targets == observed.targets == (235, 265, 295, 325)
    assert sparse.features[CGM_COLUMNS : CGM_COLUMNS + 2] == (0.0, 0.0)


def test_cadence_gate_excludes_five_minute_people_and_native_gaps() -> None:
    dense = readings(5, 46)
    native = readings(15, 16)
    windows, counts = make_cadence_windows((SourceData(dense, 0, ""),), native=True)
    assert not windows and counts["non_native_partitions_excluded"] == 1
    windows, counts = make_cadence_windows(
        (SourceData(native[:5] + native[6:], 0, ""),), native=True
    )
    assert not windows and counts["cadence_or_clock_breaks"] == 1
