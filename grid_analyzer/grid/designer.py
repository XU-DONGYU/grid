from __future__ import annotations

from fastapi import HTTPException

from grid_analyzer.constants import AUX_GAP_CAP, MAIN_GAP_CAP
from grid_analyzer.grid.spacing import design_grid
from grid_analyzer.indicators.axis import compute_axis
from grid_analyzer.indicators.volatility import compute_volatility


def build_grids(klines: list[dict], price: float, capital: float, single: bool,
                main_ratio: float, spread_pct: float, fee_pct: float,
                min_fee: float, history_closes: list[float] | None = None,
                gap_scale: float = 1.0
                ) -> tuple[dict, dict, dict, dict]:
    """基于给定K线构建主/辅网格，返回 (主网格, 辅网格, 中轴, 波动率)。"""
    if not klines:
        raise HTTPException(400, "历史数据为空，无法构建网格")
    closes = [k["close"] for k in klines]
    axis = compute_axis(closes)
    vol = compute_volatility(klines, history_closes=history_closes or closes)
    sigma_daily = vol["sigma_daily_pct"] / 100

    window60 = klines[-min(60, len(klines)):]
    low60 = min(k["low"] for k in window60)
    high60 = max(k["high"] for k in window60)
    lower = low60 * 1.02
    upper = high60 * 0.98
    if upper / lower - 1 < 0.15:
        lower, upper = axis["recommended"] * 0.92, axis["recommended"] * 1.08
    if price > upper:
        upper = price * 1.04
    if price < lower:
        lower = price * 0.96

    main_capital = capital * (1.0 if single else main_ratio)
    aux_capital = 0 if single else capital * (1 - main_ratio)

    main_grid = design_grid(
        lower, upper, price, main_capital, sigma_daily,
        vol["atr_pct"], spread_pct, fee_pct, 1.2, 1.0, 0.70,
        MAIN_GAP_CAP, min_fee, gap_scale,
    )

    if single:
        aux_grid = {**main_grid, "capital": 0, "shares_per_grid": 0, "grid_cost": 0,
                    "capital_required": 0, "capital_utilization_pct": 0}
    else:
        k20 = klines[-min(20, len(klines)):]
        low20 = min(k["low"] for k in k20)
        high20 = max(k["high"] for k in k20)
        al = max(axis["recommended"] * 0.92, low20 * 1.01)
        au = min(axis["recommended"] * 1.08, high20 * 0.99)
        if au / al - 1 < 0.06:
            al, au = axis["recommended"] * 0.94, axis["recommended"] * 1.06
        al = max(al, main_grid["lower"])
        au = min(au, main_grid["upper"])
        if au / al - 1 < 0.04:
            al = max(main_grid["lower"], axis["recommended"] * 0.98)
            au = min(main_grid["upper"], axis["recommended"] * 1.02)
        try:
            aux_grid = design_grid(
                al, au, price, aux_capital, sigma_daily,
                vol["atr_pct"], spread_pct, fee_pct, 1.0, 0.7, 0.55,
                AUX_GAP_CAP, min_fee, gap_scale,
            )
        except HTTPException:
            aux_grid = {**main_grid, "capital": aux_capital, "shares_per_grid": 0,
                        "grid_cost": 0, "capital_required": 0, "capital_utilization_pct": 0}

    return main_grid, aux_grid, axis, vol
