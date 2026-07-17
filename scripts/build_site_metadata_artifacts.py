"""Build deterministic S0-4 site-metadata audit artifacts from local sources.

Reads the untracked ``spec raw/`` source documents (survey workbook, TMY albedo
workbook, datasheets) and writes machine-readable audit artifacts into
``artifacts/phase0_site_metadata/``. The raw sources never enter Git; only the
derived audit evidence does. Every derived number is computed here so the
canonical config can be cross-checked against this script's output by the
integration tests.

Usage:
    python scripts/build_site_metadata_artifacts.py
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SPEC_RAW = ROOT / "spec raw"
OUT_DIR = ROOT / "artifacts" / "phase0_site_metadata"

BACKSIDE_XLSX = SPEC_RAW / "Backside Irradiance Sensor Data (raw).xlsx"
ALBEDO_XLSX = SPEC_RAW / "Surface Albedo Forecast TMY NSRDB PLTS IKN.xlsx"

# Nominal design tilt supplied by the product owner; the survey measured 9-10
# degrees at the four RSI-instrumented strings.
NOMINAL_TILT_DEG = 10.0
COLLECTOR_WIDTH_M = 5.00  # survey "Lebar" for both phases
FRONT_CLEAR_GAP_M = 2.50  # survey "Jarak antar PV String (depan)" both phases


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_source_manifest() -> list[dict[str, object]]:
    rows = []
    for path in sorted(SPEC_RAW.iterdir()):
        if not path.is_file():
            continue
        rows.append(
            {
                "relative_path": f"spec raw/{path.name}",
                "bytes": path.stat().st_size,
                "sha256": sha256_of(path),
            }
        )
    return rows


def build_rsi_survey() -> list[dict[str, object]]:
    df = pd.read_excel(BACKSIDE_XLSX, sheet_name="Sheet1")
    df = df.dropna(how="all")
    rows: list[dict[str, object]] = []
    for record in df.to_dict(orient="records"):
        pyr_height = record["Elevation from ground (Pyranometer) (cm)"]
        if isinstance(pyr_height, str) and pyr_height.strip() == "-":
            pyr_height = ""
        gap = record["Gap Between Array (cm)"]
        gap = "" if pd.isna(gap) else gap
        string = record["String"]
        string = "" if pd.isna(string) else string
        remark = record.get("Remarks")
        remark = "" if pd.isna(remark) else str(remark).strip()
        rows.append(
            {
                "sensor_id": record["Pyranometer"],
                "channel": str(record["Pyranometer Type"]).strip(),
                "string": string,
                "module_edge_height_cm": record[
                    "Eleveation from ground (Mounting) (cm)"
                ],
                "pyranometer_height_cm": pyr_height,
                "gap_below_array_cm": gap,
                "measured_tilt_deg": record["Tilt angle (o)"],
                "remark": remark,
            }
        )
    return rows


def build_row_geometry() -> list[dict[str, object]]:
    df = pd.read_excel(BACKSIDE_XLSX, sheet_name="PV String")
    df = df.dropna(subset=["Fase"])
    rows = []
    for record in df.to_dict(orient="records"):
        rows.append(
            {
                "phase": str(record["Fase"]).strip(),
                "table_length_m": record["Panjang (cm)"] / 100.0,
                "table_width_m": record["Lebar (cm)"] / 100.0,
                "post_spacing_m": record["Jarak antar tiang bim (cm)"] / 100.0,
                "side_clear_gap_m": record[
                    "Jarak antar PV String (samping) (cm)"
                ]
                / 100.0,
                "front_clear_gap_m": record[
                    "Jarak antar PV String (depan) (cm)"
                ]
                / 100.0,
            }
        )
    return rows


def build_albedo_monthly() -> tuple[list[dict[str, object]], dict[str, float]]:
    df = pd.read_excel(ALBEDO_XLSX)
    df["month"] = pd.to_datetime(df["Date/Time"]).dt.month
    monthly = (
        df.groupby("month")["Surface Albedo"].agg(["mean", "min", "max"]).round(6)
    )
    rows = [
        {
            "month": int(month),
            "albedo_mean": float(stats["mean"]),
            "albedo_min": float(stats["min"]),
            "albedo_max": float(stats["max"]),
        }
        for month, stats in monthly.iterrows()
    ]
    summary = {
        "annual_mean": round(float(df["Surface Albedo"].mean()), 6),
        "minimum": float(df["Surface Albedo"].min()),
        "maximum": float(df["Surface Albedo"].max()),
        "sample_count": int(len(df)),
    }
    return rows, summary


def derive_geometry(rsi_rows: list[dict[str, object]]) -> dict[str, object]:
    horizontal_footprint = COLLECTOR_WIDTH_M * math.cos(
        math.radians(NOMINAL_TILT_DEG)
    )
    row_pitch = horizontal_footprint + FRONT_CLEAR_GAP_M
    gcr = COLLECTOR_WIDTH_M / row_pitch

    heights_cm = [
        float(row["module_edge_height_cm"])
        for row in rsi_rows
        if row["module_edge_height_cm"] != ""
    ]
    module_height_m = round(sum(heights_cm) / len(heights_cm) / 100.0, 4)

    return {
        "inputs": {
            "collector_width_m": COLLECTOR_WIDTH_M,
            "front_clear_gap_m": FRONT_CLEAR_GAP_M,
            "nominal_tilt_deg": NOMINAL_TILT_DEG,
            "survey_measured_tilt_deg_range": [9.0, 10.0],
        },
        "formula": (
            "row_pitch_m = collector_width_m * cos(tilt) + front_clear_gap_m; "
            "gcr = collector_width_m / row_pitch_m"
        ),
        "row_pitch_m": round(row_pitch, 4),
        "gcr": round(gcr, 4),
        "gcr_at_9deg_tilt": round(
            COLLECTOR_WIDTH_M
            / (COLLECTOR_WIDTH_M * math.cos(math.radians(9.0)) + FRONT_CLEAR_GAP_M),
            4,
        ),
        "rejected_interpretation": (
            "Reading the 2.50 m front spacing as centre-to-centre pitch would "
            "give gcr = 2.0 (> 1), which is physically impossible; the survey "
            "value is therefore interpreted as the clear gap between rows."
        ),
        "module_height_m": {
            "value": module_height_m,
            "method": (
                "mean of the surveyed module-edge heights at the RSI mounting "
                "points (pyranometer height + 29 cm gap equals the module rear "
                "surface at that point)"
            ),
            "sample_count": len(heights_cm),
            "range_m": [
                round(min(heights_cm) / 100.0, 4),
                round(max(heights_cm) / 100.0, 4),
            ],
        },
    }


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    manifest = build_source_manifest()
    rsi_rows = build_rsi_survey()
    geometry_rows = build_row_geometry()
    albedo_rows, albedo_summary = build_albedo_monthly()
    derivation = derive_geometry(rsi_rows)

    write_csv(OUT_DIR / "source_manifest.csv", manifest)
    write_csv(OUT_DIR / "rsi_mounting_survey.csv", rsi_rows)
    write_csv(OUT_DIR / "row_geometry_survey.csv", geometry_rows)
    write_csv(OUT_DIR / "albedo_tmy_monthly.csv", albedo_rows)

    audit = {
        "task": "S0-4 site metadata audit",
        "derived_geometry": derivation,
        "albedo_tmy_summary": albedo_summary,
        "rsi_sensor_count": len(rsi_rows),
        "rsi_sensors_without_height_record": [
            row["sensor_id"] for row in rsi_rows if row["pyranometer_height_cm"] == ""
        ],
        "source_files": [row["relative_path"] for row in manifest],
    }
    (OUT_DIR / "site_metadata_audit.json").write_text(
        json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"wrote {len(manifest)} source rows, {len(rsi_rows)} RSI rows, "
          f"{len(geometry_rows)} geometry rows, {len(albedo_rows)} albedo rows")
    print(json.dumps(derivation, indent=2)[:400])


if __name__ == "__main__":
    main()
