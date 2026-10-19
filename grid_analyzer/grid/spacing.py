from __future__ import annotations

import math

from fastapi import HTTPException

from grid_analyzer.constants import BUFFER
from grid_analyzer.utils.finance import commission, round_trip_cost_pct


def design_grid(lower: float, upper: float, price: float, capital: float,
                sigma_daily: float, atr_pct: float, spread_pct: float,
                fee_pct: float, gap_ratio: float, sigma_mult: float,
                atr_anchor: float, gap_cap: float, min_fee: float = 0.0,
                gap_scale: float = 1.0) -> dict:
    """
    设计一套等比网格。
    gap_ratio: 成本门槛倍数（主1.2 / 辅1.0）
    sigma_mult: 日波动率倍数（主1.0 / 辅0.7）
    atr_anchor: ATR% 锚定倍数（主0.70 / 辅0.55，对应 file.md 的 0.65~0.80）
    """
    if upper <= lower or price <= 0 or capital <= 0:
        raise HTTPException(400, "网格区间计算异常，数据不足或价格异常")

    # 用偏保守的每格金额估算最低成本门槛（最低佣金对小资金影响很大）
    ref_amount = max(capital / 20.0, price * 100)
    rt_pct = round_trip_cost_pct(ref_amount, fee_pct, min_fee)
    min_gap = spread_pct / 100 + rt_pct / 100 + BUFFER

    atr_gap = atr_anchor * atr_pct / 100.0
    sigma_gap = sigma_mult * sigma_daily
    gap = max(gap_ratio * min_gap, atr_gap, sigma_gap) * max(gap_scale, 0.01)
    gap = min(gap, gap_cap)
    gap = max(gap, min_gap)
    if gap <= 0:
        gap = 0.003

    def make_levels(g: float) -> list[float]:
        out: list[float] = []
        p = lower
        guard = 0
        while p <= upper * (1 + 1e-9) and guard < 500:
            out.append(round(p, 3))
            p *= (1 + g)
            guard += 1
        if not out:
            raise HTTPException(400, "网格档位生成失败，请扩大区间")
        if out[-1] < upper * (1 - 1e-9):
            out.append(round(upper, 3))
        out = sorted(set(out))
        if len(out) < 2:
            raise HTTPException(400, "网格档位不足，请扩大区间或放宽资金")
        return out

    levels = make_levels(gap)
    buy_cnt = len(levels) - 1  # 最高档不买入（防踏空保护）
    per_grid_budget = capital / buy_cnt
    shares = math.floor(per_grid_budget / (price * (1 + fee_pct / 100.0)) / 100) * 100
    capital_constrained = False

    # 资金不足一手时，按“最多可买档位数”反推所需最小间距，自动拉宽
    if shares <= 0:
        lot_cost = price * 100 + commission(price * 100, fee_pct, min_fee)
        max_buy_levels = int(capital // lot_cost)
        if max_buy_levels >= 1:
            required_gap = (upper / lower) ** (1.0 / max_buy_levels) - 1
            if required_gap > gap:
                gap = max(required_gap, min_gap)
                levels = make_levels(gap)
                capital_constrained = True
                buy_cnt = len(levels) - 1
                per_grid_budget = capital / buy_cnt
                shares = math.floor(
                    per_grid_budget / (price * (1 + fee_pct / 100.0)) / 100
                ) * 100

    shares = max(shares, 0)
    grid_cost = shares * price
    capital_required = grid_cost * buy_cnt

    return {
        "lower": levels[0],
        "upper": levels[-1],
        "gap_pct": gap * 100,
        "atr_gap_pct": atr_gap * 100,
        "levels": levels,
        "capital": capital,
        "shares_per_grid": shares,
        "grid_cost": grid_cost,
        "capital_required": capital_required,
        "capital_utilization_pct": capital_required / capital * 100 if capital else 0,
        "round_trip_cost_pct": rt_pct,
        "min_gap_pct": min_gap * 100,
        "capital_constrained": capital_constrained,
        "gap_scale": gap_scale,
    }
