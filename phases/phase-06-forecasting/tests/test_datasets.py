"""Offline parsing preserves clocks, missing context and source identity."""

import zipfile
from datetime import datetime
from pathlib import Path

import pytest
from t1d_forecasting.datasets import (
    OfflineEvent,
    elapsed_seconds,
    number,
    parse_source_time,
    read_azt1d,
    read_ohio,
    read_physiocgm,
)


def test_local_clocks_are_not_converted_to_machine_timezone() -> None:
    naive = parse_source_time("01-02-2020 10:00:00", "ohio")
    assert naive == datetime(2020, 2, 1, 10) and naive.tzinfo is None
    assert parse_source_time("2020-02-01 1:05:00", "physiocgm").hour == 1
    known = parse_source_time("2020-02-01T10:00:00+05:30", "azt1d")
    assert known.utcoffset() is not None


def test_elapsed_time_rejects_cross_participant_and_clock_mixing() -> None:
    from dataclasses import replace

    first = OfflineEvent(
        "ohio",
        "test",
        "training",
        "glucose",
        datetime(2020, 1, 1),
        "source",
        100.0,
        "mg/dL",
        "hash",
        1,
    )
    second = replace(first, time=datetime(2020, 1, 1, 0, 30))
    assert elapsed_seconds(first, second) == 1800
    assert not first.timezone_known and first.available_at is None
    with pytest.raises(ValueError, match="same dataset"):
        elapsed_seconds(first, replace(second, participant="other"))
    with pytest.raises(ValueError, match="Mixed"):
        elapsed_seconds(
            first, replace(second, time=parse_source_time("2020-01-01T00:30:00Z", "azt1d"))
        )


@pytest.mark.parametrize("value", ["NaN", "inf", "-1", "invalid"])
def test_invalid_measurements_refused(value: str) -> None:
    with pytest.raises(ValueError):
        number(value)
    assert number("") is None and number("0") == 0


def test_ohio_context_and_original_split_preserved(tmp_path: Path) -> None:
    path = tmp_path / "source.zip"
    raw = """<patient id="123"><glucose_level><event ts="01-01-2020 10:00:00" value="100"/>
    </glucose_level><meal><event ts="01-01-2020 09:30:00" carbs="30"/></meal>
    <bolus><event ts_begin="01-01-2020 09:30:00" ts_end="01-01-2020 09:30:00" dose="1"/>
    </bolus></patient>"""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("2018/train/123-ws-training.xml", raw)
    data = read_ohio(path)[0]
    assert {e.kind for e in data.events} == {"glucose", "carbohydrate", "bolus"}
    assert all(e.partition == "training" and e.available_at is None for e in data.events)
    assert len(data.source_sha256) == 64 and data.rejected_rows == 0


def test_ohio_untrusted_identity_and_xml_declaration_refused(tmp_path: Path) -> None:
    path = tmp_path / "source.zip"
    for raw in ('<patient id="999"/>', '<!DOCTYPE patient><patient id="123"/>'):
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("123-ws-training.xml", raw)
        with pytest.raises(ValueError):
            read_ohio(path)


def test_physiocgm_does_not_invent_missing_context(tmp_path: Path) -> None:
    path = tmp_path / "fictional.csv"
    path.write_text(
        "Timestamp (YYYY-MM-DDThh:mm:ss),Glucose Value (mg/dL),Event Type\n"
        "2020-01-01 1:00:00,100,EGV\n,120,EGV\n2020-01-01 1:05:00,,EGV\n"
        "2020-01-01 1:10:00,120,Calibration\n",
        encoding="utf-8",
    )
    data = read_physiocgm(path)
    assert len(data.events) == 1 and data.rejected_rows == 1
    assert data.events[0].kind == "glucose" and data.events[0].available_at is None


def test_azt_canonical_files_only_and_zero_encoding_retained(tmp_path: Path) -> None:
    path = tmp_path / "azt.zip"
    csv = (
        "EventDateTime,CGM,CarbSize,TotalBolusInsulinDelivered,Basal\n"
        "2020-01-01 10:00:00,100,0,0,1\n"
        "2020-01-01 10:05:00,105,25,1,1\n"
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("AZT1D 2025/CGM Records/Subject 1/Subject 1.csv", csv)
        archive.writestr("__MACOSX/AZT1D 2025/CGM Records/Subject 1/._Subject 1.csv", "metadata")
        archive.writestr("AZT1D 2025/Visual Statistics/Subject 1.csv", "analysis")
    result = read_azt1d(path)
    assert len(result) == 1 and len(result[0].events) == 8
    unknown = [e for e in result[0].events if e.observation_status == "zero_encoding_unverified"]
    assert len(unknown) == 2 and all(e.value is None for e in unknown)
    assert all(e.unit == "source_unit_unverified" for e in result[0].events if e.kind == "basal")
    assert all(not e.timezone_known and e.available_at is None for e in result[0].events)


def test_azt_mixed_glucose_header_does_not_become_verified_cgm(tmp_path: Path) -> None:
    path = tmp_path / "azt.zip"
    csv = (
        "EventDateTime,Readings (CGM / BGM),CarbSize,TotalBolusInsulinDelivered,Basal\n"
        "2020-01-01 10:00:00,100,0,0,1\n"
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("AZT1D 2025/CGM Records/Subject 14/Subject 14.csv", csv)
    data = read_azt1d(path)[0]
    glucose = [e for e in data.events if e.kind == "glucose"]
    assert len(glucose) == 1 and glucose[0].glucose_type == "unverified_cgm_or_bgm"
