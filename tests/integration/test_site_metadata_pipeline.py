"""Cross-consistency checks between the canonical S0-4 config, the audit
artifacts, and the audit report. These tests consume only committed files;
the untracked ``spec raw/`` sources are not required."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import yaml

from src.characterisation.site_metadata import load_site_metadata

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "configs" / "site_plts-ikn.yaml"
ARTIFACT_DIR = ROOT / "artifacts" / "phase0_site_metadata"
REPORT_PATH = ROOT / "docs" / "phase0_site_metadata_audit.md"
NORMATIVE_DOCS = (
    ROOT / "PRD_Forecasting_Irradiance_ML.md",
    ROOT / "MASTER_CONTEXT_Forecasting_Irradiance_ML.md",
    ROOT / "ROADMAP_Forecasting_Irradiance_ML.md",
)


def load_audit() -> dict:
    return json.loads(
        (ARTIFACT_DIR / "site_metadata_audit.json").read_text(encoding="utf-8")
    )


def test_canonical_config_validates() -> None:
    load_site_metadata(CONFIG_PATH)


def test_config_geometry_matches_audit_artifact() -> None:
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    site = config["site"]
    derived = load_audit()["derived_geometry"]

    assert abs(site["gcr"] - derived["gcr"]) <= 0.0005
    assert abs(site["row_pitch_m"] - derived["row_pitch_m"]) <= 0.005
    assert (
        abs(site["module_height_m"] - derived["module_height_m"]["value"]) <= 0.005
    )
    assert site["collector_width_m"] == derived["inputs"]["collector_width_m"]
    assert site["row_clear_gap_front_m"] == derived["inputs"]["front_clear_gap_m"]
    assert site["surface_tilt_deg"] == derived["inputs"]["nominal_tilt_deg"]


def test_config_albedo_matches_audit_artifact() -> None:
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    summary = load_audit()["albedo_tmy_summary"]
    assert abs(config["site"]["albedo_default"] - summary["annual_mean"]) <= 0.0005
    assert summary["sample_count"] == 35040


def test_rsi_survey_artifact_matches_config_sensors() -> None:
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    with (ARTIFACT_DIR / "rsi_mounting_survey.csv").open(
        encoding="utf-8", newline=""
    ) as fh:
        rows = list(csv.DictReader(fh))

    config_sensors = config["sensor_metadata"]["rsi"]["sensors"]
    assert len(rows) == 12
    assert len(config_sensors) == 12

    by_id = {row["sensor_id"]: row for row in rows}
    for sensor in config_sensors:
        surveyed = by_id[sensor["sensor_id"]]
        expected_height_m = float(surveyed["module_edge_height_cm"]) / 100.0
        assert abs(sensor["module_edge_height_m"] - expected_height_m) < 1e-9
        assert float(surveyed["measured_tilt_deg"]) == sensor["mounting_tilt_deg"]
        if surveyed["pyranometer_height_cm"] == "":
            assert sensor["height_agl_m"] is None
            assert sensor.get("status_note")
        else:
            assert (
                abs(
                    sensor["height_agl_m"]
                    - float(surveyed["pyranometer_height_cm"]) / 100.0
                )
                < 1e-9
            )


def test_row_geometry_artifact_covers_both_phases() -> None:
    with (ARTIFACT_DIR / "row_geometry_survey.csv").open(
        encoding="utf-8", newline=""
    ) as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 2
    widths = {float(row["table_width_m"]) for row in rows}
    front_gaps = {float(row["front_clear_gap_m"]) for row in rows}
    assert widths == {5.0}
    assert front_gaps == {2.5}


def test_source_manifest_lists_spec_raw_only() -> None:
    with (ARTIFACT_DIR / "source_manifest.csv").open(
        encoding="utf-8", newline=""
    ) as fh:
        rows = list(csv.DictReader(fh))
    assert rows, "source manifest must not be empty"
    for row in rows:
        assert row["relative_path"].startswith("spec raw/")
        assert int(row["bytes"]) > 0
        assert len(row["sha256"]) == 64


def test_audit_report_status_contract() -> None:
    report = REPORT_PATH.read_text(encoding="utf-8")
    assert "S0-4 acceptance status: **YELLOW**" in report
    assert "artifacts/phase0_site_metadata" in report
    assert "unresolved" in report.lower()
    assert "calibration" in report.lower()


def test_normative_docs_reference_site_metadata_evidence() -> None:
    for path in NORMATIVE_DOCS:
        text = path.read_text(encoding="utf-8")
        assert "S0-4" in text, path.name
        assert "artifacts/phase0_site_metadata" in text, path.name
