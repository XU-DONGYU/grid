from __future__ import annotations


def percentile_rank(series: list[float], value: float) -> float:
    """value 在 series 中的分位（0~100，平局取中位）。"""
    if not series:
        return 50.0
    below = sum(1 for x in series if x < value)
    equal = sum(1 for x in series if x == value)
    return (below + equal * 0.5) / len(series) * 100.0

def ema(values: list[float], period: int) -> float:
    if not values:
        return 0.0
    period = max(1, min(period, len(values)))
    k = 2.0 / (period + 1)
    out = values[0]
    for v in values[1:]:
        out = v * k + out * (1 - k)
    return out

def linreg_slope(vals: list[float]) -> float:
    n = len(vals)
    if n < 2:
        return 0.0
    x_mean = (n - 1) / 2
    y_mean = sum(vals) / n
    num = sum((i - x_mean) * (vals[i] - y_mean) for i in range(n))
    den = sum((i - x_mean) ** 2 for i in range(n))
    return num / den if den else 0.0
