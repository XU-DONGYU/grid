from __future__ import annotations

from grid_analyzer.utils.stats import linreg_slope


def compute_trend(klines: list[dict]) -> tuple[float, float]:
    """返回 (20日趋势%, 60日趋势%)。"""
    closes = [k["close"] for k in klines]
    res = {}
    for name, n in (("t20", 20), ("t60", 60)):
        vals = closes[-min(n, len(closes)):]
        if not vals or vals[0] <= 0:
            res[name] = 0.0
            continue
        slope = linreg_slope(vals)
        res[name] = slope * (len(vals) - 1) / vals[0] * 100
    return res["t20"], res["t60"]
