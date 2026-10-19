from __future__ import annotations

import app


def test_commission_and_round_trip_cost() -> None:
    assert app.commission(100, 0.025, 5) == 5
    assert app.commission(100_000, 0.025, 5) == 25

    cost_pct = app.round_trip_cost_pct(10_000, 0.025, 5)
    assert cost_pct == 0.15


def test_design_grid_normal_case() -> None:
    grid = app.design_grid(
        95,
        105,
        100,
        1_000_000,
        sigma_daily=0.015,
        atr_pct=2.5,
        spread_pct=0.05,
        fee_pct=0.025,
        gap_ratio=1.2,
        sigma_mult=1.0,
        atr_anchor=0.7,
        gap_cap=0.08,
        min_fee=5,
    )
    assert grid["shares_per_grid"] > 0
    assert grid["levels"] == sorted(grid["levels"])
    assert grid["capital_required"] <= grid["capital"]
    assert grid["capital_utilization_pct"] <= 100
    assert grid["capital_constrained"] is False


def test_design_grid_auto_widens_when_capital_is_tight() -> None:
    grid = app.design_grid(
        95.887,
        112.563,
        100,
        21_000,
        sigma_daily=0.015,
        atr_pct=2.136,
        spread_pct=0.05,
        fee_pct=0.025,
        gap_ratio=1.2,
        sigma_mult=1.0,
        atr_anchor=0.7,
        gap_cap=0.08,
        min_fee=5,
    )
    assert grid["shares_per_grid"] > 0
    assert grid["capital_constrained"] is True
    assert grid["gap_pct"] > 8.0


def test_design_grid_returns_zero_shares_when_one_lot_is_unaffordable() -> None:
    grid = app.design_grid(
        95,
        105,
        100,
        10_000,
        sigma_daily=0.015,
        atr_pct=2.5,
        spread_pct=0.05,
        fee_pct=0.025,
        gap_ratio=1.2,
        sigma_mult=1.0,
        atr_anchor=0.7,
        gap_cap=0.08,
        min_fee=5,
    )
    assert grid["shares_per_grid"] == 0


def test_build_grids_single_mode(fixture_600000: dict) -> None:
    payload = fixture_600000
    klines = payload["klines"][-120:]
    main, aux, axis, vol = app.build_grids(
        klines,
        payload["quote"]["price"],
        100_000,
        single=True,
        main_ratio=1.0,
        spread_pct=0.05,
        fee_pct=0.025,
        min_fee=5,
    )
    assert main["shares_per_grid"] > 0
    assert aux["shares_per_grid"] == 0
    assert axis["recommended"] > 0
    assert vol["atr_pct"] > 0


def test_build_grids_dual_mode(fixture_002541: dict) -> None:
    payload = fixture_002541
    klines = payload["klines"][-120:]
    main, aux, _, _ = app.build_grids(
        klines,
        payload["quote"]["price"],
        100_000,
        single=False,
        main_ratio=0.7,
        spread_pct=0.05,
        fee_pct=0.025,
        min_fee=5,
    )
    assert main["shares_per_grid"] > 0
    assert aux["shares_per_grid"] > 0
    assert main["lower"] <= aux["lower"] <= aux["upper"] <= main["upper"]
