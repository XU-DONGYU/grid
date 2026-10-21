from __future__ import annotations

import math
from datetime import date, datetime, timedelta

import pytest

from grid_analyzer.backtest.plateau import (
    AtrPoint,
    InsufficientPlateauDataError,
    PlateauConfig,
    _band_levels,
    _build_day_steps,
    _DayStep,
    build_daily_anchors,
    build_live_output,
    compute_atr_series,
    detect_islands,
    effective_friction_pct,
    front_running_adjust,
    plateau_k_values,
    prior_overlap,
    resolve_band,
    run_plateau_scan,
    safe_k_floor,
    select_plateau,
    simulate_k,
)
from grid_analyzer.constants import STAMP_TAX


def point(k: float, value: float) -> dict:
    return {
        "k": k,
        "net_return_pct": value,
        "loops": 50,
        "open_position_pnl_pct": 0.0,
        "total_return_pct": value,
        "below_safe": False,
        "is_island": False,
        "in_plateau": False,
        "is_optimal": False,
    }


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


def make_config(**overrides: object) -> PlateauConfig:
    values: dict = {
        "capital": 1_000_000,
        "shares_per_grid": 100,
        "fee": 0.0,
        "min_fee": 0.0,
        "spread_pct": 0.0,
        "slippage_pct": 0.0,
        "price_limit_pct": 0.0,
        "holdout_ratio": 0.0,
    }
    values.update(overrides)
    return PlateauConfig(**values)


def test_plateau_k_values_default_range() -> None:
    values = plateau_k_values(0.20, 2.50, 0.05)
    assert len(values) == 47
    assert values[0] == 0.2
    assert values[-1] == 2.5


def test_safe_k_floor_and_friction() -> None:
    config = PlateauConfig(shares_per_grid=100, fee=0.025, min_fee=5, spread_pct=0.05)
    friction = effective_friction_pct(config, 100.0)
    assert friction == pytest.approx(0.025 * 2 + 0.05 + 0.05)
    assert safe_k_floor(0.1, 2.0) == pytest.approx(0.5)
    assert math.isinf(safe_k_floor(0.1, 0.0))


def test_compute_atr_series_does_not_revise_history() -> None:
    days = [f"2025-01-{index:02d}" for index in range(1, 21)]
    bars = [
        {
            "trading_day": day,
            "open": 100.0,
            "high": 101.0 + index * 0.1,
            "low": 99.0 - index * 0.1,
            "close": 100.0,
        }
        for index, day in enumerate(days)
    ]
    baseline = compute_atr_series(bars, 14)
    extended = compute_atr_series(
        bars + [{"trading_day": "2025-01-21", "open": 100, "high": 150, "low": 50, "close": 100}],
        14,
    )
    assert len(baseline) == 20
    assert extended[:20] == baseline
    assert extended[-1].atr > baseline[-1].atr


def test_day_step_uses_only_prior_atr() -> None:
    atr_series = [
        AtrPoint("2025-01-02", 100.0, 2.0, 2.0),
        AtrPoint("2025-01-03", 100.0, 10.0, 10.0),
        AtrPoint("2025-01-04", 100.0, 6.0, 6.0),
    ]
    days = ["2025-01-02", "2025-01-03", "2025-01-04"]
    dynamic = _build_day_steps(atr_series, days, PlateauConfig(mode="dynamic"), 1.0)
    assert "2025-01-02" not in dynamic
    assert dynamic["2025-01-03"].atr_pct == pytest.approx(2.0)
    assert dynamic["2025-01-03"].anchor == pytest.approx(100.0)
    assert dynamic["2025-01-04"].atr_pct == pytest.approx(10.0)
    assert dynamic["2025-01-04"].anchor == pytest.approx(100.0)

    static = _build_day_steps(atr_series, days, PlateauConfig(mode="static_mean"), 1.0)
    assert static["2025-01-03"].step_pct == pytest.approx(2.0)
    assert static["2025-01-03"].step_abs == pytest.approx(2.0)
    assert static["2025-01-04"].step_pct == pytest.approx(6.0)
    assert static["2025-01-04"].step_abs == pytest.approx(6.0)


def step(day: str, step_abs: float, anchor: float = 100.0) -> _DayStep:
    return _DayStep(day, step_pct=step_abs, step_abs=step_abs, atr_pct=step_abs, anchor=anchor)


def test_step_trigger_buys_after_crossing_and_respects_t_plus_one() -> None:
    day_steps = {
        "2025-01-02": step("2025-01-02", 2.0),
        "2025-01-03": step("2025-01-03", 2.0),
        "2025-01-04": step("2025-01-04", 2.0),
    }
    bars_by_day = {
        "2025-01-02": [bar("2025-01-02", "09:35", 100, 100, 101, 99)],
        "2025-01-03": [bar("2025-01-03", "09:35", 100, 100, 101, 97.99)],
        "2025-01-04": [bar("2025-01-04", "09:35", 100, 100, 101, 99)],
    }
    result = simulate_k(bars_by_day, day_steps, make_config())
    net_profit = (100 - 98) * 100 - 100 * 100 * STAMP_TAX
    assert result["loops"] == 1
    assert result["open_position_count"] == 0
    assert result["net_return_pct"] == pytest.approx(net_profit / 1_000_000 * 100)
    assert result["max_positions_used"] == 1


def test_one_cent_short_of_grid_line_does_not_fill() -> None:
    day_steps = {
        "2025-01-02": step("2025-01-02", 2.0),
        "2025-01-03": step("2025-01-03", 2.0),
    }
    bars_by_day = {
        "2025-01-02": [bar("2025-01-02", "09:35", 100, 100, 101, 98.01)],
        "2025-01-03": [bar("2025-01-03", "09:35", 100, 100, 101, 99)],
    }
    result = simulate_k(bars_by_day, day_steps, make_config())
    assert result["loops"] == 0
    assert result["open_position_count"] == 0


def test_penetration_requires_crossing_by_configured_amount() -> None:
    day_steps = {
        "2025-01-02": step("2025-01-02", 2.0),
        "2025-01-03": step("2025-01-03", 2.0),
        "2025-01-06": step("2025-01-06", 2.0),
        "2025-01-07": step("2025-01-07", 2.0),
    }
    bars_by_day = {
        "2025-01-02": [bar("2025-01-02", "09:35", 100, 100, 101, 98.0)],
        "2025-01-03": [bar("2025-01-03", "09:35", 100, 100, 101, 97.99)],
        "2025-01-06": [bar("2025-01-06", "09:35", 100, 100, 100.0, 99)],
        "2025-01-07": [bar("2025-01-07", "09:35", 100, 100, 100.01, 99)],
    }
    result = simulate_k(
        bars_by_day,
        day_steps,
        make_config(penetration_abs=0.01),
    )
    assert result["loops"] == 1
    assert result["first_trade_day"] == "2025-01-03"
    assert result["last_trade_day"] == "2025-01-07"


def test_ending_equity_splits_realized_and_open_pnl() -> None:
    day_steps = {
        "2025-01-02": step("2025-01-02", 2.0),
        "2025-01-03": step("2025-01-03", 2.0),
    }
    bars_by_day = {
        "2025-01-02": [bar("2025-01-02", "09:35", 100, 100, 99, 97.99)],
        "2025-01-03": [bar("2025-01-03", "09:35", 99, 99, 99, 98)],
    }
    result = simulate_k(
        bars_by_day,
        day_steps,
        make_config(penetration_abs=0.01),
    )
    assert result["loops"] == 0
    assert result["realized_profit_yuan"] == pytest.approx(0.0)
    assert result["open_position_pnl_yuan"] == pytest.approx(100.0)
    assert result["total_pnl_yuan"] == pytest.approx(100.0)
    assert result["ending_equity_yuan"] == pytest.approx(1_000_100.0)
    assert result["ending_equity_return_pct"] == pytest.approx(0.01)


def test_static_mode_uses_percentage_step() -> None:
    day_steps = {
        "2025-01-02": step("2025-01-02", 2.0),
        "2025-01-03": step("2025-01-03", 2.0),
    }
    bars_by_day = {
        "2025-01-02": [bar("2025-01-02", "09:35", 100, 100, 101, 97.9)],
        "2025-01-03": [bar("2025-01-03", "09:35", 100, 100, 101, 99)],
    }
    result = simulate_k(bars_by_day, day_steps, make_config(mode="static_mean"))
    net_profit = (100 - 98) * 100 - 100 * 100 * STAMP_TAX
    assert result["loops"] == 1
    assert result["net_return_pct"] == pytest.approx(net_profit / 1_000_000 * 100)


def test_rolling_ladder_rearms_in_a_trend_and_caps_positions() -> None:
    day_steps = {
        "2025-01-02": step("2025-01-02", 2.0, 100.0),
        "2025-01-03": step("2025-01-03", 2.0, 102.0),
        "2025-01-04": step("2025-01-04", 2.0, 104.0),
        "2025-01-05": step("2025-01-05", 2.0, 106.0),
    }
    bars_by_day = {
        "2025-01-02": [bar("2025-01-02", "09:35", 100, 100, 100, 95)],
        "2025-01-03": [bar("2025-01-03", "09:35", 102, 103, 103, 101)],
        "2025-01-04": [bar("2025-01-04", "09:35", 104, 104, 104, 99)],
        "2025-01-05": [bar("2025-01-05", "09:35", 106, 107, 107, 105)],
    }
    result = simulate_k(bars_by_day, day_steps, make_config(max_positions=2))
    assert result["loops"] == 4
    assert result["max_positions_used"] == 2
    assert result["max_positions"] == 2
    assert result["capital_return_pct"] == pytest.approx(result["net_return_pct"])


def test_default_is_fixed_band_without_stop() -> None:
    config = PlateauConfig()
    assert config.anchor_policy == "fixed"
    assert config.stop_loss_pct == 0.0


def test_band_levels_and_breakout_wait() -> None:
    levels = _band_levels(90.0, 110.0, 10.0)
    assert [round(level, 4) for _, level in levels] == [90.0, 99.0, 108.9]

    day_steps = {
        "2025-01-02": _DayStep(
            "2025-01-02",
            step_pct=10.0,
            step_abs=10.0,
            atr_pct=2.0,
            anchor=100.0,
            prev_close=100.0,
            band_lower=90.0,
            band_upper=110.0,
        ),
        "2025-01-03": _DayStep(
            "2025-01-03",
            step_pct=10.0,
            step_abs=10.0,
            atr_pct=2.0,
            anchor=100.0,
            prev_close=100.0,
            band_lower=90.0,
            band_upper=110.0,
        ),
        "2025-01-06": _DayStep(
            "2025-01-06",
            step_pct=10.0,
            step_abs=10.0,
            atr_pct=2.0,
            anchor=100.0,
            prev_close=109.0,
            band_lower=90.0,
            band_upper=110.0,
        ),
    }
    bars_by_day = {
        "2025-01-02": [bar("2025-01-02", "09:35", 100, 100, 100, 95)],
        "2025-01-03": [bar("2025-01-03", "09:35", 108, 109, 109, 107)],
        "2025-01-06": [bar("2025-01-06", "09:35", 115, 115, 116, 114)],
    }
    result = simulate_k(
        bars_by_day,
        day_steps,
        make_config(anchor_policy="fixed", max_positions=8),
    )
    assert result["loops"] == 1
    assert result["open_position_count"] == 0
    assert result["upper_breakout_days"] == 1
    assert result["lower_breakout_days"] == 0


def test_resolve_band_manual_and_auto() -> None:
    manual = resolve_band([], "2025-01-02", PlateauConfig(band_lower=8.0, band_upper=12.0))
    assert manual == (8.0, 12.0, "manual")

    prior = [
        AtrPoint("2025-01-02", 10.0, 0.2, 2.0, high=10.5, low=9.5),
        AtrPoint("2025-01-03", 10.2, 0.2, 2.0, high=10.8, low=9.8),
    ]
    lower, upper, source = resolve_band(prior, "2025-01-06", PlateauConfig())
    assert source == "auto"
    assert lower == pytest.approx(9.5 * 1.02)
    assert upper == pytest.approx(10.8 * 0.98)


def test_anchor_policies_use_only_prior_data() -> None:
    atr_series = [
        AtrPoint("2025-01-02", 100.0, 2.0, 2.0, high=101.0, low=99.0),
        AtrPoint("2025-01-03", 105.0, 2.0, 2.0, high=106.0, low=104.0),
        AtrPoint("2025-01-06", 120.0, 2.0, 2.0, high=121.0, low=119.0),
        AtrPoint("2025-01-07", 121.0, 2.0, 2.0, high=122.0, low=120.0),
    ]
    days = ["2025-01-02", "2025-01-03", "2025-01-06", "2025-01-07"]
    daily = build_daily_anchors(atr_series, days, PlateauConfig(anchor_policy="daily_roll"))
    assert daily["2025-01-03"] == pytest.approx(100.0)
    assert daily["2025-01-06"] == pytest.approx(105.0)
    assert daily["2025-01-07"] == pytest.approx(120.0)

    fixed = build_daily_anchors(atr_series, days, PlateauConfig(anchor_policy="fixed"))
    assert fixed["2025-01-03"] == pytest.approx(100.0)
    assert fixed["2025-01-06"] == pytest.approx(100.0)
    assert fixed["2025-01-07"] == pytest.approx(100.0)

    periodic = build_daily_anchors(
        atr_series,
        days,
        PlateauConfig(anchor_policy="periodic", reanchor_period_days=2),
    )
    assert periodic["2025-01-03"] == pytest.approx(100.0)
    assert periodic["2025-01-06"] == pytest.approx(105.0)
    assert periodic["2025-01-07"] == pytest.approx(105.0)

    band = build_daily_anchors(
        atr_series,
        days,
        PlateauConfig(anchor_policy="fixed_band", band_lookback_days=2, band_buffer_pct=0.0),
    )
    assert band["2025-01-03"] == pytest.approx(100.0)
    assert band["2025-01-06"] == pytest.approx(105.0)
    assert band["2025-01-07"] == pytest.approx(120.0)


def test_lot_rounding_and_capital_constraint() -> None:
    day_steps = {
        "2025-01-02": step("2025-01-02", 2.0, 100.0),
        "2025-01-03": step("2025-01-03", 2.0, 102.0),
    }
    bars_by_day = {
        "2025-01-02": [bar("2025-01-02", "09:35", 100, 100, 100, 95)],
        "2025-01-03": [bar("2025-01-03", "09:35", 102, 102, 102, 101)],
    }
    traded = simulate_k(
        bars_by_day,
        day_steps,
        make_config(max_positions=1),
    )
    assert traded["loops"] == 1
    assert traded["capital_constrained_buys"] == 0
    assert traded["open_position_count"] == 0

    expensive = simulate_k(
        {
            "2025-01-02": [bar("2025-01-02", "09:35", 200, 200, 200, 190)],
            "2025-01-03": [bar("2025-01-03", "09:35", 200, 200, 200, 199)],
        },
        {
            "2025-01-02": step("2025-01-02", 4.0, 200.0),
            "2025-01-03": step("2025-01-03", 4.0, 204.0),
        },
        make_config(max_positions=1, capital=10_000),
    )
    assert expensive["loops"] == 0
    assert expensive["open_position_count"] == 0
    assert expensive["capital_constrained_buys"] > 0


def test_slippage_reduces_net_return() -> None:
    day_steps = {
        "2025-01-02": step("2025-01-02", 2.0, 100.0),
        "2025-01-03": step("2025-01-03", 2.0, 102.0),
    }
    bars_by_day = {
        "2025-01-02": [bar("2025-01-02", "09:35", 100, 100, 100, 95)],
        "2025-01-03": [bar("2025-01-03", "09:35", 102, 102, 102, 101)],
    }
    clean = simulate_k(bars_by_day, day_steps, make_config())
    slipped = simulate_k(bars_by_day, day_steps, make_config(slippage_pct=0.5))
    assert slipped["net_return_pct"] < clean["net_return_pct"]
    assert slipped["slippage_paid_pct"] > 0


def test_stop_loss_liquidates_and_restarts_band() -> None:
    day_steps = {
        "2025-01-02": _DayStep(
            "2025-01-02", step_pct=2.0, step_abs=2.0, atr_pct=2.0, anchor=100.0, prev_close=100.0
        ),
        "2025-01-03": _DayStep(
            "2025-01-03", step_pct=2.0, step_abs=2.0, atr_pct=2.0, anchor=100.0, prev_close=100.0
        ),
        "2025-01-06": _DayStep(
            "2025-01-06", step_pct=2.0, step_abs=2.0, atr_pct=2.0, anchor=90.0, prev_close=90.0
        ),
        "2025-01-07": _DayStep(
            "2025-01-07", step_pct=2.0, step_abs=2.0, atr_pct=2.0, anchor=90.0, prev_close=90.0
        ),
    }
    bars_by_day = {
        "2025-01-02": [bar("2025-01-02", "09:35", 100, 100, 100, 97)],
        "2025-01-03": [bar("2025-01-03", "09:35", 90, 90, 90, 89)],
        "2025-01-06": [bar("2025-01-06", "09:35", 90, 90, 90, 87)],
        "2025-01-07": [bar("2025-01-07", "09:35", 90, 90, 90, 89)],
    }
    result = simulate_k(
        bars_by_day,
        day_steps,
        make_config(max_positions=1, stop_loss_pct=5.0, restart_cooldown_days=0, penetration_abs=0.0),
    )
    assert result["stop_count"] == 1
    assert result["restart_count"] == 1
    assert result["last_stop_day"] == "2025-01-03"
    assert result["loops"] == 1
    assert result["open_position_count"] == 0


def test_stop_loss_cooldown_delays_restart() -> None:
    day_steps = {
        "2025-01-02": _DayStep(
            "2025-01-02", step_pct=2.0, step_abs=2.0, atr_pct=2.0, anchor=100.0, prev_close=100.0
        ),
        "2025-01-03": _DayStep(
            "2025-01-03", step_pct=2.0, step_abs=2.0, atr_pct=2.0, anchor=100.0, prev_close=100.0
        ),
        "2025-01-06": _DayStep(
            "2025-01-06", step_pct=2.0, step_abs=2.0, atr_pct=2.0, anchor=90.0, prev_close=90.0
        ),
        "2025-01-07": _DayStep(
            "2025-01-07", step_pct=2.0, step_abs=2.0, atr_pct=2.0, anchor=90.0, prev_close=90.0
        ),
        "2025-01-08": _DayStep(
            "2025-01-08", step_pct=2.0, step_abs=2.0, atr_pct=2.0, anchor=90.0, prev_close=90.0
        ),
    }
    bars_by_day = {
        "2025-01-02": [bar("2025-01-02", "09:35", 100, 100, 100, 97)],
        "2025-01-03": [bar("2025-01-03", "09:35", 90, 90, 90, 89)],
        "2025-01-06": [bar("2025-01-06", "09:35", 90, 90, 90, 87)],
        "2025-01-07": [bar("2025-01-07", "09:35", 90, 90, 90, 87)],
        "2025-01-08": [bar("2025-01-08", "09:35", 90, 90, 90, 89)],
    }
    result = simulate_k(
        bars_by_day,
        day_steps,
        make_config(max_positions=1, stop_loss_pct=5.0, restart_cooldown_days=1, penetration_abs=0.0),
    )
    assert result["stop_count"] == 1
    assert result["stopped_days"] == 1
    assert result["restart_count"] == 1


def test_price_limit_lock_blocks_fills() -> None:
    day_steps = {
        "2025-01-02": _DayStep(
            "2025-01-02", step_pct=2.0, step_abs=2.0, atr_pct=2.0, anchor=100.0, prev_close=100.0
        ),
        "2025-01-03": _DayStep(
            "2025-01-03", step_pct=2.0, step_abs=2.0, atr_pct=2.0, anchor=100.0, prev_close=100.0
        ),
    }
    bars_by_day = {
        "2025-01-02": [bar("2025-01-02", "09:35", 100, 100, 100, 100)],
        "2025-01-03": [bar("2025-01-03", "09:35", 90, 90, 90, 90)],
    }
    result = simulate_k(
        bars_by_day,
        day_steps,
        make_config(price_limit_pct=10.0),
    )
    assert result["limit_locked_days"] == 1
    assert result["loops"] == 0
    assert result["open_position_count"] == 0


def test_detect_islands_flags_single_spike() -> None:
    config = PlateauConfig(island_drop_ratio=0.25, island_min_drop_pct=0.2)
    points = [point(0.2, 1.0), point(0.25, 1.1), point(0.3, 5.0), point(0.35, 1.2), point(0.4, 1.3)]
    islands = detect_islands(points, config)
    assert [item["k"] for item in islands] == [0.3]
    assert points[2]["is_island"] is True


def test_select_plateau_uses_high_mean_low_variance_and_center_left() -> None:
    points = [
        point(0.2, 1.0),
        point(0.25, 2.0),
        point(0.3, 3.0),
        point(0.35, 3.1),
        point(0.4, 2.9),
        point(0.45, 1.5),
    ]
    config = PlateauConfig(plateau_window=3, plateau_stability_penalty=0.5)
    plateau = select_plateau(points, config)
    assert plateau is not None
    assert plateau["k_left"] == 0.3
    assert plateau["k_right"] == 0.4
    assert plateau["k_star"] == 0.35
    assert plateau["window_points"] == 3
    assert plateau["profitable"] is True


def test_select_plateau_penalises_open_losses() -> None:
    def with_open(k: float, net: float, open_pnl: float) -> dict:
        item = point(k, net)
        item["open_position_pnl_pct"] = open_pnl
        item["selection_value"] = net - 0.5 * max(0.0, -open_pnl)
        return item

    points = [
        with_open(0.2, 100.0, -100.0),
        with_open(0.25, 90.0, -20.0),
        with_open(0.3, 80.0, 0.0),
        with_open(0.35, 70.0, 0.0),
        with_open(0.4, 60.0, 0.0),
    ]
    plateau = select_plateau(
        points,
        PlateauConfig(plateau_window=3, plateau_stability_penalty=0.5, open_loss_penalty=0.5),
    )
    assert plateau is not None
    assert plateau["k_left"] == 0.25
    assert plateau["k_right"] == 0.35


def test_prior_overlap_detects_band_and_mismatch() -> None:
    overlap = prior_overlap(
        {"k_left": 0.6, "k_right": 0.8, "k_star": 0.7, "mean_net_return_pct": 1.0}
    )
    assert overlap["matches"] is True
    assert overlap["overlap_left"] == pytest.approx(0.65)
    assert overlap["overlap_right"] == pytest.approx(0.8)
    assert overlap["contains_anchor"] is True
    assert overlap["k_star_relation"] == "inside_prior"

    mismatch = prior_overlap(
        {"k_left": 0.9, "k_right": 1.1, "k_star": 1.0, "mean_net_return_pct": 1.0}
    )
    assert mismatch["matches"] is False
    assert mismatch["k_star_relation"] == "above_prior"


def test_front_running_adjusts_round_number_downward() -> None:
    config = PlateauConfig(front_run_offset_pct=0.2, front_run_band_pct=0.08)
    adjusted = front_running_adjust(3.0, 2.0, 0.2, config)
    assert adjusted["adjusted"] is True
    assert adjusted["threshold_pct"] == 3.0
    assert adjusted["d_exec_pct"] == pytest.approx(2.8)

    untouched = front_running_adjust(2.5, 2.0, 0.2, config)
    assert untouched["adjusted"] is False
    assert untouched["d_exec_pct"] == pytest.approx(2.5)

    blocked = front_running_adjust(2.0, 2.0, 1.0, config)
    assert blocked["adjusted"] is False
    assert "安全底线" in str(blocked["reason"])


def test_build_live_output_converts_k_star_to_executable_step() -> None:
    live = build_live_output(
        k_star=1.5,
        latest_atr_pct=2.0,
        latest_price=100.0,
        friction_pct=0.2,
        k_min_safe=0.2,
        config=PlateauConfig(front_run_offset_pct=0.2, front_run_band_pct=0.08),
    )
    assert live["d_raw_pct"] == pytest.approx(3.0)
    assert live["d_exec_pct"] == pytest.approx(2.8)
    assert live["k_exec"] == pytest.approx(1.4)
    assert live["d_exec_abs"] == pytest.approx(2.8)
    assert live["breakout"]["stretch_step_pct"] == pytest.approx(3.1)


def trading_days(count: int) -> list[str]:
    days = []
    current = date(2025, 1, 2)
    while len(days) < count:
        if current.weekday() < 5:
            days.append(current.isoformat())
        current += timedelta(days=1)
    return days


def intraday_times() -> list[str]:
    times = []
    current = datetime(2025, 1, 2, 9, 35)
    while current <= datetime(2025, 1, 2, 11, 30):
        times.append(current.strftime("%H:%M"))
        current += timedelta(minutes=5)
    current = datetime(2025, 1, 2, 13, 5)
    while current <= datetime(2025, 1, 2, 15, 0):
        times.append(current.strftime("%H:%M"))
        current += timedelta(minutes=5)
    return times


def make_scan_bars(days: list[str]) -> tuple[list[dict], list[dict]]:
    times = intraday_times()
    daily = []
    bars_5m = []
    for day in days:
        daily.append(
            {
                "trading_day": day,
                "open": 100.0,
                "high": 102.0,
                "low": 98.0,
                "close": 100.0,
            }
        )
        for time in times:
            bars_5m.append(
                {
                    "timestamp": f"{day} {time}",
                    "trading_day": day,
                    "open": 100.0,
                    "high": 103.0,
                    "low": 97.0,
                    "close": 100.0,
                }
            )
    return bars_5m, daily


def test_run_plateau_scan_returns_chart_ready_payload() -> None:
    days = trading_days(40)
    bars_5m, daily = make_scan_bars(days)
    config = make_config(
        capital=100_000,
        k_start=0.2,
        k_end=1.0,
        k_step=0.1,
        plateau_window=3,
        mode="dynamic",
    )
    result = run_plateau_scan(bars_5m, daily, config)
    assert len(result["curve"]) == 9
    assert len(result["k_values"]) == 9
    assert result["summary"]["trading_days"] == 40
    assert result["summary"]["mean_atr_pct"] == pytest.approx(4.0)
    assert result["summary"]["k_min_safe"] == pytest.approx(0.125)
    assert result["plateau"] is not None
    assert result["live"] is not None
    assert result["live"]["k_star"] == result["plateau"]["k_star"]
    assert result["prior_validation"]["matches"] in {True, False}
    assert all(0.0 <= item["net_return_pct"] or item["loops"] >= 0 for item in result["curve"])


def test_run_plateau_scan_holdout_uses_in_sample_only_for_selection() -> None:
    days = trading_days(60)
    bars_5m, daily = make_scan_bars(days)
    config = make_config(
        capital=100_000,
        k_start=0.2,
        k_end=1.0,
        k_step=0.1,
        plateau_window=3,
        holdout_ratio=0.3,
    )
    result = run_plateau_scan(bars_5m, daily, config)
    assert result["summary"]["in_sample_days"] == 42
    assert result["summary"]["oos_days"] == 18
    assert result["summary"]["total_days"] == 60
    assert result["holdout"]["enabled"] is True
    assert result["holdout"]["k_star"] == result["plateau"]["k_star"]
    assert result["holdout"]["net_return_pct"] is not None
    assert result["data"]["oos_start"] == days[42]
    assert result["data"]["end"] == days[41]


def test_run_plateau_scan_marks_all_forbidden_without_live_output() -> None:
    days = trading_days(40)
    bars_5m, daily = make_scan_bars(days)
    config = PlateauConfig(
        capital=10_000,
        shares_per_grid=1,
        fee=0.025,
        min_fee=5,
        friction_pct=2.0,
        k_start=0.2,
        k_end=1.0,
        k_step=0.1,
        plateau_window=3,
        holdout_ratio=0.0,
        price_limit_pct=0.0,
    )
    result = run_plateau_scan(bars_5m, daily, config)
    assert result["summary"]["all_forbidden"] is True
    assert result["plateau"] is None
    assert result["live"] is None
    assert "安全底线" in str(result["summary"]["live_unavailable_reason"])


def test_run_plateau_scan_rejects_empty_data() -> None:
    with pytest.raises(InsufficientPlateauDataError):
        run_plateau_scan([], [], PlateauConfig())
