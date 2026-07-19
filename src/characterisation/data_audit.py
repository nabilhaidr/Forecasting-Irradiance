"""S0-5 historical coverage audit: minute-grid coverage, gaps, and outages.

All computations are backward-only: a minute bin is covered strictly when an
event lands inside the bin, and covered in ZOH terms when the latest event at
or before the bin end is younger than the configured staleness. No future
information is consulted. Timestamps are the historian's naive local stamps;
the unresolved timezone caveat travels with every derived artifact.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


GAP_BUCKETS_S = (
    ("gaps_gt_5min", 300.0),
    ("gaps_gt_30min", 1800.0),
    ("gaps_gt_6h", 6 * 3600.0),
    ("gaps_gt_24h", 24 * 3600.0),
    ("gaps_gt_3d", 3 * 24 * 3600.0),
)


def daily_coverage_summary(
    events: pd.DataFrame,
    *,
    grid: pd.DatetimeIndex,
    daylight: pd.Series,
    zoh_staleness: pd.Timedelta,
) -> pd.DataFrame:
    """Per (emi, channel_key, day): strict and ZOH minute coverage counts."""

    if len(grid) == 0:
        raise ValueError("audit grid is empty")
    step = grid[1] - grid[0] if len(grid) > 1 else pd.Timedelta("1min")
    daylight_mask = daylight.reindex(grid).fillna(False).to_numpy(dtype=bool)
    grid_values = grid.values
    grid_days = grid.date
    day_frame = pd.DataFrame({"date": grid_days, "daylight": daylight_mask})
    per_day = day_frame.groupby("date", sort=True)["daylight"].agg(
        daylight_minutes="sum", all_day_minutes="count"
    )

    rows: list[dict[str, object]] = []
    for (emi, channel_key), group in events.groupby(
        ["emi", "channel_key"], sort=True, observed=True
    ):
        event_times = np.sort(group["event_time"].to_numpy(dtype="datetime64[ns]"))
        bin_end = grid_values + step.to_timedelta64()
        last_index = np.searchsorted(event_times, bin_end, side="left") - 1
        has_last = last_index >= 0
        last_event = event_times[np.maximum(last_index, 0)]
        zoh_covered = has_last & (
            last_event + zoh_staleness.to_timedelta64() > grid_values
        )
        event_bins = event_times.astype("datetime64[m]").astype("datetime64[ns]")
        strict_covered = np.isin(
            grid_values.astype("datetime64[m]").astype("datetime64[ns]"), event_bins
        )
        cover_frame = pd.DataFrame(
            {
                "date": grid_days,
                "strict_daylight": strict_covered & daylight_mask,
                "zoh_daylight": zoh_covered & daylight_mask,
                "strict_all_day": strict_covered,
                "zoh_all_day": zoh_covered,
            }
        )
        per_day_cover = cover_frame.groupby("date", sort=True).sum()
        for date, day_row in per_day_cover.iterrows():
            daylight_minutes = int(per_day.loc[date, "daylight_minutes"])
            strict_minutes = int(day_row["strict_daylight"])
            zoh_minutes = int(day_row["zoh_daylight"])
            rows.append(
                {
                    "emi": emi,
                    "channel_key": channel_key,
                    "date": date,
                    "daylight_minutes": daylight_minutes,
                    "daylight_minutes_with_event": strict_minutes,
                    "daylight_minutes_zoh": zoh_minutes,
                    "all_day_minutes_with_event": int(day_row["strict_all_day"]),
                    "all_day_minutes_zoh": int(day_row["zoh_all_day"]),
                    "daylight_coverage_strict": (
                        strict_minutes / daylight_minutes if daylight_minutes else 0.0
                    ),
                    "daylight_coverage_zoh": (
                        zoh_minutes / daylight_minutes if daylight_minutes else 0.0
                    ),
                }
            )
    return pd.DataFrame(rows)


def gap_profile(events: pd.DataFrame) -> pd.DataFrame:
    """Per (emi, channel_key): inter-event gap statistics and bucket counts."""

    rows: list[dict[str, object]] = []
    for (emi, channel_key), group in events.groupby(
        ["emi", "channel_key"], sort=True, observed=True
    ):
        event_times = np.unique(group["event_time"].to_numpy(dtype="datetime64[ns]"))
        gaps_s = (
            np.diff(event_times).astype("timedelta64[ns]").astype("int64") / 1e9
            if len(event_times) > 1
            else np.array([], dtype="float64")
        )
        row: dict[str, object] = {
            "emi": emi,
            "channel_key": channel_key,
            "event_count": int(len(event_times)),
            "first_event": pd.Timestamp(event_times[0]),
            "last_event": pd.Timestamp(event_times[-1]),
            "max_gap_s": float(gaps_s.max()) if gaps_s.size else np.nan,
            "interarrival_p50_s": (
                float(np.percentile(gaps_s, 50)) if gaps_s.size else np.nan
            ),
            "interarrival_p90_s": (
                float(np.percentile(gaps_s, 90)) if gaps_s.size else np.nan
            ),
            "interarrival_p99_s": (
                float(np.percentile(gaps_s, 99)) if gaps_s.size else np.nan
            ),
        }
        for bucket_name, threshold_s in GAP_BUCKETS_S:
            row[bucket_name] = int((gaps_s > threshold_s).sum())
        rows.append(row)
    return pd.DataFrame(rows)


def detect_outage_candidates(
    daily: pd.DataFrame, *, min_days: int
) -> pd.DataFrame:
    """Merge consecutive zero-ZOH-daylight days into outage candidate runs."""

    rows: list[dict[str, object]] = []
    zero_days = daily[
        (daily["daylight_minutes"] > 0) & (daily["daylight_minutes_zoh"] == 0)
    ]
    for (emi, channel_key), group in zero_days.groupby(
        ["emi", "channel_key"], sort=True, observed=True
    ):
        dates = sorted(group["date"])
        run_start = dates[0]
        previous = dates[0]
        runs: list[tuple[object, object]] = []
        for date in dates[1:]:
            if (pd.Timestamp(date) - pd.Timestamp(previous)).days == 1:
                previous = date
                continue
            runs.append((run_start, previous))
            run_start = date
            previous = date
        runs.append((run_start, previous))
        for start_date, end_date in runs:
            n_days = (pd.Timestamp(end_date) - pd.Timestamp(start_date)).days + 1
            if n_days >= min_days:
                rows.append(
                    {
                        "emi": emi,
                        "channel_key": channel_key,
                        "start_date": start_date,
                        "end_date": end_date,
                        "n_days": int(n_days),
                    }
                )
    return pd.DataFrame(
        rows, columns=["emi", "channel_key", "start_date", "end_date", "n_days"]
    )


def crosscheck_operator_leads(
    outages: pd.DataFrame,
    leads: pd.DataFrame,
    *,
    data_window_start: object | None = None,
) -> pd.DataFrame:
    """Compare operator-reported outage leads against measured outage runs.

    When ``data_window_start`` is given, a matched zero-run that begins at the
    very start of the analysed window is reported as ``absent_from_window_start``
    rather than ``corroborated``: the channel is simply missing for the whole
    window (consistent with a pre-window removal), which does not measure the
    reported date. A run that begins after the window start is a genuine
    in-window transition and stays ``corroborated``.
    """

    window_start_ts = (
        pd.to_datetime(data_window_start) if data_window_start is not None else None
    )
    rows: list[dict[str, object]] = []
    for lead in leads.to_dict("records"):
        reported_start = pd.to_datetime(
            str(lead["reported_start"] or ""), errors="coerce"
        )
        reported_end = pd.to_datetime(str(lead["reported_end"] or ""), errors="coerce")
        window_start = reported_start if pd.notna(reported_start) else pd.Timestamp.min
        window_end = reported_end if pd.notna(reported_end) else pd.Timestamp.max
        matching = outages[
            (outages["emi"] == lead["emi"])
            & (outages["channel_key"] == lead["channel_key"])
        ]
        overlapping = matching[
            (pd.to_datetime(matching["start_date"]) <= window_end)
            & (pd.to_datetime(matching["end_date"]) >= window_start)
        ]
        if overlapping.empty:
            rows.append(
                {
                    **lead,
                    "measured_start": None,
                    "measured_end": None,
                    "measured_run_count": 0,
                    "status": "not_found",
                }
            )
            continue
        measured_start = overlapping["start_date"].min()
        status = "corroborated"
        if (
            window_start_ts is not None
            and pd.to_datetime(measured_start) <= window_start_ts
        ):
            status = "absent_from_window_start"
        rows.append(
            {
                **lead,
                "measured_start": measured_start,
                "measured_end": overlapping["end_date"].max(),
                "measured_run_count": int(len(overlapping)),
                "status": status,
            }
        )
    return pd.DataFrame(rows)


def monthly_coverage_summary(daily: pd.DataFrame) -> pd.DataFrame:
    """Aggregate the daily coverage table into calendar months."""

    frame = daily.copy()
    frame["month"] = pd.to_datetime(frame["date"]).dt.strftime("%Y-%m")
    rows: list[dict[str, object]] = []
    for (emi, channel_key, month), group in frame.groupby(
        ["emi", "channel_key", "month"], sort=True, observed=True
    ):
        daylight_total = int(group["daylight_minutes"].sum())
        rows.append(
            {
                "emi": emi,
                "channel_key": channel_key,
                "month": month,
                "days_in_data": int(len(group)),
                "days_with_any_event": int(
                    (group["all_day_minutes_with_event"] > 0).sum()
                ),
                "daylight_minutes": daylight_total,
                "daylight_coverage_strict": (
                    float(group["daylight_minutes_with_event"].sum()) / daylight_total
                    if daylight_total
                    else 0.0
                ),
                "daylight_coverage_zoh": (
                    float(group["daylight_minutes_zoh"].sum()) / daylight_total
                    if daylight_total
                    else 0.0
                ),
            }
        )
    return pd.DataFrame(rows)
