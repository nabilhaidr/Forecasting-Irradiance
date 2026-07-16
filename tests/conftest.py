from __future__ import annotations

import pandas as pd
import pytest


@pytest.fixture
def valid_ifs_frame() -> pd.DataFrame:
    issue = pd.Timestamp("2026-07-16T06:00:00Z").as_unit("ns")
    retrieved = pd.Timestamp("2026-07-16T07:15:30Z").as_unit("ns")
    common = {
        "site_id": "PLTS-IKN",
        "nwp_provider": "ecmwf_opendata",
        "nwp_source": "ecmwf_ifs",
        "nwp_model": "ifs",
        "issue_time_utc": issue,
        "retrieved_at_utc": retrieved,
        "site_latitude": -0.9911713315158186,
        "site_longitude": 116.63811127764585,
        "grid_latitude": -1.0,
        "grid_longitude": 116.75,
        "grid_distance_km": 12.478274049682074,
        "grid_selection_method": "nearest",
        "lcc_frac": None,
        "mcc_frac": None,
        "hcc_frac": None,
        "cp_accum_m": None,
        "cp_interval_m": None,
        "cp_mm": None,
        "ecmwf_client_source": "google",
        "ecmwf_client_version": "0.3.30",
        "eccodes_version": "2.47.0",
        "schema_version": 1,
        "ecmwf_dataset_url": "https://www.ecmwf.int/en/forecasts/datasets/open-data",
        "licence_id": "CC-BY-4.0",
    }
    rows = [
        {
            **common,
            "valid_time_utc": issue,
            "lead_time_min": 0,
            "ssrd_wm2": None,
            "ssrd_accum_jm2": 0.0,
            "ssrd_interval_jm2": None,
            "ssrd_interval_seconds": 0,
            "ssrd_conversion_method": "lead_zero",
            "grib_start_step_h": 0,
            "grib_end_step_h": 0,
            "grib_step_type": "accum",
            "tcc_frac": 0.20,
            "t2m_c": 25.0,
            "d2m_c": 24.0,
            "u10_ms": 2.0,
            "v10_ms": -1.0,
            "tp_accum_m": 0.0,
            "tp_interval_m": None,
            "tp_mm": None,
            "sp_pa": 100000.0,
            "sp_hpa": 1000.0,
            "tcwv_kgm2": 30.0,
            "mucape_jkg": 400.0,
        },
        {
            **common,
            "valid_time_utc": issue + pd.Timedelta(hours=3),
            "lead_time_min": 180,
            "ssrd_wm2": 100.0,
            "ssrd_accum_jm2": 1_080_000.0,
            "ssrd_interval_jm2": 1_080_000.0,
            "ssrd_interval_seconds": 10_800,
            "ssrd_conversion_method": "run_total_difference",
            "grib_start_step_h": 0,
            "grib_end_step_h": 3,
            "grib_step_type": "accum",
            "tcc_frac": 0.25,
            "t2m_c": 26.85,
            "d2m_c": 25.0,
            "u10_ms": 2.5,
            "v10_ms": -1.0,
            "tp_accum_m": 0.0012,
            "tp_interval_m": 0.0012,
            "tp_mm": 1.2,
            "sp_pa": 100000.0,
            "sp_hpa": 1000.0,
            "tcwv_kgm2": 30.0,
            "mucape_jkg": 400.0,
        },
    ]
    return pd.DataFrame(rows)
