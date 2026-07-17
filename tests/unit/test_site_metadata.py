from __future__ import annotations

import copy

import pytest

from src.characterisation.site_metadata import (
    SiteMetadataError,
    collect_site_metadata_errors,
    validate_site_metadata_config,
)


def build_valid_config() -> dict:
    return {
        "site": {
            "site_id": "PLTS-IKN",
            "name": "PLTS IKN 10MW",
            "latitude_deg": -0.9911713315158186,
            "longitude_deg": 116.63811127764585,
            "elevation_m": 85.0,
            "timezone": "Asia/Makassar",
            "canonical_freq": "1min",
            "racking_type": "fixed",
            "surface_tilt_deg": 10.0,
            "surface_azimuth_deg": 0.0,
            "poa_is_coplanar_with_modules": True,
            "collector_width_m": 5.0,
            "row_clear_gap_front_m": 2.5,
            "row_pitch_m": 7.424,
            "gcr": 0.6735,
            "module_height_m": 1.46,
            "bifaciality_factor": 0.80,
            "albedo_default": 0.153,
            "has_albedometer": False,
            "horizons_min": None,
            "daylight_elev_threshold_deg": None,
            "clearsky_model": None,
            "nrmse_denominator": None,
            "valid_from": "2026-07-17",
            "valid_to": None,
        },
        "sensor_metadata": {
            "dni_cosz": {
                "canonical_name": "Direct Horizontal Irradiance (DNIcosZ)",
                "is_derived_tag": False,
                "semantics_decision": "measured",
                "serial": None,
                "calibration_date": None,
                "calibration_due": None,
                "calibration_factor": None,
            },
            "rsi": {
                "canonical_name": "Rear-Side Irradiance (RSI)",
                "serial": None,
                "calibration_date": None,
                "calibration_due": None,
                "calibration_factor": None,
                "sensors": [
                    {
                        "sensor_id": "WS1.1",
                        "height_agl_m": 1.47,
                        "mounting_tilt_deg": 9.0,
                    },
                    {
                        "sensor_id": "WS3.1",
                        "height_agl_m": None,
                        "mounting_tilt_deg": 10.0,
                        "status_note": "reported removed during troubleshooting",
                    },
                ],
            },
        },
        "provenance": {
            "latitude_deg": {
                "method": "supplied",
                "source": "product owner statement",
                "confidence": "medium",
            },
        },
        "unresolved_metadata": [
            {
                "field": "sensor_metadata.*.serial",
                "reason": "serials not in supplied documents",
                "owner": "O&M Engineering",
                "due_date": "2026-07-24",
            },
            {
                "field": (
                    "sensor_metadata.*.calibration_date/"
                    "calibration_due/calibration_factor"
                ),
                "reason": "certificates not supplied",
                "owner": "O&M Engineering",
                "due_date": "2026-07-24",
            },
            {
                "field": (
                    "site.horizons_min/site.daylight_elev_threshold_deg/"
                    "site.clearsky_model/site.nrmse_denominator"
                ),
                "reason": "Phase 1 policy decisions",
                "owner": "ML Engineering",
                "due_date": "2026-08-07",
            },
        ],
    }


def test_valid_config_passes() -> None:
    validate_site_metadata_config(build_valid_config())


def assert_single_complaint(config: dict, fragment: str) -> None:
    errors = collect_site_metadata_errors(config)
    assert any(fragment in error for error in errors), errors
    with pytest.raises(SiteMetadataError):
        validate_site_metadata_config(config)


def test_missing_latitude_refuses() -> None:
    config = build_valid_config()
    config["site"]["latitude_deg"] = None
    assert_single_complaint(config, "latitude_deg")


def test_zero_zero_coordinates_rejected() -> None:
    config = build_valid_config()
    config["site"]["latitude_deg"] = 0.0
    config["site"]["longitude_deg"] = 0.0
    assert_single_complaint(config, "0,0")


def test_latitude_out_of_range_rejected() -> None:
    config = build_valid_config()
    config["site"]["latitude_deg"] = 91.0
    assert_single_complaint(config, "latitude_deg")


def test_invalid_timezone_rejected() -> None:
    config = build_valid_config()
    config["site"]["timezone"] = "Mars/Olympus"
    assert_single_complaint(config, "timezone")


def test_unknown_racking_type_rejected() -> None:
    config = build_valid_config()
    config["site"]["racking_type"] = "dual_axis"
    assert_single_complaint(config, "racking_type")


def test_fixed_racking_requires_tilt_and_azimuth() -> None:
    config = build_valid_config()
    config["site"]["surface_tilt_deg"] = None
    assert_single_complaint(config, "surface_tilt_deg")


def test_gcr_above_one_rejected() -> None:
    config = build_valid_config()
    config["site"]["gcr"] = 2.0
    assert_single_complaint(config, "gcr")


def test_bifaciality_above_one_rejected() -> None:
    config = build_valid_config()
    config["site"]["bifaciality_factor"] = 1.2
    assert_single_complaint(config, "bifaciality_factor")


def test_albedo_out_of_range_rejected() -> None:
    config = build_valid_config()
    config["site"]["albedo_default"] = 1.5
    assert_single_complaint(config, "albedo_default")


def test_row_pitch_must_match_geometry() -> None:
    config = build_valid_config()
    config["site"]["row_pitch_m"] = 9.0
    assert_single_complaint(config, "row_pitch_m")


def test_gcr_must_match_width_over_pitch() -> None:
    config = build_valid_config()
    config["site"]["gcr"] = 0.62
    assert_single_complaint(config, "gcr")


def test_dni_cosz_decision_boolean_is_locked() -> None:
    config = build_valid_config()
    config["sensor_metadata"]["dni_cosz"]["is_derived_tag"] = True
    assert_single_complaint(config, "is_derived_tag")


def test_unresolved_entry_requires_owner() -> None:
    config = build_valid_config()
    config["unresolved_metadata"][0].pop("owner")
    assert_single_complaint(config, "owner")


def test_unresolved_entry_requires_iso_due_date() -> None:
    config = build_valid_config()
    config["unresolved_metadata"][0]["due_date"] = "next week"
    assert_single_complaint(config, "due_date")


def test_null_policy_field_needs_unresolved_coverage() -> None:
    config = build_valid_config()
    config["unresolved_metadata"] = [
        entry
        for entry in config["unresolved_metadata"]
        if "clearsky_model" not in entry["field"]
    ]
    assert_single_complaint(config, "clearsky_model")


def test_null_serial_needs_unresolved_coverage() -> None:
    config = build_valid_config()
    config["unresolved_metadata"] = [
        entry
        for entry in config["unresolved_metadata"]
        if "serial" not in entry["field"]
    ]
    assert_single_complaint(config, "serial")


def test_rsi_sensor_without_height_needs_status_note() -> None:
    config = build_valid_config()
    del config["sensor_metadata"]["rsi"]["sensors"][1]["status_note"]
    assert_single_complaint(config, "status_note")


def test_provenance_method_vocabulary_enforced() -> None:
    config = build_valid_config()
    config["provenance"]["latitude_deg"]["method"] = "guessed"
    assert_single_complaint(config, "method")


def test_provenance_confidence_vocabulary_enforced() -> None:
    config = build_valid_config()
    config["provenance"]["latitude_deg"]["confidence"] = "certain"
    assert_single_complaint(config, "confidence")


def test_module_height_must_be_positive() -> None:
    config = build_valid_config()
    config["site"]["module_height_m"] = -1.0
    assert_single_complaint(config, "module_height_m")


def test_errors_do_not_mutate_input() -> None:
    config = build_valid_config()
    snapshot = copy.deepcopy(config)
    collect_site_metadata_errors(config)
    assert config == snapshot
