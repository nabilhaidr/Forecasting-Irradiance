"""S0-6 point-in-time leakage harness.

The helpers in this module are deliberately test-only: feature and ensemble
production packages do not exist during Sprint 0.  They establish the contract
those packages must satisfy later and exercise the backward-only primitives
that already exist.

Historian timestamps below are synthetic ordering evidence only.  They do not
resolve the open S0-2 timezone-semantics question.  Minute-audit outputs are
indexed by bin start but become available only at bin end; they must never be
treated as features available at their index timestamp.
"""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd
import pytest

from src.characterisation.cov_contract import ParameterClass
from src.characterisation.data_audit import daily_coverage_summary
from src.characterisation.dni_cosz import REQUIRED_CHANNELS, align_cov_backward
from src.characterisation.kc_regime import minute_ghi_zoh


FrameTransform = Callable[[pd.DataFrame], pd.DataFrame]


def _assert_cutoff_invariant(
    transform: FrameTransform,
    frame: pd.DataFrame,
    *,
    cutoff: pd.Timestamp,
) -> None:
    """Apply the canonical full-vs-future-poisoned feature test."""

    full = transform(frame.copy())
    truncated = frame.copy()
    truncated.loc[truncated.index > cutoff, :] = float("nan")
    partial = transform(truncated)
    try:
        pd.testing.assert_frame_equal(
            full.loc[full.index <= cutoff],
            partial.loc[partial.index <= cutoff],
            check_exact=False,
            rtol=1e-9,
        )
    except AssertionError as exc:
        raise AssertionError(
            "output at or before cutoff changed after future information "
            "was removed"
        ) from exc


def _assert_target_isolation(
    transform: FrameTransform,
    frame: pd.DataFrame,
    *,
    cutoff: pd.Timestamp,
    target_columns: tuple[str, ...],
) -> None:
    """Poison targets from T onward and require features through T to hold."""

    full = transform(frame.copy())
    overlap = sorted(set(full.columns).intersection(target_columns))
    if overlap:
        raise AssertionError(f"target columns leaked into features: {overlap}")
    poisoned = frame.copy()
    poisoned.loc[poisoned.index >= cutoff, list(target_columns)] = float("nan")
    partial = transform(poisoned)
    try:
        pd.testing.assert_frame_equal(
            full.loc[full.index <= cutoff],
            partial.loc[partial.index <= cutoff],
            check_exact=False,
            rtol=1e-9,
        )
    except AssertionError as exc:
        raise AssertionError(
            "feature output depends on target data at or after decision time"
        ) from exc


def _assert_backward_sources(
    frame: pd.DataFrame,
    *,
    decision_time_column: str,
    source_time_columns: tuple[str, ...],
    max_staleness: pd.Timedelta,
    inclusive: bool,
) -> None:
    """Require sources to exist no later than T and within their age budget."""

    decision_time = frame[decision_time_column]
    if decision_time.isna().any():
        raise AssertionError("missing decision time")
    for column in source_time_columns:
        source_time = frame[column]
        if source_time.isna().any():
            raise AssertionError(f"missing source detected in {column}")
        age = decision_time - source_time
        if (age < pd.Timedelta(0)).any():
            raise AssertionError(f"future source detected in {column}")
        stale = age > max_staleness if inclusive else age >= max_staleness
        if stale.any():
            raise AssertionError(f"stale source detected in {column}")


def _assert_verification_lag(
    forecasts: pd.DataFrame,
    *,
    update_time_utc: pd.Timestamp,
) -> None:
    """Require every selected actual to have materialised by the update time."""

    issuance = forecasts["issuance_time_utc"]
    valid = forecasts["valid_time_utc"]
    horizon = valid - issuance
    if (horizon < pd.Timedelta(0)).any():
        raise AssertionError("negative horizon is invalid")
    available = valid <= update_time_utc
    equivalent_cutoff = issuance <= (update_time_utc - horizon)
    if not (available & equivalent_cutoff).all():
        raise AssertionError("verification lag admits an unavailable outcome")


def _trailing_features(source: pd.DataFrame) -> pd.DataFrame:
    sensor = source["sensor"]
    return pd.DataFrame(
        {
            "lag_1": sensor.shift(1),
            "mean_3min": sensor.rolling("3min", closed="left").mean(),
        },
        index=source.index,
    )


def _closure_events() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for channel_index, channel in enumerate(REQUIRED_CHANNELS):
        for timestamp, offset in (
            (pd.Timestamp("2026-07-19 00:00:30"), 0.0),
            (pd.Timestamp("2026-07-19 00:02:30"), 10.0),
        ):
            rows.append(
                {
                    "emi": "EMI01",
                    "channel_group": channel,
                    "parameter_class": (
                        ParameterClass.INSTANTANEOUS_IRRADIANCE.value
                    ),
                    "event_time": timestamp,
                    "value": 100.0 + channel_index + offset,
                }
            )
    return pd.DataFrame(rows)


def test_canonical_cutoff_harness_accepts_trailing_features() -> None:
    index = pd.date_range("2026-07-19T00:00:00Z", periods=6, freq="1min")
    frame = pd.DataFrame({"sensor": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]}, index=index)

    _assert_cutoff_invariant(_trailing_features, frame, cutoff=index[2])


def test_canonical_cutoff_harness_rejects_future_fill() -> None:
    index = pd.date_range("2026-07-19T00:00:00Z", periods=6, freq="1min")
    frame = pd.DataFrame(
        {"sensor": [1.0, 2.0, None, 40.0, 50.0, 60.0]},
        index=index,
    )

    def future_fill(source: pd.DataFrame) -> pd.DataFrame:
        return pd.DataFrame(
            {"future_fill": source["sensor"].bfill()},
            index=source.index,
        )

    with pytest.raises(AssertionError, match="future information"):
        _assert_cutoff_invariant(future_fill, frame, cutoff=index[2])


def test_target_isolation_accepts_features_and_rejects_same_row_target_use() -> None:
    index = pd.date_range("2026-07-19T00:00:00Z", periods=4, freq="1min")
    frame = pd.DataFrame(
        {
            "sensor": [1.0, 2.0, 3.0, 4.0],
            "ghi_target": [10.0, 20.0, 30.0, 40.0],
        },
        index=index,
    )

    _assert_target_isolation(
        _trailing_features,
        frame,
        cutoff=index[2],
        target_columns=("ghi_target",),
    )

    def same_row_target(source: pd.DataFrame) -> pd.DataFrame:
        return pd.DataFrame(
            {"renamed_target": source["ghi_target"]},
            index=source.index,
        )

    with pytest.raises(AssertionError, match="target data"):
        _assert_target_isolation(
            same_row_target,
            frame,
            cutoff=index[2],
            target_columns=("ghi_target",),
        )


def test_verification_lag_accepts_boundary_and_rejects_future_actual() -> None:
    update_time = pd.Timestamp("2026-07-19T11:00:00Z")
    eligible = pd.DataFrame(
        {
            "issuance_time_utc": pd.to_datetime(
                ["2026-07-19T09:00:00Z", "2026-07-19T10:00:00Z"]
            ),
            "valid_time_utc": pd.to_datetime(
                ["2026-07-19T11:00:00Z", "2026-07-19T11:00:00Z"]
            ),
        }
    )
    _assert_verification_lag(eligible, update_time_utc=update_time)

    premature = pd.concat(
        [
            eligible,
            pd.DataFrame(
                {
                    "issuance_time_utc": pd.to_datetime(
                        ["2026-07-19T10:00:01Z"]
                    ),
                    "valid_time_utc": pd.to_datetime(
                        ["2026-07-19T11:00:01Z"]
                    ),
                }
            ),
        ],
        ignore_index=True,
    )
    with pytest.raises(AssertionError, match="verification lag"):
        _assert_verification_lag(premature, update_time_utc=update_time)

    negative_horizon = pd.DataFrame(
        {
            "issuance_time_utc": pd.to_datetime(["2026-07-19T10:00:00Z"]),
            "valid_time_utc": pd.to_datetime(["2026-07-19T09:59:59Z"]),
        }
    )
    with pytest.raises(AssertionError, match="negative horizon"):
        _assert_verification_lag(
            negative_horizon,
            update_time_utc=update_time,
        )


def test_backward_source_harness_accepts_inclusive_staleness_boundary() -> None:
    aligned = pd.DataFrame(
        {
            "decision_time": pd.to_datetime(["2026-07-19T00:02:00Z"]),
            "sensor_source_time": pd.to_datetime(["2026-07-19T00:00:00Z"]),
        }
    )

    _assert_backward_sources(
        aligned,
        decision_time_column="decision_time",
        source_time_columns=("sensor_source_time",),
        max_staleness=pd.Timedelta("2min"),
        inclusive=True,
    )


def test_backward_source_harness_rejects_a_future_source() -> None:
    aligned = pd.DataFrame(
        {
            "decision_time": pd.to_datetime(["2026-07-19T00:02:00Z"]),
            "sensor_source_time": pd.to_datetime(["2026-07-19T00:02:01Z"]),
        }
    )

    with pytest.raises(AssertionError, match="future source"):
        _assert_backward_sources(
            aligned,
            decision_time_column="decision_time",
            source_time_columns=("sensor_source_time",),
            max_staleness=pd.Timedelta("2min"),
            inclusive=True,
        )


def test_backward_source_harness_rejects_a_stale_source() -> None:
    aligned = pd.DataFrame(
        {
            "decision_time": pd.to_datetime(["2026-07-19T00:02:00Z"]),
            "sensor_source_time": pd.to_datetime(["2026-07-18T23:59:59Z"]),
        }
    )

    with pytest.raises(AssertionError, match="stale source"):
        _assert_backward_sources(
            aligned,
            decision_time_column="decision_time",
            source_time_columns=("sensor_source_time",),
            max_staleness=pd.Timedelta("2min"),
            inclusive=True,
        )


def test_backward_source_harness_rejects_a_missing_source() -> None:
    aligned = pd.DataFrame(
        {
            "decision_time": pd.to_datetime(["2026-07-19T00:02:00Z"]),
            "sensor_source_time": pd.to_datetime([None], utc=True),
        }
    )

    with pytest.raises(AssertionError, match="missing source"):
        _assert_backward_sources(
            aligned,
            decision_time_column="decision_time",
            source_time_columns=("sensor_source_time",),
            max_staleness=pd.Timedelta("2min"),
            inclusive=True,
        )


def test_dni_alignment_uses_only_fresh_sources_at_or_before_grid_time() -> None:
    aligned = align_cov_backward(
        _closure_events(),
        frequency="1min",
        staleness_s=90.0,
    )
    source_columns = tuple(
        f"{channel}_source_time" for channel in REQUIRED_CHANNELS
    )

    assert list(aligned["grid_time"]) == [
        pd.Timestamp("2026-07-19 00:01:00"),
        pd.Timestamp("2026-07-19 00:02:00"),
    ]
    _assert_backward_sources(
        aligned,
        decision_time_column="grid_time",
        source_time_columns=source_columns,
        max_staleness=pd.Timedelta(seconds=90),
        inclusive=True,
    )


def test_minute_zoh_excludes_an_event_at_the_closed_bin_end() -> None:
    grid = pd.date_range("2026-07-19 00:00:00", periods=2, freq="1min")
    events = pd.DataFrame(
        {
            "event_time": pd.to_datetime(
                ["2026-07-19 00:00:30", "2026-07-19 00:01:00"]
            ),
            "value": [10.0, 99.0],
        }
    )

    result = minute_ghi_zoh(
        events,
        grid=grid,
        zoh_staleness=pd.Timedelta("5min"),
    )

    first_bin_available_at = grid[0] + pd.Timedelta("1min")
    assert events.loc[0, "event_time"] < first_bin_available_at
    assert events.loc[1, "event_time"] == first_bin_available_at
    assert result.loc[grid[0]] == 10.0
    assert result.loc[grid[1]] == 99.0


def test_minute_zoh_rejects_exact_staleness_at_the_next_bin() -> None:
    grid = pd.date_range("2026-07-19 00:00:00", periods=2, freq="1min")
    events = pd.DataFrame(
        {
            "event_time": pd.to_datetime(["2026-07-19 00:00:30"]),
            "value": [10.0],
        }
    )

    result = minute_ghi_zoh(
        events,
        grid=grid,
        zoh_staleness=pd.Timedelta("30s"),
    )

    assert result.loc[grid[0]] == 10.0
    assert pd.isna(result.loc[grid[1]])


def test_daily_coverage_does_not_count_an_event_at_bin_end() -> None:
    grid = pd.date_range("2026-07-19 00:00:00", periods=1, freq="1min")
    events = pd.DataFrame(
        {
            "emi": ["EMI01"],
            "channel_key": ["GHI"],
            "event_time": pd.to_datetime(["2026-07-19 00:01:00"]),
        }
    )
    daylight = pd.Series([True], index=grid)

    daily = daily_coverage_summary(
        events,
        grid=grid,
        daylight=daylight,
        zoh_staleness=pd.Timedelta("5min"),
    )

    assert int(daily.iloc[0]["daylight_minutes_with_event"]) == 0
    assert int(daily.iloc[0]["daylight_minutes_zoh"]) == 0
