from __future__ import annotations

import math
from datetime import date, datetime, timedelta

import pytest

from grid_analyzer.services.intraday_research import (
    InsufficientIntradayDataError,
    IntradayValidationConfig,
    intraday_k_values,
    run_intraday_validation,
)


def trading_days(count: int) -> list[str]:
    days = []
    current = date(2025, 1, 2)
    while len(days) < count:
        if current.weekday() < 5:
            days.append(current.isoformat())
        current += timedelta(days=1)
    return days


def make_daily_bars(days: list[str]) -> list[dict]:
    bars = []
    for i, day in enumerate(days):
        close = 100 + 5 * math.sin(i / 5)
        bars.append(
            {
                "timestamp": day,
                "trading_day": day,
                "open": close - 0.5,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close,
                "volume": 100000,
                "amount": 10000000,
            }
        )
    return bars


def intraday_times() -> list[str]:
    times = []
    current = datetime(2025, 1, 2, 9, 35)
    morning_end = datetime(2025, 1, 2, 11, 30)
    while current <= morning_end:
        times.append(current.strftime("%H:%M"))
        current += timedelta(minutes=5)
    current = datetime(2025, 1, 2, 13, 5)
    afternoon_end = datetime(2025, 1, 2, 15, 0)
    while current <= afternoon_end:
        times.append(current.strftime("%H:%M"))
        current += timedelta(minutes=5)
    return times


def make_5m_bars(days: list[str]) -> list[dict]:
    times = intraday_times()
    bars = []
    for day_index, day in enumerate(days):
        base = 100 + 5 * math.sin(day_index / 5)
        for i, time in enumerate(times):
            price = base + 0.8 * math.sin(i / 3 + day_index)
            bars.append(
                {
                    "timestamp": f"{day} {time}",
                    "trading_day": day,
                    "open": price,
                    "high": price + 0.2,
                    "low": price - 0.2,
                    "close": price,
                    "volume": 1000,
                    "amount": 10000,
                }
            )
    return bars


def test_default_k_values_are_21() -> None:
    values = intraday_k_values()
    assert len(values) == 21
    assert values[0] == 0.5
    assert values[-1] == 1.5


def test_run_intraday_validation() -> None:
    days = trading_days(60)
    bars_5m = make_5m_bars(days)
    daily = make_daily_bars(days)
    config = IntradayValidationConfig(
        capital=1_000_000,
        stop_losses=(0.0,),
        window_days=10,
        in_sample_ratio=0.7,
        final_blind_days=3,
        min_oos_days=0,
    )
    result = run_intraday_validation(bars_5m, daily, config)

    assert len(result["k_values"]) == 21
    assert len(result["stop_losses"]) == 1
    assert result["folds"]
    assert len(result["cells"]) == 21
    assert result["summary"]["oos_coverage_days"] >= 0
    assert result["parameter_stability"]["k_values"]
    assert result["locked"]["k"] in result["k_values"]
    assert result["locked"]["blind"] is not None

    folds = result["folds"]
    for previous, current in zip(folds, folds[1:]):
        assert current["oos_start"] >= previous["oos_end"]
    assert result["locked"]["blind"]["start"] > folds[-1]["oos_end"]


def test_insufficient_data_raises() -> None:
    days = trading_days(10)
    with pytest.raises(InsufficientIntradayDataError):
        run_intraday_validation(
            make_5m_bars(days),
            make_daily_bars(days),
            IntradayValidationConfig(),
        )
