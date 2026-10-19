from __future__ import annotations

import app


def bar(day: str, time: str, open_: float, close: float, high: float, low: float) -> dict:
    return {
        "timestamp": f"{day} {time}",
        "trading_day": day,
        "open": open_,
        "close": close,
        "high": high,
        "low": low,
        "volume": 1000,
        "amount": 10000,
    }


def manual_grid() -> dict:
    return {
        "capital": 100_000,
        "shares_per_grid": 100,
        "levels": [90.0, 100.0, 110.0],
        "gap_pct": 11.11,
    }


def test_t_plus_one_uses_trading_day_not_bar_index() -> None:
    bars = [
        bar("2026-01-05", "09:35", 95, 95, 96, 90),
        bar("2026-01-05", "09:40", 95, 109, 110, 95),
        bar("2026-01-06", "09:35", 109, 109, 110, 108),
    ]
    bt = app.run_backtest(bars, manual_grid(), 0.025, 5.0, 0.0, 0.0)
    assert bt["buy_count"] == 1
    assert bt["rounds"] == 1
    assert bt["sell_count"] == 1
    assert bt["end_holding"] == 0
    assert bt["trading_days"] == 2
    assert len(bt["equity_curve"]) == 3
    assert bt["equity_curve"][0]["trading_day"] == "2026-01-05"


def test_same_day_later_bars_cannot_sell() -> None:
    bars = [
        bar("2026-01-05", "09:35", 95, 95, 96, 90),
        bar("2026-01-05", "09:40", 95, 109, 110, 95),
    ]
    bt = app.run_backtest(bars, manual_grid(), 0.025, 5.0, 0.0, 0.0)
    assert bt["rounds"] == 0
    assert bt["end_holding"] == 1


def test_intraday_stop_respects_t_plus_one() -> None:
    bars = [
        bar("2026-01-05", "09:35", 95, 95, 96, 90),
        bar("2026-01-05", "09:40", 95, 80, 95, 79),
        bar("2026-01-06", "09:35", 80, 80, 81, 79),
    ]
    bt = app.run_backtest(bars, manual_grid(), 0.025, 5.0, 0.0, 5.0)
    assert bt["stop_triggered"] is True
    assert bt["stop_date"] == "2026-01-05 09:40"
    assert bt["end_holding"] == 0
    assert bt["trading_days"] == 2
