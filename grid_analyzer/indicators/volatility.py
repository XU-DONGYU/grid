from __future__ import annotations

import math
import statistics

from grid_analyzer.constants import TRADING_DAYS
from grid_analyzer.utils.stats import ema, percentile_rank


def compute_atr(klines: list[dict], period: int = 14) -> float:
    """Wilder ATR，含跳空缺口。"""
    if not klines:
        return 0.0
    if len(klines) == 1:
        return klines[0]["high"] - klines[0]["low"]
    trs = []
    prev_close = klines[0]["close"]
    for k in klines[1:]:
        tr = max(k["high"] - k["low"], abs(k["high"] - prev_close), abs(k["low"] - prev_close))
        trs.append(tr)
        prev_close = k["close"]
    if not trs:
        return 0.0
    n = min(period, len(trs))
    atr = sum(trs[:n]) / n
    for tr in trs[n:]:
        atr = (atr * (n - 1) + tr) / n
    return atr

def bollinger(closes: list[float], period: int = 20) -> dict:
    n = min(period, len(closes))
    if n <= 0:
        return {"mid": 0.0, "sd": 0.0, "upper": 0.0, "lower": 0.0, "bandwidth_pct": 0.0}
    window = closes[-n:]
    mid = sum(window) / n
    sd = statistics.pstdev(window) if n > 1 else 0.0
    upper = mid + 2 * sd
    lower = mid - 2 * sd
    bandwidth_pct = (upper - lower) / mid * 100.0 if mid else 0.0
    return {"mid": mid, "sd": sd, "upper": upper, "lower": lower, "bandwidth_pct": bandwidth_pct}

def bollinger_bandwidth_series(closes: list[float], period: int = 20) -> list[float]:
    if len(closes) < 2:
        return []
    n = min(period, len(closes))
    series = []
    for end in range(n, len(closes) + 1):
        window = closes[end - n:end]
        mid = sum(window) / n
        if mid <= 0:
            continue
        sd = statistics.pstdev(window) if n > 1 else 0.0
        series.append(4 * sd / mid * 100.0)
    return series

def compute_volatility(klines: list[dict], history_closes: list[float] | None = None) -> dict:
    closes = [k["close"] for k in klines]
    rets = [(closes[i] - closes[i - 1]) / closes[i - 1]
            for i in range(1, len(closes)) if closes[i - 1] > 0]
    sigma_daily = statistics.stdev(rets) if len(rets) > 1 else 0.0
    atr = compute_atr(klines)
    last_price = closes[-1]
    boll = bollinger(closes, 20)

    hist = history_closes or closes
    bw_series = bollinger_bandwidth_series(hist, 20)
    bw_pct = boll["bandwidth_pct"]
    bw_rank = percentile_rank(bw_series, bw_pct) if bw_series else 50.0

    roll_sigmas = []
    for end in range(20, len(rets) + 1):
        window = rets[end - 20:end]
        if len(window) > 1:
            roll_sigmas.append(statistics.stdev(window))
    vol_of_vol = statistics.stdev(roll_sigmas) * math.sqrt(TRADING_DAYS) * 100 if len(roll_sigmas) > 1 else 0.0

    ema20 = ema(closes, 20)
    atr14 = compute_atr(klines, 14)
    kelt_upper = ema20 + 2 * atr14
    kelt_lower = ema20 - 2 * atr14
    ttm_squeeze = bool(boll["upper"] < kelt_upper and boll["lower"] > kelt_lower)
    squeeze = bool(bw_rank <= 10.0 or ttm_squeeze)

    return {
        "sigma_daily_pct": sigma_daily * 100,
        "sigma_annual_pct": sigma_daily * math.sqrt(TRADING_DAYS) * 100,
        "vol_of_vol_pct": vol_of_vol,
        "atr": atr,
        "atr_pct": (atr / last_price * 100) if last_price else 0,
        "boll_upper": boll["upper"],
        "boll_lower": boll["lower"],
        "boll_width_pct": bw_pct,
        "boll_width_percentile": bw_rank,
        "squeeze": squeeze,
        "ttm_squeeze": ttm_squeeze,
        "keltner_upper": kelt_upper,
        "keltner_lower": kelt_lower,
    }
