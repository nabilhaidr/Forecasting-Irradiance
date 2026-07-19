from __future__ import annotations

import pandas as pd

from src.characterisation.data_audit import (
    crosscheck_operator_leads,
    daily_coverage_summary,
    detect_outage_candidates,
    gap_profile,
    monthly_coverage_summary,
)


def _events(rows: list[tuple[str, str, str]]) -> pd.DataFrame:
    frame = pd.DataFrame(rows, columns=["emi", "channel_key", "event_time"])
    frame["event_time"] = pd.to_datetime(frame["event_time"])
    return frame


def _grid_and_daylight(
    start: str, end: str, daylight_start: str = "06:00", daylight_end: str = "18:00"
) -> tuple[pd.DatetimeIndex, pd.Series]:
    grid = pd.date_range(start, end, freq="1min", inclusive="left")
    times = pd.Series(grid, index=grid)
    daylight = (times.dt.strftime("%H:%M") >= daylight_start) & (
        times.dt.strftime("%H:%M") < daylight_end
    )
    return grid, daylight


def test_daily_coverage_summary_counts_strict_and_zoh_minutes() -> None:
    grid, daylight = _grid_and_daylight("2026-06-01", "2026-06-02")
    events = _events(
        [
            ("EMI01", "GHI", "2026-06-01 06:00:30"),
            ("EMI01", "GHI", "2026-06-01 06:05:10"),
        ]
    )

    daily = daily_coverage_summary(
        events, grid=grid, daylight=daylight, zoh_staleness=pd.Timedelta("15min")
    )

    assert daily[["emi", "channel_key"]].drop_duplicates().to_dict("records") == [
        {"emi": "EMI01", "channel_key": "GHI"}
    ]
    row = daily.iloc[0]
    assert row["date"] == pd.Timestamp("2026-06-01").date()
    assert row["daylight_minutes"] == 720
    # events land in the 06:00 and 06:05 minute bins
    assert row["daylight_minutes_with_event"] == 2
    # ZOH hold covers 06:00 .. 06:20 (staleness 15 min from the 06:05 event)
    assert row["daylight_minutes_zoh"] == 21
    assert row["daylight_coverage_zoh"] == 21 / 720


def test_daily_coverage_summary_all_day_and_absent_days() -> None:
    grid, daylight = _grid_and_daylight("2026-06-01", "2026-06-03")
    events = _events([("EMI02", "POA", "2026-06-01 12:00:00")])

    daily = daily_coverage_summary(
        events, grid=grid, daylight=daylight, zoh_staleness=pd.Timedelta("15min")
    )

    assert len(daily) == 2  # both grid days reported, including the empty one
    empty_day = daily[daily["date"] == pd.Timestamp("2026-06-02").date()].iloc[0]
    assert empty_day["daylight_minutes_with_event"] == 0
    assert empty_day["daylight_minutes_zoh"] == 0
    assert empty_day["all_day_minutes_with_event"] == 0


def test_gap_profile_buckets_and_percentiles() -> None:
    events = _events(
        [
            ("EMI01", "GHI", "2026-06-01 06:00:00"),
            ("EMI01", "GHI", "2026-06-01 06:00:10"),
            ("EMI01", "GHI", "2026-06-01 06:10:10"),
            ("EMI01", "GHI", "2026-06-03 06:10:10"),
        ]
    )

    profile = gap_profile(events)

    assert len(profile) == 1
    row = profile.iloc[0]
    assert row["event_count"] == 4
    assert row["max_gap_s"] == 2 * 24 * 3600.0
    assert row["gaps_gt_5min"] == 2
    assert row["gaps_gt_30min"] == 1
    assert row["gaps_gt_6h"] == 1
    assert row["gaps_gt_3d"] == 0


def test_detect_outage_candidates_merges_consecutive_zero_days() -> None:
    daily = pd.DataFrame(
        {
            "emi": ["EMI03"] * 5,
            "channel_key": ["GHI"] * 5,
            "date": [
                pd.Timestamp("2025-03-01").date(),
                pd.Timestamp("2025-03-02").date(),
                pd.Timestamp("2025-03-03").date(),
                pd.Timestamp("2025-03-04").date(),
                pd.Timestamp("2025-03-05").date(),
            ],
            "daylight_minutes": [720] * 5,
            "daylight_minutes_zoh": [500, 0, 0, 0, 400],
        }
    )

    outages = detect_outage_candidates(daily, min_days=2)

    assert outages.to_dict("records") == [
        {
            "emi": "EMI03",
            "channel_key": "GHI",
            "start_date": pd.Timestamp("2025-03-02").date(),
            "end_date": pd.Timestamp("2025-03-04").date(),
            "n_days": 3,
        }
    ]


def test_crosscheck_operator_leads_reports_overlap() -> None:
    outages = pd.DataFrame(
        {
            "emi": ["EMI03"],
            "channel_key": ["GHI"],
            "start_date": [pd.Timestamp("2025-03-06").date()],
            "end_date": [pd.Timestamp("2025-06-24").date()],
            "n_days": [111],
        }
    )
    leads = pd.DataFrame(
        {
            "lead_id": ["ws3-ghi-outage", "ws4-rsi2-removal"],
            "emi": ["EMI03", "EMI04"],
            "channel_key": ["GHI", "RSI_02"],
            "reported_start": ["2025-03-01", "2026-01-05"],
            "reported_end": ["2025-06-25", ""],
        }
    )

    crosschecked = crosscheck_operator_leads(outages, leads)

    ws3 = crosschecked[crosschecked["lead_id"] == "ws3-ghi-outage"].iloc[0]
    assert ws3["status"] == "corroborated"
    assert ws3["measured_start"] == pd.Timestamp("2025-03-06").date()
    assert ws3["measured_end"] == pd.Timestamp("2025-06-24").date()
    ws4 = crosschecked[crosschecked["lead_id"] == "ws4-rsi2-removal"].iloc[0]
    assert ws4["status"] == "not_found"


def test_crosscheck_operator_leads_flags_window_start_absence() -> None:
    outages = pd.DataFrame(
        {
            "emi": ["EMI03", "EMI04"],
            "channel_key": ["RSI_01", "RSI_02"],
            "start_date": [
                pd.Timestamp("2025-12-01").date(),
                pd.Timestamp("2026-01-06").date(),
            ],
            "end_date": [
                pd.Timestamp("2026-06-30").date(),
                pd.Timestamp("2026-06-30").date(),
            ],
            "n_days": [212, 176],
        }
    )
    leads = pd.DataFrame(
        {
            "lead_id": ["ws3-rsi1-removal", "ws4-rsi2-removal"],
            "emi": ["EMI03", "EMI04"],
            "channel_key": ["RSI_01", "RSI_02"],
            "reported_start": ["2025-06-30", "2026-01-05"],
            "reported_end": ["", ""],
        }
    )

    crosschecked = crosscheck_operator_leads(
        outages, leads, data_window_start=pd.Timestamp("2025-12-01").date()
    )

    # RSI_01 zero-run begins exactly at the data window start -> pre-window
    # absence, not a measured transition to the reported date.
    pre = crosschecked[crosschecked["lead_id"] == "ws3-rsi1-removal"].iloc[0]
    assert pre["status"] == "absent_from_window_start"
    # RSI_02 transitions to zero within the window -> genuine measurement.
    transition = crosschecked[crosschecked["lead_id"] == "ws4-rsi2-removal"].iloc[0]
    assert transition["status"] == "corroborated"


def test_monthly_coverage_summary_aggregates_daily() -> None:
    daily = pd.DataFrame(
        {
            "emi": ["EMI01", "EMI01", "EMI01"],
            "channel_key": ["GHI", "GHI", "GHI"],
            "date": [
                pd.Timestamp("2026-05-31").date(),
                pd.Timestamp("2026-06-01").date(),
                pd.Timestamp("2026-06-02").date(),
            ],
            "daylight_minutes": [720, 720, 720],
            "daylight_minutes_with_event": [700, 0, 360],
            "daylight_minutes_zoh": [710, 0, 720],
            "all_day_minutes_with_event": [800, 0, 400],
        }
    )

    monthly = monthly_coverage_summary(daily)

    june = monthly[monthly["month"] == "2026-06"].iloc[0]
    assert june["days_in_data"] == 2
    assert june["days_with_any_event"] == 1
    assert june["daylight_coverage_zoh"] == (0 + 720) / (720 + 720)
    may = monthly[monthly["month"] == "2026-05"].iloc[0]
    assert may["daylight_coverage_strict"] == 700 / 720
