"""S0-4 canonical site/sensor metadata schema validation.

Validates ``configs/site_plts-ikn.yaml`` against the Sprint 0 metadata
contract: FR-004 core facts must be present and physical, derived geometry
must stay internally consistent with its own derivation, the S0-3 DNI·cosZ
decision boolean is locked, and every critical null must be covered by an
``unresolved_metadata`` entry that names an owner, a reason, and a due date.
"""

from __future__ import annotations

import math
from datetime import date
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

PROVENANCE_METHODS = {"measured", "calculated", "supplied", "assumed"}
PROVENANCE_CONFIDENCES = {"low", "medium", "high"}
RACKING_TYPES = {"fixed", "single_axis"}

# Site keys that may be null only when an unresolved_metadata entry names them.
DEFERRABLE_SITE_KEYS = (
    "horizons_min",
    "daylight_elev_threshold_deg",
    "clearsky_model",
    "nrmse_denominator",
)
# Per-channel keys that may be null only when covered by unresolved_metadata.
DEFERRABLE_CHANNEL_KEYS = (
    "serial",
    "calibration_date",
    "calibration_due",
    "calibration_factor",
)

ROW_PITCH_TOLERANCE_M = 0.05
GCR_TOLERANCE = 0.005


class SiteMetadataError(ValueError):
    """Raised when the canonical site metadata violates the S0-4 contract."""


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _unresolved_field_text(config: dict) -> str:
    entries = config.get("unresolved_metadata") or []
    return " ".join(str(entry.get("field", "")) for entry in entries)


def collect_site_metadata_errors(config: dict) -> list[str]:
    """Return every contract violation found in the parsed config."""

    errors: list[str] = []
    site = config.get("site")
    if not isinstance(site, dict):
        return ["config must contain a 'site' mapping"]

    # --- FR-004 core facts: refuse rather than default -----------------
    latitude = site.get("latitude_deg")
    longitude = site.get("longitude_deg")
    if not _is_number(latitude) or not (-90.0 <= latitude <= 90.0):
        errors.append(
            "site.latitude_deg must be a number in [-90, 90]; refusing to "
            "default (FR-004)"
        )
    if not _is_number(longitude) or not (-180.0 <= longitude <= 180.0):
        errors.append(
            "site.longitude_deg must be a number in [-180, 180]; refusing to "
            "default (FR-004)"
        )
    if _is_number(latitude) and _is_number(longitude):
        if latitude == 0.0 and longitude == 0.0:
            errors.append(
                "site coordinates must not be the 0,0 placeholder (FR-004)"
            )

    elevation = site.get("elevation_m")
    if not _is_number(elevation) or not (-430.0 <= elevation <= 8850.0):
        errors.append("site.elevation_m must be a plausible number (FR-004)")

    timezone = site.get("timezone")
    if not isinstance(timezone, str) or not timezone:
        errors.append("site.timezone must be a non-empty IANA name (FR-004)")
    else:
        try:
            ZoneInfo(timezone)
        except Exception:
            errors.append(f"site.timezone {timezone!r} is not a valid IANA timezone")

    for key in ("site_id", "name", "canonical_freq"):
        if not site.get(key):
            errors.append(f"site.{key} must be present and non-empty")

    # --- Racking and orientation ---------------------------------------
    racking = site.get("racking_type")
    if racking not in RACKING_TYPES:
        errors.append(
            f"site.racking_type must be one of {sorted(RACKING_TYPES)}, "
            f"got {racking!r}"
        )
    if racking == "fixed":
        tilt = site.get("surface_tilt_deg")
        azimuth = site.get("surface_azimuth_deg")
        if not _is_number(tilt) or not (0.0 <= tilt <= 90.0):
            errors.append(
                "site.surface_tilt_deg is required for fixed racking and must "
                "be in [0, 90]"
            )
        if not _is_number(azimuth) or not (0.0 <= azimuth < 360.0):
            errors.append(
                "site.surface_azimuth_deg is required for fixed racking and "
                "must be in [0, 360)"
            )

    # --- Physical ranges for resolved values ---------------------------
    gcr = site.get("gcr")
    if gcr is not None and (not _is_number(gcr) or not (0.0 < gcr <= 1.0)):
        errors.append("site.gcr must lie in (0, 1] when resolved")

    bifaciality = site.get("bifaciality_factor")
    if bifaciality is not None and (
        not _is_number(bifaciality) or not (0.0 <= bifaciality <= 1.0)
    ):
        errors.append("site.bifaciality_factor must lie in [0, 1] when resolved")

    albedo = site.get("albedo_default")
    if albedo is not None and (
        not _is_number(albedo) or not (0.0 < albedo < 1.0)
    ):
        errors.append("site.albedo_default must lie in (0, 1) when resolved")

    module_height = site.get("module_height_m")
    if module_height is not None and (
        not _is_number(module_height) or module_height <= 0.0
    ):
        errors.append("site.module_height_m must be positive when resolved")

    # --- Derived-geometry internal consistency -------------------------
    width = site.get("collector_width_m")
    gap = site.get("row_clear_gap_front_m")
    pitch = site.get("row_pitch_m")
    tilt = site.get("surface_tilt_deg")
    if all(_is_number(value) for value in (width, gap, pitch, tilt)):
        expected_pitch = width * math.cos(math.radians(tilt)) + gap
        if abs(pitch - expected_pitch) > ROW_PITCH_TOLERANCE_M:
            errors.append(
                "site.row_pitch_m is inconsistent with collector_width_m * "
                f"cos(tilt) + row_clear_gap_front_m (expected ~{expected_pitch:.3f})"
            )
    if all(_is_number(value) for value in (width, pitch)) and _is_number(gcr):
        expected_gcr = width / pitch
        if abs(gcr - expected_gcr) > GCR_TOLERANCE:
            errors.append(
                "site.gcr is inconsistent with collector_width_m / row_pitch_m "
                f"(expected ~{expected_gcr:.4f})"
            )

    unresolved_text = _unresolved_field_text(config)

    # --- Deferred site policy fields need named coverage ----------------
    for key in DEFERRABLE_SITE_KEYS:
        if site.get(key) is None and key not in unresolved_text:
            errors.append(
                f"site.{key} is null but no unresolved_metadata entry names it"
            )

    # --- Sensor metadata -------------------------------------------------
    sensors = config.get("sensor_metadata")
    if not isinstance(sensors, dict) or not sensors:
        errors.append("config must contain a non-empty 'sensor_metadata' mapping")
        sensors = {}

    dni = sensors.get("dni_cosz")
    if isinstance(dni, dict):
        if dni.get("is_derived_tag") is not False:
            errors.append(
                "sensor_metadata.dni_cosz.is_derived_tag must be false: the "
                "S0-3 decision classified the channel as measured"
            )
        if dni.get("semantics_decision") != "measured":
            errors.append(
                "sensor_metadata.dni_cosz.semantics_decision must be 'measured'"
            )
    else:
        errors.append("sensor_metadata.dni_cosz must be present")

    for channel_name, channel in sensors.items():
        if not isinstance(channel, dict):
            errors.append(f"sensor_metadata.{channel_name} must be a mapping")
            continue
        if not channel.get("canonical_name"):
            errors.append(
                f"sensor_metadata.{channel_name}.canonical_name must be present"
            )
        for key in DEFERRABLE_CHANNEL_KEYS:
            if key in channel and channel[key] is None and key not in unresolved_text:
                errors.append(
                    f"sensor_metadata.{channel_name}.{key} is null but no "
                    "unresolved_metadata entry names it"
                )
        for sensor in channel.get("sensors") or []:
            if sensor.get("height_agl_m") is None and not sensor.get("status_note"):
                errors.append(
                    f"sensor_metadata.{channel_name} sensor "
                    f"{sensor.get('sensor_id')!r} has no height_agl_m and no "
                    "status_note explaining why"
                )

    # --- Provenance vocabulary ------------------------------------------
    for field_name, record in (config.get("provenance") or {}).items():
        if not isinstance(record, dict):
            errors.append(f"provenance.{field_name} must be a mapping")
            continue
        if record.get("method") not in PROVENANCE_METHODS:
            errors.append(
                f"provenance.{field_name}.method must be one of "
                f"{sorted(PROVENANCE_METHODS)}"
            )
        if record.get("confidence") not in PROVENANCE_CONFIDENCES:
            errors.append(
                f"provenance.{field_name}.confidence must be one of "
                f"{sorted(PROVENANCE_CONFIDENCES)}"
            )
        if not record.get("source"):
            errors.append(f"provenance.{field_name}.source must be non-empty")

    # --- Unresolved entries must be actionable ---------------------------
    for index, entry in enumerate(config.get("unresolved_metadata") or []):
        if not isinstance(entry, dict):
            errors.append(f"unresolved_metadata[{index}] must be a mapping")
            continue
        for key in ("field", "reason", "owner"):
            if not entry.get(key):
                errors.append(
                    f"unresolved_metadata[{index}] is missing a non-empty "
                    f"'{key}'"
                )
        due = entry.get("due_date")
        try:
            date.fromisoformat(str(due))
        except (TypeError, ValueError):
            errors.append(
                f"unresolved_metadata[{index}].due_date must be an ISO date, "
                f"got {due!r}"
            )

    return errors


def validate_site_metadata_config(config: dict) -> None:
    """Raise :class:`SiteMetadataError` listing every violation, if any."""

    errors = collect_site_metadata_errors(config)
    if errors:
        raise SiteMetadataError(
            "site metadata contract violations:\n- " + "\n- ".join(errors)
        )


def load_site_metadata(path: Path) -> dict:
    """Load and validate the canonical site metadata config."""

    config = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise SiteMetadataError(f"{path} did not parse to a mapping")
    validate_site_metadata_config(config)
    return config
