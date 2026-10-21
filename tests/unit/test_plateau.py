from __future__ import annotations

import math
from datetime import date, datetime, timedelta

import pytest

from grid_analyzer.backtest.plateau import (
    AtrPoint,
    InsufficientPlateauDataError,
    PlateauConfig,
    _build_day_steps,
    _DayStep,
    build_live_output,
    compute_atr_series,
    detect_islands,
    effective_friction_pct,
    front_running_adjust,
    plateau_k_values,
    prior_overlap,
    run_plateau_scan,
    safe_k_floor,
    select_plateau,
    simulate_k,
)


def point(k: float, value: float) -> dict:
    return {
        "k": k,
        "net_return_pct": value,
        "loops": 1,
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


def test_plateau_k_values_default_range() -> None:
    values = plateau_k_values(0.20, 2.50, 0.05)
    assert len(values) == 47
    assert values[0] == 0.2
    assert values[-1] == 2.5


def test_safe_k_floor_and_friction() -> None:
    config = PlateauConfig(grid_amount=10_000, fee=0.025, min_fee=5, spread_pct=0.05)
    friction = effective_friction_pct(config)
    assert friction == pytest.approx(0.05 * 2 + 0.05 + 0.05)
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
    result = simulate_k(
        bars_by_day,
        day_steps,
        PlateauConfig(grid_amount=10_000, friction_pct=0.1),
        friction_pct=0.1,
    )
    assert result["loops"] == 1
    assert result["open_position_count"] == 0
    assert result["net_return_pct"] == pytest.approx((100 / 98 - 1) * 100 - 0.1)
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
    result = simulate_k(
        bars_by_day,
        day_steps,
        PlateauConfig(grid_amount=10_000, friction_pct=0.1),
        friction_pct=0.1,
    )
    assert result["loops"] == 0
    assert result["open_position_count"] == 0


def test_static_mode_uses_percentage_step() -> None:
    day_steps = {
        "2025-01-02": step("2025-01-02", 2.0),
        "2025-01-03": step("2025-01-03", 2.0),
    }
    bars_by_day = {
        "2025-01-02": [bar("2025-01-02", "09:35", 100, 100, 101, 97.9)],
        "2025-01-03": [bar("2025-01-03", "09:35", 100, 100, 101, 99)],
    }
    result = simulate_k(
        bars_by_day,
        day_steps,
        PlateauConfig(grid_amount=10_000, friction_pct=0.1, mode="static_mean"),
        friction_pct=0.1,
    )
    assert result["loops"] == 1
    assert result["net_return_pct"] == pytest.approx((100 / 98 - 1) * 100 - 0.1)


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
    result = simulate_k(
        bars_by_day,
        day_steps,
        PlateauConfig(grid_amount=10_000, max_positions=2, friction_pct=0.1),
        friction_pct=0.1,
    )
    assert result["loops"] == 4
    assert result["max_positions_used"] == 2
    assert result["max_positions"] == 2
    assert result["capital_return_pct"] == pytest.approx(result["net_return_pct"] / 2)


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
    config = PlateauConfig(
        grid_amount=100_000,
        fee=0.0,
        min_fee=0.0,
        spread_pct=0.0,
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


def test_run_plateau_scan_marks_all_forbidden_without_live_output() -> None:
    days = trading_days(40)
    bars_5m, daily = make_scan_bars(days)
    config = PlateauConfig(
        grid_amount=100,
        fee=0.025,
        min_fee=5,
        k_start=0.2,
        k_end=1.0,
        k_step=0.1,
        plateau_window=3,
    )
    result = run_plateau_scan(bars_5m, daily, config)
    assert result["summary"]["all_forbidden"] is True
    assert result["plateau"] is None
    assert result["live"] is None
    assert "安全底线" in str(result["summary"]["live_unavailable_reason"])


def test_run_plateau_scan_rejects_empty_data() -> None:
    with pytest.raises(InsufficientPlateauDataError):
        run_plateau_scan([], [], PlateauConfig())
