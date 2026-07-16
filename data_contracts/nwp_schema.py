from __future__ import annotations

from datetime import datetime, timezone
from typing import Final

import pandas as pd
from pandas.api.types import is_numeric_dtype


NWP_SCHEMA_VERSION: Final[int] = 1
NWP_PRIMARY_KEY: Final[tuple[str, ...]] = (
    "site_id",
    "nwp_source",
    "issue_time_utc",
    "valid_time_utc",
)
TIMESTAMP_COLUMNS: Final[tuple[str, ...]] = (
    "issue_time_utc",
    "valid_time_utc",
    "retrieved_at_utc",
)
CLOUD_COLUMNS: Final[tuple[str, ...]] = (
    "tcc_frac",
    "lcc_frac",
    "mcc_frac",
    "hcc_frac",
)
NUMERIC_COLUMNS: Final[tuple[str, ...]] = (
    "lead_time_min",
    "ssrd_wm2",
    "ssrd_accum_jm2",
    "ssrd_interval_jm2",
    "ssrd_interval_seconds",
    "tcc_frac",
    "lcc_frac",
    "mcc_frac",
    "hcc_frac",
    "t2m_c",
    "d2m_c",
    "u10_ms",
    "v10_ms",
    "tp_accum_m",
    "tp_interval_m",
    "tp_mm",
    "sp_pa",
    "sp_hpa",
    "tcwv_kgm2",
    "cp_accum_m",
    "cp_interval_m",
    "cp_mm",
    "mucape_jkg",
    "site_latitude",
    "site_longitude",
    "grid_latitude",
    "grid_longitude",
    "grid_distance_km",
    "grib_start_step_h",
    "grib_end_step_h",
    "schema_version",
)
NWP_COLUMNS: Final[tuple[str, ...]] = (
    "site_id",
    "nwp_provider",
    "nwp_source",
    "nwp_model",
    "issue_time_utc",
    "valid_time_utc",
    "retrieved_at_utc",
    "lead_time_min",
    "ssrd_wm2",
    "ssrd_accum_jm2",
    "ssrd_interval_jm2",
    "ssrd_interval_seconds",
    "ssrd_conversion_method",
    "grib_start_step_h",
    "grib_end_step_h",
    "grib_step_type",
    "tcc_frac",
    "lcc_frac",
    "mcc_frac",
    "hcc_frac",
    "t2m_c",
    "d2m_c",
    "u10_ms",
    "v10_ms",
    "tp_accum_m",
    "tp_interval_m",
    "tp_mm",
    "sp_pa",
    "sp_hpa",
    "tcwv_kgm2",
    "cp_accum_m",
    "cp_interval_m",
    "cp_mm",
    "mucape_jkg",
    "site_latitude",
    "site_longitude",
    "grid_latitude",
    "grid_longitude",
    "grid_distance_km",
    "grid_selection_method",
    "ecmwf_client_source",
    "ecmwf_client_version",
    "eccodes_version",
    "schema_version",
    "ecmwf_dataset_url",
    "licence_id",
)
NWP_INTEGER_COLUMNS: Final[tuple[str, ...]] = (
    "lead_time_min",
    "ssrd_interval_seconds",
    "grib_start_step_h",
    "grib_end_step_h",
    "schema_version",
)
NWP_FLOAT_COLUMNS: Final[tuple[str, ...]] = tuple(
    column for column in NUMERIC_COLUMNS if column not in NWP_INTEGER_COLUMNS
)
NWP_STRING_COLUMNS: Final[tuple[str, ...]] = tuple(
    column
    for column in NWP_COLUMNS
    if column not in TIMESTAMP_COLUMNS and column not in NUMERIC_COLUMNS
)
SOURCE_MODEL = {"ecmwf_ifs": "ifs", "ecmwf_aifs_single": "aifs-single"}


class NwpContractError(ValueError):
    pass


def _require_utc_dtype(frame: pd.DataFrame, column: str) -> None:
    dtype = frame[column].dtype
    if not isinstance(dtype, pd.DatetimeTZDtype) or str(dtype.tz) != "UTC":
        raise NwpContractError(f"{column} must use timezone-aware UTC dtype")


def validate_nwp_frame(frame: pd.DataFrame) -> pd.DataFrame:
    missing = [column for column in NWP_COLUMNS if column not in frame.columns]
    if missing:
        raise NwpContractError(f"missing columns: {missing}")
    for column in TIMESTAMP_COLUMNS:
        _require_utc_dtype(frame, column)
        if frame[column].isna().any():
            raise NwpContractError(f"{column} must be non-null")
    for column in NUMERIC_COLUMNS:
        if not is_numeric_dtype(frame[column]) and frame[column].notna().any():
            raise NwpContractError(f"{column} must be numeric")
    if frame[list(NWP_PRIMARY_KEY)].isna().any().any():
        raise NwpContractError("primary key must be non-null")
    if frame.duplicated(list(NWP_PRIMARY_KEY)).any():
        raise NwpContractError("duplicate primary key")
    expected_model = frame["nwp_source"].map(SOURCE_MODEL)
    if expected_model.isna().any() or (expected_model != frame["nwp_model"]).any():
        raise NwpContractError("source/model pair is invalid")
    expected_lead = (
        (frame["valid_time_utc"] - frame["issue_time_utc"]).dt.total_seconds() / 60
    ).astype("int64")
    if not expected_lead.equals(frame["lead_time_min"].astype("int64")):
        raise NwpContractError("lead_time_min does not match valid minus issue")
    if (frame["valid_time_utc"] < frame["issue_time_utc"]).any():
        raise NwpContractError("valid_time_utc precedes issue_time_utc")
    if (frame["retrieved_at_utc"] < frame["issue_time_utc"]).any():
        raise NwpContractError("retrieved_at_utc precedes issue_time_utc")
    for column in CLOUD_COLUMNS:
        valid = frame[column].dropna()
        if not valid.between(0.0, 1.0, inclusive="both").all():
            raise NwpContractError(f"{column} must be in [0, 1]")
    if (frame["grid_distance_km"] > 25.0).any() or (
        frame["grid_distance_km"] < 0
    ).any():
        raise NwpContractError("grid_distance_km must be in [0, 25]")
    grouped = frame.groupby(["nwp_source", "issue_time_utc"], dropna=False)
    if (
        grouped["grid_latitude"].nunique().max() != 1
        or grouped["grid_longitude"].nunique().max() != 1
    ):
        raise NwpContractError("grid coordinates must be constant within a run")
    if not (frame["schema_version"] == NWP_SCHEMA_VERSION).all():
        raise NwpContractError("schema_version mismatch")
    return frame


def canonicalize_nwp_frame(frame: pd.DataFrame) -> pd.DataFrame:
    validated = validate_nwp_frame(frame)
    canonical = validated.copy()
    for column in TIMESTAMP_COLUMNS:
        canonical[column] = canonical[column].astype("datetime64[ns, UTC]")
    for column in NWP_INTEGER_COLUMNS:
        canonical[column] = pd.to_numeric(canonical[column]).astype("Int64")
    for column in NWP_FLOAT_COLUMNS:
        canonical[column] = pd.to_numeric(canonical[column]).astype("Float64")
    for column in NWP_STRING_COLUMNS:
        canonical[column] = canonical[column].astype("string")
    return validate_nwp_frame(canonical)


def available_nwp_as_of(frame: pd.DataFrame, as_of_utc: datetime) -> pd.DataFrame:
    if (
        as_of_utc.tzinfo is None
        or as_of_utc.utcoffset() != timezone.utc.utcoffset(as_of_utc)
    ):
        raise NwpContractError("as_of_utc must be timezone-aware UTC")
    validated = validate_nwp_frame(frame)
    return validated.loc[
        validated["retrieved_at_utc"] <= pd.Timestamp(as_of_utc)
    ].copy()
