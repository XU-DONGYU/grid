from __future__ import annotations

from grid_analyzer.constants import STAMP_TAX


def commission(amount: float, fee_pct: float, min_fee: float = 0.0) -> float:
    """单笔佣金 = max(金额 × 费率, 最低佣金)。"""
    if amount <= 0:
        return 0.0
    return max(amount * fee_pct / 100.0, min_fee)

def round_trip_cost_pct(amount: float, fee_pct: float, min_fee: float = 0.0) -> float:
    """每格往返成本率（%）= (买入佣金 + 卖出佣金 + 卖出印花税) / 金额 × 100。"""
    if amount <= 0:
        return 0.0
    buy = commission(amount, fee_pct, min_fee)
    sell = commission(amount, fee_pct, min_fee)
    total = buy + sell + amount * STAMP_TAX
    return total / amount * 100.0
