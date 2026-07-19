from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.characterisation.coverage_xlsx import (
    ingest_coverage_xlsx,
    parse_coverage_filename,
)


def _write_workbook(path: Path, value_column: str, values: list[float]) -> None:
    frame = pd.DataFrame(
        {
            "Unnamed: 0": range(len(values) + 1),
            "date_time": [
                pd.Timestamp("2026-06-01 12:00:00"),
                pd.Timestamp("2026-06-01 12:01:00"),
                pd.NaT,
            ],
            value_column: [*values, 99999.0],
            "object_caeid": ["0", "0", "helper"],
            "Tanggal/Waktu": [
                pd.Timestamp("2026-06-01 00:00:00"),
                pd.Timestamp("2026-06-01 00:05:00"),
                pd.Timestamp("2026-06-01 00:10:00"),
            ],
        }
    )
    frame.to_excel(path, index=False)


def test_parse_coverage_filename_standardized_channels() -> None:
    cases = {
        "GHI_PLTS-IKN_WS-1_2026-Juni.xlsx": ("GHI", None, "1", "standardized"),
        "DHI_PLTS-IKN_WS-3_2026-Mar.xlsx": ("DHI", None, "3", "standardized"),
        "DNIcosZ_PLTS-IKN_WS-4_2025-Dec.xlsx": ("DNIcosZ", None, "4", "standardized"),
        "POA_PLTS-IKN_WS-2_2026-Jan.xlsx": ("POA", None, "2", "standardized"),
        "RSI_01_PLTS-IKN_WS-4_2026-Feb.xlsx": ("RSI", "RSI_01", "4", "standardized"),
        "RSI_03_PLTS-IKN_WS-1_2026-Juni.xlsx": ("RSI", "RSI_03", "1", "standardized"),
        "Total_Irradiance_PLTS-IKN_WS-5_2025-Dec.xlsx": (
            "GHI",
            None,
            "5",
            "standardized",
        ),
    }
    for name, expected in cases.items():
        identity = parse_coverage_filename(name)
        assert identity is not None, name
        assert (
            identity.channel_group,
            identity.subchannel,
            identity.ws,
            identity.filename_schema,
        ) == expected, name


def test_parse_coverage_filename_rejects_non_instantaneous_files() -> None:
    rejected = [
        "GHI_Daily_Accum_PLTS-IKN_WS-1_2026-Juni.xlsx",
        "RSI_01_Yearly_Accum_PLTS-IKN_WS-4_2026-Feb.xlsx",
        "Daily_Radiation_PLTS-IKN_WS-5_2025-Dec.xlsx",
        "Ambient_Air_Humidity_PLTS-IKN_WS-1_2026-Juni.xlsx",
        "PV_Modul_Temp_01_PLTS-IKN_WS-1_2026-Juni.xlsx",
        "Peak_of_Sun_Hours_PLTS-IKN_WS-3_2026-Mar.xlsx",
        "Wind_Speed_PLTS-IKN_WS-5_2025-Dec.xlsx",
        "GHI Daily Accumulation WS-1 PLTS IKN Juli 2025.xlsx",
    ]
    for name in rejected:
        assert parse_coverage_filename(name) is None, name


def test_parse_coverage_filename_legacy_names() -> None:
    cases = {
        "GHI WS-1 PLTS IKN Agustus 2025.xlsx": ("GHI", None, "1", "legacy"),
        "DNI cosZ WS-2 PLTS IKN Juli 2025.xlsx": ("DNIcosZ", None, "2", "legacy"),
        "DHI WS-4 PLTS IKN Oktober 2025.xlsx": ("DHI", None, "4", "legacy"),
        "POA WS-3 PLTS IKN September 2025.xlsx": ("POA", None, "3", "legacy"),
        "RSI 02 WS-4 PLTS IKN Juli 2025.xlsx": ("RSI", "RSI_02", "4", "legacy"),
        "Total Irradiance WS-5 PLTS IKN Juli 2025.xlsx": ("GHI", None, "5", "legacy"),
    }
    for name, expected in cases.items():
        identity = parse_coverage_filename(name)
        assert identity is not None, name
        assert (
            identity.channel_group,
            identity.subchannel,
            identity.ws,
            identity.filename_schema,
        ) == expected, name


def test_ingest_coverage_xlsx_reads_raw_columns_across_channels(
    tmp_path: Path,
) -> None:
    poa = tmp_path / "POA_PLTS-IKN_WS-2_2026-Juni.xlsx"
    _write_workbook(poa, "POA_PLTS-IKN_WS-2_2026-Juni", [700.0, 701.0])
    rsi = tmp_path / "RSI_02_PLTS-IKN_WS-4_2026-Juni.xlsx"
    _write_workbook(rsi, "RSI_02_PLTS-IKN_WS-4_2026-Juni", [80.0, 81.0])
    ws5 = tmp_path / "Total_Irradiance_PLTS-IKN_WS-5_2026-Juni.xlsx"
    _write_workbook(ws5, "Total_Irradiance_PLTS-IKN_WS-5_2026-Juni", [500.0, 501.0])
    _write_workbook(
        tmp_path / "POA_Daily_Accum_PLTS-IKN_WS-2_2026-Juni.xlsx",
        "POA_Daily_Accum_PLTS-IKN_WS-2_2026-Juni",
        [1000.0, 2000.0],
    )

    result = ingest_coverage_xlsx(tmp_path)

    assert result.strict_errors == ()
    records = result.events[
        ["emi", "channel_group", "channel_key", "value"]
    ].to_dict("records")
    assert records == [
        {"emi": "EMI02", "channel_group": "POA", "channel_key": "POA", "value": 700.0},
        {"emi": "EMI02", "channel_group": "POA", "channel_key": "POA", "value": 701.0},
        {
            "emi": "EMI04",
            "channel_group": "RSI",
            "channel_key": "RSI_02",
            "value": 80.0,
        },
        {
            "emi": "EMI04",
            "channel_group": "RSI",
            "channel_key": "RSI_02",
            "value": 81.0,
        },
        {"emi": "EMI05", "channel_group": "GHI", "channel_key": "GHI", "value": 500.0},
        {"emi": "EMI05", "channel_group": "GHI", "channel_key": "GHI", "value": 501.0},
    ]
    manifest = result.source_manifest
    assert manifest["xlsx_name"].tolist() == [poa.name, rsi.name, ws5.name]
    assert manifest["sha256"].str.len().eq(64).all()
    assert manifest["subchannel"].tolist() == [None, "RSI_02", None]


def test_ingest_coverage_xlsx_records_strict_error_for_bad_layout(
    tmp_path: Path,
) -> None:
    path = tmp_path / "GHI_PLTS-IKN_WS-1_2026-Juni.xlsx"
    frame = pd.DataFrame({"date_time": [pd.Timestamp("2026-06-01 12:00:00")]})
    frame.to_excel(path, index=False)

    result = ingest_coverage_xlsx(tmp_path)

    assert result.events.empty
    assert len(result.strict_errors) == 1
    assert "object_caeid" in result.strict_errors[0]
