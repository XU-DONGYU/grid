from __future__ import annotations

import pytest

import app


def manual_grid(
    capital: float = 100_000,
    shares: int = 100,
    levels: list[float] | None = None,
) -> dict:
    levels = levels or [90.0, 100.0, 110.0]
    return {
        "capital": capital,
        "shares_per_grid": shares,
        "levels": levels,
        "gap_pct": (levels[1] / levels[0] - 1) * 100,
    }


def make_bar(date: str, open_: float, close: float, high: float, low: float) -> dict:
    return {
        "date": date,
        "open": open_,
        "close": close,
        "high": high,
        "low": low,
        "volume": 1,
    }


def test_backtest_invariants(fixture_002541: dict) -> None:
    payload = fixture_002541
    klines = payload["klines"][-120:]
    grid, _, _, _ = app.build_grids(
        klines,
        payload["quote"]["price"],
        100_000,
        single=True,
        main_ratio=1.0,
        spread_pct=0.05,
        fee_pct=0.025,
        min_fee=5,
    )
    bt = app.run_backtest(klines, grid, 0.025, 5.0, 0.0, 5.0)

    assert len(bt["equity_curve"]) == len(klines)
    assert abs((bt["end_cash"] + bt["end_holding_value"]) - (100_000 + bt["net_profit"])) < 1e-6
    assert abs((bt["realized_pnl"] + bt["unrealized_pnl"]) - bt["net_profit"]) < 1e-6
    assert bt["end_cash"] >= -1e-9
    assert 0 <= bt["max_drawdown_pct"] <= 100
    assert bt["min_equity_pnl"] <= 0
    assert bt["total_fees"] >= 0


def test_t_plus_one_blocks_same_day_sell() -> None:
    grid = manual_grid()
    klines = [make_bar("d0", 95, 109, 110, 90)]

    bt = app.run_backtest(klines, grid, 0.025, 5.0, 0.0, 0.0)

    assert bt["buy_count"] == 1
    assert bt["rounds"] == 0
    assert bt["sell_count"] == 0
    assert bt["end_holding"] == 1
    assert bt["end_holding_qty"] == 100


def test_sell_after_t_plus_one_unlocks() -> None:
    grid = manual_grid()
    klines = [
        make_bar("d0", 95, 109, 110, 90),
        make_bar("d1", 109, 110, 111, 108),
    ]

    bt = app.run_backtest(klines, grid, 0.025, 5.0, 0.0, 0.0)

    assert bt["rounds"] == 1
    assert bt["sell_count"] == 1
    assert bt["end_holding"] == 0
    assert bt["net_profit"] > 0


def test_stop_loss_liquidates_and_stops_trading() -> None:
    grid = manual_grid()
    klines = [
        make_bar("d0", 95, 95, 96, 90),
        make_bar("d1", 80, 80, 81, 79),
        make_bar("d2", 75, 75, 76, 74),
    ]

    bt = app.run_backtest(klines, grid, 0.025, 5.0, 0.0, 5.0)

    assert bt["stop_triggered"] is True
    assert bt["stop_date"] == "d1"
    assert bt["stop_fill_price"] == 80
    assert bt["end_holding"] == 0
    assert bt["net_profit"] < 0


def test_minimum_commission_is_applied() -> None:
    grid = manual_grid(capital=100_000, shares=100, levels=[9.0, 10.0, 11.0])
    klines = [
        make_bar("d0", 9.5, 10.4, 10.4, 9),
        make_bar("d1", 10.5, 10.5, 10.6, 10.5),
    ]

    bt = app.run_backtest(klines, grid, 0.025, 5.0, 0.0, 0.0)

    assert bt["rounds"] == 1
    assert bt["total_fees"] >= 10.5
    assert bt["net_profit"] == pytest.approx(139.475, abs=0.01)


def test_initial_position_cost_is_deducted() -> None:
    grid = manual_grid()
    klines = [make_bar("d0", 95, 95, 96, 90)]

    bt = app.run_backtest(klines, grid, 0.025, 5.0, 0.3, 0.0)

    assert bt["init_cost"] > 0
    assert abs((bt["end_cash"] + bt["end_holding_value"]) - (100_000 + bt["net_profit"])) < 1e-6


def test_zero_shares_returns_empty_backtest() -> None:
    grid = manual_grid(shares=0)
    bt = app.run_backtest([make_bar("d0", 95, 95, 96, 90)], grid, 0.025, 5.0, 0.0, 5.0)
    assert bt["rounds"] == 0
    assert bt["equity_curve"] == []
