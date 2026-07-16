from __future__ import annotations

import pandas as pd
import pytest

from data_contracts.nwp_schema import (
    NwpContractError,
    canonicalize_nwp_frame,
    validate_nwp_frame,
)


def test_valid_ifs_frame_satisfies_schema(valid_ifs_frame: pd.DataFrame) -> None:
    result = validate_nwp_frame(valid_ifs_frame)
    assert result.equals(valid_ifs_frame)


def test_duplicate_primary_key_is_rejected(valid_ifs_frame: pd.DataFrame) -> None:
    duplicate = pd.concat([valid_ifs_frame, valid_ifs_frame.iloc[[1]]], ignore_index=True)
    with pytest.raises(NwpContractError, match="duplicate primary key"):
        validate_nwp_frame(duplicate)


def test_lead_time_must_equal_valid_minus_issue(valid_ifs_frame: pd.DataFrame) -> None:
    invalid = valid_ifs_frame.copy()
    invalid.loc[1, "lead_time_min"] = 179
    with pytest.raises(NwpContractError, match="lead_time_min"):
        validate_nwp_frame(invalid)


@pytest.mark.parametrize("value", [-0.0001, 1.0001])
def test_cloud_fraction_out_of_bounds_is_rejected(
    valid_ifs_frame: pd.DataFrame, value: float
) -> None:
    invalid = valid_ifs_frame.copy()
    invalid.loc[1, "tcc_frac"] = value
    with pytest.raises(NwpContractError, match="tcc_frac"):
        validate_nwp_frame(invalid)


def test_source_model_pair_must_match(valid_ifs_frame: pd.DataFrame) -> None:
    invalid = valid_ifs_frame.copy()
    invalid["nwp_model"] = "aifs-single"
    with pytest.raises(NwpContractError, match="source/model"):
        validate_nwp_frame(invalid)


def test_grid_coordinates_are_constant_within_run(valid_ifs_frame: pd.DataFrame) -> None:
    invalid = valid_ifs_frame.copy()
    invalid.loc[1, "grid_longitude"] = 116.50
    with pytest.raises(NwpContractError, match="grid coordinates"):
        validate_nwp_frame(invalid)


def test_all_null_model_specific_columns_receive_stable_numeric_dtypes(
    valid_ifs_frame: pd.DataFrame,
) -> None:
    canonical = canonicalize_nwp_frame(valid_ifs_frame)
    for column in ("lcc_frac", "mcc_frac", "hcc_frac", "cp_accum_m", "cp_interval_m", "cp_mm"):
        assert str(canonical[column].dtype) == "Float64"
    for column in ("lead_time_min", "schema_version"):
        assert str(canonical[column].dtype) == "Int64"


def test_canonicalization_stabilizes_utc_timestamps_at_nanoseconds(
    valid_ifs_frame: pd.DataFrame,
) -> None:
    microsecond_frame = valid_ifs_frame.copy()
    timestamp_columns = ("issue_time_utc", "valid_time_utc", "retrieved_at_utc")
    for column in timestamp_columns:
        microsecond_frame[column] = microsecond_frame[column].astype(
            "datetime64[us, UTC]"
        )

    canonical = canonicalize_nwp_frame(microsecond_frame)

    for column in timestamp_columns:
        assert str(canonical[column].dtype) == "datetime64[ns, UTC]"
