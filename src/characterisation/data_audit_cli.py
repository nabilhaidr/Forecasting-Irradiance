"""Composition point and CLI for the S0-5 historical coverage audit.

Two scopes:

* ``irradiance`` derives, from the raw instantaneous XLSX history (and an
  optional raw COV cross-check), the per-channel minute-grid coverage timeline,
  gap profile, outage candidates, empirical monthly ``k_c`` distribution, and
  rule-based cloud-regime distribution. Seasons are read from the data's own
  regime distribution, never from an assumed monsoon calendar (ML-002).
* ``operational`` extracts maintenance, curtailment, and outage/limitation
  periods from the operator workbooks as corroboration.

All timestamps are the historian's naive local stamps. The historian timezone
confirmation is still open (S0-2); every artifact and the run manifest carry
that caveat explicitly rather than waiting for it to close.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml

from .cov_ingest import CovInputError, ingest_cov_directory
from .coverage_xlsx import ingest_coverage_xlsx
from .data_audit import (
    crosscheck_operator_leads,
    daily_coverage_summary,
    detect_outage_candidates,
    gap_profile,
    monthly_coverage_summary,
)
from .kc_regime import (
    REGIME_RULES,
    clearsky_ghi,
    compute_kc,
    kc_monthly_summary,
    label_regimes,
    minute_ghi_zoh,
    regime_monthly_distribution,
)
from .operational_periods import (
    file_provenance,
    parse_curtailment_daily,
    parse_dcm_outage_limitation,
    parse_maintenance_records,
)


TIMEZONE_CAVEAT = (
    "historian timezone/clock offset is unconfirmed (S0-2 open item); every "
    "local-time claim below - daylight hours, months, seasonal regime - is "
    "provisional under the Asia/Makassar (WITA) working assumption."
)
ZOH_STALENESS = pd.Timedelta("15min")
KC_VALID_MIN_WM2 = 20.0
KC_MAX = 1.5
OUTAGE_MIN_DAYS = 3

# Operator-reported channel leads, corrected 2026-07-18 (see
# configs/site_plts-ikn.yaml operational_notes and RSI status_note fields).
# EMI<->WS mapping follows the S0-3 WS_TO_LOCATION hypothesis (still assumed).
OPERATOR_LEADS = pd.DataFrame(
    [
        {
            "lead_id": "ws3-ghi-outage",
            "emi": "EMI03",
            "channel_key": "GHI",
            "reported_start": "2025-03-01",
            "reported_end": "2025-06-25",
            "description": "WS-3 GHI down March 2025, normal since 2025-06-25",
        },
        {
            "lead_id": "ws3-rsi1-removal",
            "emi": "EMI03",
            "channel_key": "RSI_01",
            "reported_start": "2025-06-30",
            "reported_end": "",
            "description": "RSI WS3.1 removed 2025-06-30",
        },
        {
            "lead_id": "ws3-rsi2-removal",
            "emi": "EMI03",
            "channel_key": "RSI_02",
            "reported_start": "2025-06-30",
            "reported_end": "",
            "description": "RSI WS3.2 removed 2025-06-30",
        },
        {
            "lead_id": "ws3-rsi3-removal",
            "emi": "EMI03",
            "channel_key": "RSI_03",
            "reported_start": "2025-06-30",
            "reported_end": "",
            "description": "RSI WS3.3 removed 2025-06-30",
        },
        {
            "lead_id": "ws4-rsi1-removal",
            "emi": "EMI04",
            "channel_key": "RSI_01",
            "reported_start": "2025-09-01",
            "reported_end": "",
            "description": "RSI WS4.1 removed 2025-09-01",
        },
        {
            "lead_id": "ws4-rsi2-removal",
            "emi": "EMI04",
            "channel_key": "RSI_02",
            "reported_start": "2026-01-05",
            "reported_end": "",
            "description": "RSI WS4.2 removed 2026-01-05",
        },
    ]
)


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, lineterminator="\n", float_format="%.12g")


def _write_json(value: object, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest(paths: dict[str, Path], extra: dict[str, object]) -> dict[str, object]:
    return {
        "artifact_sha256": {
            name: _sha256(path) for name, path in sorted(paths.items())
        },
        "timezone_caveat": TIMEZONE_CAVEAT,
        **extra,
    }


def _read_site(site_config_path: Path) -> dict[str, object]:
    config = yaml.safe_load(Path(site_config_path).read_text(encoding="utf-8"))
    if not isinstance(config, dict) or not isinstance(config.get("site"), dict):
        raise CovInputError("site config must contain a site mapping")
    site = config["site"]
    for key in ("latitude_deg", "longitude_deg", "timezone", "canonical_freq"):
        if site.get(key) in (None, ""):
            raise CovInputError(f"site config missing required value: {key}")
    return site


def _build_grid(events: pd.DataFrame, freq: str) -> pd.DatetimeIndex:
    start = events["event_time"].min().normalize()
    end = events["event_time"].max().normalize() + pd.Timedelta(days=1)
    return pd.date_range(start, end, freq=freq, inclusive="left")


def _daylight_mask(grid: pd.DatetimeIndex, site: dict[str, object]) -> pd.Series:
    import pvlib

    localized = grid.tz_localize(str(site["timezone"]))
    solpos = pvlib.solarposition.get_solarposition(
        localized,
        latitude=float(site["latitude_deg"]),
        longitude=float(site["longitude_deg"]),
        altitude=float(site.get("elevation_m") or 0.0),
    )
    daylight = solpos["apparent_elevation"].to_numpy() > 0.0
    return pd.Series(daylight, index=grid)


def run_irradiance_audit(
    *,
    xlsx_root: Path,
    cov_dir: Path | None,
    site_config_path: Path,
    output_dir: Path,
) -> dict[str, object]:
    """Derive coverage, gaps, outages, and empirical kc/regime from history."""

    site = _read_site(Path(site_config_path))
    freq = str(site["canonical_freq"])
    ingestion = ingest_coverage_xlsx(Path(xlsx_root))
    events = ingestion.events
    if events.empty:
        raise CovInputError("no instantaneous XLSX events found for the audit")

    grid = _build_grid(events, freq)
    daylight = _daylight_mask(grid, site)

    daily = daily_coverage_summary(
        events, grid=grid, daylight=daylight, zoh_staleness=ZOH_STALENESS
    )
    monthly = monthly_coverage_summary(daily)
    gaps = gap_profile(events)
    outages = detect_outage_candidates(daily, min_days=OUTAGE_MIN_DAYS)
    data_window_start = events["event_time"].min().normalize().date()
    crosscheck = crosscheck_operator_leads(
        outages, OPERATOR_LEADS, data_window_start=data_window_start
    )

    kc_frames: list[pd.DataFrame] = []
    regime_frames: list[pd.DataFrame] = []
    ghi_events = events[events["channel_key"] == "GHI"]
    ghi_cs = clearsky_ghi(
        grid,
        latitude_deg=float(site["latitude_deg"]),
        longitude_deg=float(site["longitude_deg"]),
        altitude_m=float(site.get("elevation_m") or 0.0),
        local_timezone=str(site["timezone"]),
    )
    for emi, group in ghi_events.groupby("emi", sort=True, observed=True):
        ghi = minute_ghi_zoh(
            group[["event_time", "value"]], grid=grid, zoh_staleness=ZOH_STALENESS
        )
        kc_frame = compute_kc(
            ghi, ghi_cs, kc_valid_min_wm2=KC_VALID_MIN_WM2, kc_max=KC_MAX
        )
        labels = label_regimes(kc_frame)
        kc_month = kc_monthly_summary(kc_frame)
        kc_month.insert(0, "emi", emi)
        kc_frames.append(kc_month)
        # The cloud-regime distribution is only meaningful over daylight minutes;
        # normalising over the full 24 h buries it under a night-time UNKNOWN mass.
        daylight_labels = labels[daylight.to_numpy()]
        regime_month = regime_monthly_distribution(daylight_labels)
        regime_month.insert(0, "emi", emi)
        regime_frames.append(regime_month)

    kc_monthly = (
        pd.concat(kc_frames, ignore_index=True) if kc_frames else pd.DataFrame()
    )
    regime_monthly = (
        pd.concat(regime_frames, ignore_index=True)
        if regime_frames
        else pd.DataFrame()
    )

    cov_crosscheck = pd.DataFrame()
    cov_zip_count = 0
    if cov_dir is not None:
        cov = ingest_cov_directory(Path(cov_dir))
        cov_zip_count = int(len(cov.source_manifest))
        cov_events = cov.events[cov.events["channel_group"].notna()]
        cov_crosscheck = (
            cov_events.groupby(["emi", "channel_group"], observed=True)
            .size()
            .reset_index(name="cov_event_count")
            .sort_values(["emi", "channel_group"], ignore_index=True)
        )

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {
        "source_manifest.csv": output_dir / "source_manifest.csv",
        "coverage_daily.csv": output_dir / "coverage_daily.csv",
        "coverage_monthly.csv": output_dir / "coverage_monthly.csv",
        "gap_profile.csv": output_dir / "gap_profile.csv",
        "kc_monthly.csv": output_dir / "kc_monthly.csv",
        "regime_monthly.csv": output_dir / "regime_monthly.csv",
        "outage_candidates.csv": output_dir / "outage_candidates.csv",
        "operator_lead_crosscheck.csv": output_dir / "operator_lead_crosscheck.csv",
        "regime_rules.json": output_dir / "regime_rules.json",
    }
    _write_csv(ingestion.source_manifest, paths["source_manifest.csv"])
    _write_csv(daily, paths["coverage_daily.csv"])
    _write_csv(monthly, paths["coverage_monthly.csv"])
    _write_csv(gaps, paths["gap_profile.csv"])
    _write_csv(kc_monthly, paths["kc_monthly.csv"])
    _write_csv(regime_monthly, paths["regime_monthly.csv"])
    _write_csv(outages, paths["outage_candidates.csv"])
    _write_csv(crosscheck, paths["operator_lead_crosscheck.csv"])
    _write_json(REGIME_RULES, paths["regime_rules.json"])
    if not cov_crosscheck.empty:
        paths["cov_channel_crosscheck.csv"] = (
            output_dir / "cov_channel_crosscheck.csv"
        )
        _write_csv(cov_crosscheck, paths["cov_channel_crosscheck.csv"])

    figure_paths = _write_irradiance_figures(
        monthly, kc_monthly, regime_monthly, output_dir
    )
    paths.update(figure_paths)

    coverage_start = str(events["event_time"].min())
    coverage_end = str(events["event_time"].max())
    manifest_extra = {
        "coverage_start": coverage_start,
        "coverage_end": coverage_end,
        "xlsx_file_count": int(len(ingestion.source_manifest)),
        "cov_zip_count": cov_zip_count,
        "channels": sorted(events["channel_key"].astype(str).unique()),
        "months_in_data": sorted(monthly["month"].astype(str).unique()),
        "outage_candidate_count": int(len(outages)),
        "zoh_staleness_minutes": int(ZOH_STALENESS.total_seconds() // 60),
        "kc_valid_min_wm2": KC_VALID_MIN_WM2,
        "kc_max": KC_MAX,
        "clearsky_model": "pvlib_ineichen_linke_climatology",
        "regime_rules_version": REGIME_RULES["version"],
        "regime_distribution_scope": "daylight_minutes_only",
        "data_window_start": str(data_window_start),
        "xlsx_strict_error_count": len(ingestion.strict_errors),
    }
    manifest_path = output_dir / "run_manifest.json"
    _write_json(_manifest(paths, manifest_extra), manifest_path)
    return {
        "scope": "irradiance",
        "coverage_start": coverage_start,
        "coverage_end": coverage_end,
        "months": manifest_extra["months_in_data"],
        "outage_candidate_count": int(len(outages)),
        "manifest_sha256": _sha256(manifest_path),
    }


def _write_irradiance_figures(
    monthly: pd.DataFrame,
    kc_monthly: pd.DataFrame,
    regime_monthly: pd.DataFrame,
    output_dir: Path,
) -> dict[str, Path]:
    figures_dir = output_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}

    coverage_path = figures_dir / "coverage_timeline.png"
    if not monthly.empty:
        pivot = monthly.assign(
            row=monthly["emi"].astype(str) + ":" + monthly["channel_key"].astype(str)
        ).pivot_table(index="row", columns="month", values="daylight_coverage_zoh")
        figure, axis = plt.subplots(
            figsize=(
                max(6, 0.5 * pivot.shape[1] + 3),
                max(3, 0.35 * pivot.shape[0] + 2),
            )
        )
        image = axis.imshow(
            pivot.to_numpy(), aspect="auto", vmin=0.0, vmax=1.0, cmap="viridis"
        )
        axis.set_xticks(range(pivot.shape[1]))
        axis.set_xticklabels(pivot.columns, rotation=90, fontsize="small")
        axis.set_yticks(range(pivot.shape[0]))
        axis.set_yticklabels(pivot.index, fontsize="small")
        axis.set_title("Daylight ZOH coverage by channel and month (provisional WITA)")
        figure.colorbar(image, ax=axis, label="coverage fraction")
        figure.tight_layout()
        figure.savefig(coverage_path, dpi=150)
        plt.close(figure)
    else:
        _blank_figure(coverage_path, "No coverage")
    paths["figures/coverage_timeline.png"] = coverage_path

    kc_path = figures_dir / "kc_monthly.png"
    if not kc_monthly.empty:
        figure, axis = plt.subplots(
            figsize=(max(6, 0.4 * kc_monthly["month"].nunique() + 3), 4)
        )
        for emi, group in kc_monthly.groupby("emi", sort=True):
            group = group.sort_values("month")
            axis.plot(group["month"], group["kc_p50"], marker="o", label=f"{emi} p50")
            axis.fill_between(
                group["month"], group["kc_p10"], group["kc_p90"], alpha=0.15
            )
        axis.set_ylabel("clear-sky index k_c")
        axis.set_title("Empirical monthly k_c (p10-p50-p90) - measured, not calendar")
        axis.tick_params(axis="x", rotation=90)
        axis.legend(fontsize="small")
        axis.grid(alpha=0.3)
        figure.tight_layout()
        figure.savefig(kc_path, dpi=150)
        plt.close(figure)
    else:
        _blank_figure(kc_path, "No kc")
    paths["figures/kc_monthly.png"] = kc_path

    regime_path = figures_dir / "regime_monthly.png"
    if not regime_monthly.empty:
        first_emi = sorted(regime_monthly["emi"].astype(str).unique())[0]
        subset = regime_monthly[
            regime_monthly["emi"].astype(str) == first_emi
        ].sort_values("month")
        figure, axis = plt.subplots(figsize=(max(6, 0.4 * len(subset) + 3), 4))
        bottom = np.zeros(len(subset))
        for label in REGIME_RULES["labels"]:
            column = f"frac_{label.lower()}"
            if column in subset:
                axis.bar(subset["month"], subset[column], bottom=bottom, label=label)
                bottom = bottom + subset[column].to_numpy()
        axis.set_ylabel("fraction of minutes")
        axis.set_title(f"Monthly cloud-regime distribution ({first_emi}) - data-derived")
        axis.tick_params(axis="x", rotation=90)
        axis.legend(fontsize="small", ncol=2)
        figure.tight_layout()
        figure.savefig(regime_path, dpi=150)
        plt.close(figure)
    else:
        _blank_figure(regime_path, "No regime")
    paths["figures/regime_monthly.png"] = regime_path
    return paths


def _blank_figure(path: Path, message: str) -> None:
    figure, axis = plt.subplots(figsize=(6, 3))
    axis.text(0.5, 0.5, message, ha="center", va="center")
    axis.set_axis_off()
    figure.savefig(path, dpi=150)
    plt.close(figure)


def run_operational_audit(
    *, spec_raw_dir: Path, output_dir: Path
) -> dict[str, object]:
    """Extract maintenance, curtailment, and outage periods from workbooks."""

    spec_raw_dir = Path(spec_raw_dir)
    maintenance_path = spec_raw_dir / "Maintenance Record PLTS IKN 50 MW.xlsx"
    generation_path = spec_raw_dir / "IKN Generation.xlsx"
    dcm_path = spec_raw_dir / "DCM Manual Calucation Rekon PLTS IKN.xlsx"

    provenance_rows: list[dict[str, object]] = []

    maintenance = pd.DataFrame()
    if maintenance_path.is_file():
        maintenance = parse_maintenance_records(maintenance_path)
        provenance_rows.append(
            {"role": "maintenance", **file_provenance(maintenance_path)}
        )

    curtailment = pd.DataFrame()
    if generation_path.is_file():
        frames = []
        for sheet in ("Detail2", "Sheet2", "Detail3"):
            try:
                frames.append(parse_curtailment_daily(generation_path, sheet=sheet))
            except (KeyError, ValueError):
                continue
        if frames:
            curtailment = (
                pd.concat(frames, ignore_index=True)
                .drop_duplicates(subset=["date"])
                .sort_values("date", ignore_index=True)
            )
        provenance_rows.append(
            {"role": "generation", **file_provenance(generation_path)}
        )

    dcm = pd.DataFrame()
    if dcm_path.is_file():
        import openpyxl

        workbook = openpyxl.load_workbook(dcm_path, read_only=True, data_only=True)
        sheet_names = list(workbook.sheetnames)
        workbook.close()
        frames = []
        for sheet in sheet_names:
            parsed = parse_dcm_outage_limitation(dcm_path, sheet=sheet)
            if not parsed.empty:
                frames.append(parsed)
        if frames:
            dcm = pd.concat(frames, ignore_index=True)
        provenance_rows.append({"role": "dcm", **file_provenance(dcm_path)})

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    provenance = pd.DataFrame(
        provenance_rows, columns=["role", "source_name", "byte_size", "sha256"]
    )
    paths = {
        "maintenance_periods.csv": output_dir / "maintenance_periods.csv",
        "curtailment_periods.csv": output_dir / "curtailment_periods.csv",
        "dcm_outage_limitation.csv": output_dir / "dcm_outage_limitation.csv",
        "operational_source_manifest.csv": (
            output_dir / "operational_source_manifest.csv"
        ),
    }
    _write_csv(maintenance, paths["maintenance_periods.csv"])
    _write_csv(curtailment, paths["curtailment_periods.csv"])
    _write_csv(dcm, paths["dcm_outage_limitation.csv"])
    _write_csv(provenance, paths["operational_source_manifest.csv"])

    ws_maintenance = (
        int(maintenance["is_weather_station"].sum()) if not maintenance.empty else 0
    )
    manifest_extra = {
        "maintenance_row_count": int(len(maintenance)),
        "weather_station_maintenance_count": ws_maintenance,
        "curtailment_row_count": int(len(curtailment)),
        "dcm_interval_count": int(len(dcm)),
    }
    manifest_path = output_dir / "run_manifest.json"
    _write_json(_manifest(paths, manifest_extra), manifest_path)
    return {
        "scope": "operational",
        "manifest_sha256": _sha256(manifest_path),
        **manifest_extra,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the S0-5 historical coverage audit."
    )
    parser.add_argument("--scope", choices=("irradiance", "operational"), required=True)
    parser.add_argument("--xlsx-root", type=Path)
    parser.add_argument("--cov-dir", type=Path)
    parser.add_argument("--spec-raw-dir", type=Path)
    parser.add_argument("--site-config", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.scope == "irradiance":
        if args.xlsx_root is None or args.site_config is None:
            _parser().error("irradiance scope requires --xlsx-root and --site-config")
        summary = run_irradiance_audit(
            xlsx_root=args.xlsx_root,
            cov_dir=args.cov_dir,
            site_config_path=args.site_config,
            output_dir=args.output_dir,
        )
    else:
        if args.spec_raw_dir is None:
            _parser().error("operational scope requires --spec-raw-dir")
        summary = run_operational_audit(
            spec_raw_dir=args.spec_raw_dir, output_dir=args.output_dir
        )
    print(json.dumps(summary, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
