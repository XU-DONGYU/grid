from __future__ import annotations

import pytest

from grid_analyzer.backtest.engine import run_backtest
from grid_analyzer.backtest.metrics import (
    aggregate_metrics,
    compute_metrics,
    daily_equity,
    daily_returns,
    sharpe_ratio,
    sortino_ratio,
)


def test_daily_equity_uses_last_point_per_day() -> None:
    curve = [
        {"date": "2026-01-05 09:35", "trading_day": "2026-01-05", "equity": 100},
        {"date": "2026-01-05 15:00", "trading_day": "2026-01-05", "equity": 102},
        {"date": "2026-01-06 15:00", "trading_day": "2026-01-06", "equity": 101},
    ]
    assert daily_equity(curve) == [("2026-01-05", 102), ("2026-01-06", 101)]
    assert daily_returns(curve) == pytest.approx([101 / 102 - 1])


def test_ratios_are_finite() -> None:
    assert sharpe_ratio([0.01, 0.02, -0.01]) > 0
    assert sortino_ratio([0.01, 0.02, -0.01]) > 0
    assert sharpe_ratio([0.01]) == 0
    assert sortino_ratio([0.01]) == 0


def test_compute_metrics_from_backtest() -> None:
    grid = {
        "capital": 100_000,
        "shares_per_grid": 100,
        "levels": [90.0, 100.0, 110.0],
        "gap_pct": 11.11,
    }
    bars = [
        {"date": "d0", "open": 95, "close": 95, "high": 96, "low": 90, "volume": 1},
        {"date": "d1", "open": 109, "close": 109, "high": 110, "low": 108, "volume": 1},
    ]
    bt = run_backtest(bars, grid, 0.025, 5.0, 0.0, 0.0)
    metrics = compute_metrics(bt, 100_000)
    assert metrics["realized_annual_pct"] > 0
    assert metrics["total_annual_pct"] > 0
    assert metrics["max_drawdown_pct"] >= 0
    assert metrics["win_rate_pct"] == pytest.approx(100.0)
    assert metrics["profit_factor"] is None or metrics["profit_factor"] > 0


def test_aggregate_metrics() -> None:
    aggregated = aggregate_metrics(
        [
            {"realized_annual_pct": 10.0, "total_annual_pct": 12.0},
            {"realized_annual_pct": 14.0, "total_annual_pct": 16.0},
        ]
    )
    assert aggregated["realized_annual_pct"]["mean"] == pytest.approx(12.0)
    assert aggregated["realized_annual_pct"]["worst"] == pytest.approx(10.0)
