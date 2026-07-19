from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.characterisation.kc_regime import (
    REGIME_RULES,
    clearsky_ghi,
    compute_kc,
    kc_monthly_summary,
    label_regimes,
    minute_ghi_zoh,
    regime_monthly_distribution,
)


def test_minute_ghi_zoh_is_backward_only() -> None:
    grid = pd.date_range("2026-06-01 12:00", periods=20, freq="1min")
    events = pd.DataFrame(
        {
            "event_time": [pd.Timestamp("2026-06-01 12:00:30")],
            "value": [500.0],
        }
    )

    series = minute_ghi_zoh(events, grid=grid, zoh_staleness=pd.Timedelta("15min"))

    assert series.loc[pd.Timestamp("2026-06-01 12:00")] == 500.0
    assert series.loc[pd.Timestamp("2026-06-01 12:15")] == 500.0
    assert np.isnan(series.loc[pd.Timestamp("2026-06-01 12:16")])


def test_compute_kc_threshold_and_clip_guard() -> None:
    grid = pd.date_range("2026-06-01 12:00", periods=4, freq="1min")
    ghi = pd.Series([500.0, 15.0, 900.0, np.nan], index=grid)
    ghi_cs = pd.Series([1000.0, 10.0, 500.0, 800.0], index=grid)

    frame = compute_kc(ghi, ghi_cs, kc_valid_min_wm2=20.0, kc_max=1.5)

    assert frame.loc[grid[0], "kc"] == 0.5
    assert frame.loc[grid[0], "kc_valid"]
    # clear-sky below the validity floor -> NaN, not a huge ratio
    assert np.isnan(frame.loc[grid[1], "kc"])
    assert not frame.loc[grid[1], "kc_valid"]
    # 900/500 = 1.8 exceeds the outlier guard -> clipped to 1.5 and counted
    assert frame.loc[grid[2], "kc"] == 1.5
    assert frame.loc[grid[2], "kc_clipped"]
    assert np.isnan(frame.loc[grid[3], "kc"])


def test_label_regimes_rule_set() -> None:
    grid = pd.date_range("2026-06-01 10:00", periods=240, freq="1min")
    kc = pd.Series(0.95, index=grid)
    kc.iloc[60:120] = 0.5
    kc.iloc[120:180] = np.nan
    rng = np.arange(60)
    kc.iloc[180:240] = np.where(rng % 2 == 0, 0.2, 1.2)
    frame = pd.DataFrame({"kc": kc, "kc_valid": kc.notna()})

    labels = label_regimes(frame)

    assert labels.iloc[30] == "CLEAR"
    assert labels.iloc[110] == "PARTLY_CLOUDY"
    assert labels.iloc[150] == "UNKNOWN"
    assert labels.iloc[235] == "HIGHLY_VARIABLE"
    assert set(labels.unique()) <= set(REGIME_RULES["labels"])


def test_kc_monthly_summary_distribution() -> None:
    may = pd.date_range("2026-05-31 10:00", periods=60, freq="1min")
    june = pd.date_range("2026-06-01 10:00", periods=60, freq="1min")
    grid = may.append(june)
    kc = pd.Series([0.4] * 60 + [0.8] * 60, index=grid, dtype="float64")
    frame = pd.DataFrame(
        {"kc": kc, "kc_valid": True, "kc_clipped": False}
    )

    summary = kc_monthly_summary(frame)

    june_row = summary[summary["month"] == "2026-06"].iloc[0]
    assert june_row["n_valid_minutes"] == 60
    assert june_row["kc_p50"] == pytest.approx(0.8)
    assert june_row["frac_kc_gt_1"] == 0.0
    assert summary[summary["month"] == "2026-05"].iloc[0]["kc_mean"] == pytest.approx(
        0.4
    )


def test_regime_monthly_distribution_fractions() -> None:
    grid = pd.date_range("2026-06-01 10:00", periods=100, freq="1min")
    labels = pd.Series(["CLEAR"] * 50 + ["OVERCAST"] * 50, index=grid)

    distribution = regime_monthly_distribution(labels)

    row = distribution[distribution["month"] == "2026-06"].iloc[0]
    assert row["n_minutes"] == 100
    assert row["frac_clear"] == 0.5
    assert row["frac_overcast"] == 0.5
    assert row["frac_unknown"] == 0.0


def test_clearsky_ghi_site_sanity() -> None:
    grid = pd.date_range("2026-06-01 00:00", "2026-06-02 00:00", freq="30min")

    ghi_cs = clearsky_ghi(
        grid,
        latitude_deg=-0.9911713,
        longitude_deg=116.6381113,
        altitude_m=85.0,
        local_timezone="Asia/Makassar",
    )

    assert ghi_cs.index.equals(grid)
    assert ghi_cs.loc[pd.Timestamp("2026-06-01 12:00")] > 400.0
    assert ghi_cs.loc[pd.Timestamp("2026-06-01 00:00")] == 0.0
    assert (ghi_cs >= 0).all()
