"""Clear-sky index and rule-based cloud-regime labelling for the S0-5 audit.

The clear-sky model is pvlib Ineichen with the bundled Linke turbidity
climatology (ML-004 default; the haze caveat from PRD 16.6 applies and is
recorded in the audit report). ``k_c`` follows the PRD contract: NaN wherever
``GHI_cs`` is below ``kc_valid_min_wm2`` (twilight singularity guard), no
clipping of physically real enhancement below ``kc_max``, and every clip at
``kc_max`` is counted rather than silently discarded.

Timestamps are naive historian stamps interpreted under the configured local
timezone assumption; the historian timezone confirmation is still open (S0-2)
and that caveat must accompany every consumer of these numbers.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


REGIME_RULES: dict[str, object] = {
    "version": "s0-5-audit-v1",
    "labels": [
        "CLEAR",
        "MOSTLY_CLEAR",
        "PARTLY_CLOUDY",
        "OVERCAST",
        "HIGHLY_VARIABLE",
        "UNKNOWN",
    ],
    "kc_thresholds": {
        "clear_min": 0.90,
        "mostly_clear_min": 0.75,
        "partly_cloudy_min": 0.45,
    },
    "variability": {
        "window_minutes": 30,
        "min_periods": 15,
        "std_threshold": 0.15,
    },
    "notes": (
        "Deterministic audit-grade rule set (FR-026 MVP). Labels derive only "
        "from kc and its trailing-window variability; RAIN_DEGRADED requires "
        "rain-gauge semantics that are not audited in S0-5 and is therefore "
        "not emitted. The trailing window keeps the labelling backward-only."
    ),
}


def minute_ghi_zoh(
    events: pd.DataFrame,
    *,
    grid: pd.DatetimeIndex,
    zoh_staleness: pd.Timedelta,
) -> pd.Series:
    """Backward-only zero-order-hold of event values onto the minute grid."""

    if len(grid) == 0:
        raise ValueError("audit grid is empty")
    step = grid[1] - grid[0] if len(grid) > 1 else pd.Timedelta("1min")
    ordered = events.sort_values("event_time", kind="stable")
    event_times = ordered["event_time"].to_numpy(dtype="datetime64[ns]")
    event_values = ordered["value"].to_numpy(dtype="float64")
    grid_values = grid.values
    bin_end = grid_values + step.to_timedelta64()
    last_index = np.searchsorted(event_times, bin_end, side="left") - 1
    has_last = last_index >= 0
    last_event = event_times[np.maximum(last_index, 0)]
    fresh = has_last & (last_event + zoh_staleness.to_timedelta64() > grid_values)
    values = np.where(fresh, event_values[np.maximum(last_index, 0)], np.nan)
    return pd.Series(values, index=grid, name="ghi")


def clearsky_ghi(
    grid: pd.DatetimeIndex,
    *,
    latitude_deg: float,
    longitude_deg: float,
    altitude_m: float,
    local_timezone: str,
) -> pd.Series:
    """Ineichen clear-sky GHI for a naive local-time grid (ML-004 default)."""

    import pvlib

    location = pvlib.location.Location(
        latitude_deg, longitude_deg, tz=local_timezone, altitude=altitude_m
    )
    localized = grid.tz_localize(local_timezone)
    clearsky = location.get_clearsky(localized, model="ineichen")
    return pd.Series(
        clearsky["ghi"].to_numpy(dtype="float64"), index=grid, name="ghi_cs"
    )


def compute_kc(
    ghi: pd.Series,
    ghi_cs: pd.Series,
    *,
    kc_valid_min_wm2: float,
    kc_max: float,
) -> pd.DataFrame:
    """PRD-contract clear-sky index with twilight and outlier guards."""

    valid = ghi.notna() & (ghi_cs >= kc_valid_min_wm2)
    kc_raw = pd.Series(np.nan, index=ghi.index, dtype="float64")
    kc_raw[valid] = ghi[valid] / ghi_cs[valid]
    clipped = valid & (kc_raw > kc_max)
    kc = kc_raw.where(~clipped, kc_max)
    return pd.DataFrame(
        {
            "ghi": ghi,
            "ghi_cs": ghi_cs,
            "kc": kc,
            "kc_valid": valid,
            "kc_clipped": clipped,
        }
    )


def label_regimes(frame: pd.DataFrame) -> pd.Series:
    """Deterministic backward-only regime labels from kc and its variability."""

    thresholds = REGIME_RULES["kc_thresholds"]
    variability = REGIME_RULES["variability"]
    kc = frame["kc"]
    rolling_std = kc.rolling(
        window=int(variability["window_minutes"]),
        min_periods=int(variability["min_periods"]),
    ).std()
    labels = pd.Series("UNKNOWN", index=frame.index, dtype="object")
    known = kc.notna()
    calm_or_unmeasured = ~(rolling_std >= float(variability["std_threshold"]))
    labels[known & ~calm_or_unmeasured] = "HIGHLY_VARIABLE"
    steady = known & calm_or_unmeasured
    labels[steady & (kc >= float(thresholds["clear_min"]))] = "CLEAR"
    labels[
        steady
        & (kc >= float(thresholds["mostly_clear_min"]))
        & (kc < float(thresholds["clear_min"]))
    ] = "MOSTLY_CLEAR"
    labels[
        steady
        & (kc >= float(thresholds["partly_cloudy_min"]))
        & (kc < float(thresholds["mostly_clear_min"]))
    ] = "PARTLY_CLOUDY"
    labels[steady & (kc < float(thresholds["partly_cloudy_min"]))] = "OVERCAST"
    return labels


def kc_monthly_summary(frame: pd.DataFrame) -> pd.DataFrame:
    """Monthly kc distribution statistics over valid minutes only."""

    valid = frame[frame["kc_valid"] & frame["kc"].notna()]
    rows: list[dict[str, object]] = []
    months = valid.index.strftime("%Y-%m")
    for month, group in valid.groupby(months, sort=True):
        kc = group["kc"]
        delta = kc.diff().abs().dropna()
        rows.append(
            {
                "month": month,
                "n_valid_minutes": int(len(kc)),
                "kc_mean": float(kc.mean()),
                "kc_std": float(kc.std()) if len(kc) > 1 else np.nan,
                "kc_p10": float(kc.quantile(0.10)),
                "kc_p25": float(kc.quantile(0.25)),
                "kc_p50": float(kc.quantile(0.50)),
                "kc_p75": float(kc.quantile(0.75)),
                "kc_p90": float(kc.quantile(0.90)),
                "frac_kc_gt_1": float((kc > 1.0).mean()),
                "kc_clip_count": int(group["kc_clipped"].sum()),
                "mean_abs_delta_kc": (
                    float(delta.mean()) if len(delta) else np.nan
                ),
            }
        )
    return pd.DataFrame(rows)


def regime_monthly_distribution(labels: pd.Series) -> pd.DataFrame:
    """Monthly fraction of minutes per regime label."""

    rows: list[dict[str, object]] = []
    months = labels.index.strftime("%Y-%m")
    for month, group in labels.groupby(months, sort=True):
        total = int(len(group))
        row: dict[str, object] = {"month": month, "n_minutes": total}
        for label in REGIME_RULES["labels"]:
            row[f"frac_{label.lower()}"] = (
                float((group == label).sum() / total) if total else 0.0
            )
        rows.append(row)
    return pd.DataFrame(rows)
