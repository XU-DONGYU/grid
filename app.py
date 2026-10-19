# -*- coding: utf-8 -*-
"""
A股网格交易参数分析器 · FastAPI 后端
===================================
接口：GET /api/analyze?code=&capital=&fee=&main_ratio=&min_fee=&init_position=&stop_loss=
- 行情代理：腾讯财经实时行情 + 前复权日K线（约250日，图表/回测取最近120日）
- 计算引擎：中轴 / 波动率 / 布林带宽分位 / TTM Squeeze / ATR / 网格区间 / 网格间距 / 资金分配
- 费用引擎：单边佣金（含最低佣金）+ 印花税0.05%（卖出）
- 回测引擎：事件驱动、T+1、现金约束、跳空处理、破网止损、逐日权益曲线
- 规则引擎：流动性 / 趋势 / 挤压 / 适配度 / 风险提示

部署：
    pip install -r requirements.txt
    uvicorn app:app --host 0.0.0.0 --port 8000
"""
import math
import re
import statistics

import requests
import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from pathlib import Path

app = FastAPI(title="A股网格交易参数分析器", version="2.1")


@app.middleware("http")
async def add_no_cache_headers(request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response

# ---------------- 常量 ----------------
STAMP_TAX = 0.0005      # 印花税（卖出）0.05%
BUFFER = 0.0015         # 最低间距门槛的缓冲 0.15%
TRADING_DAYS = 243      # 年化交易日数
MAIN_GAP_CAP = 0.08     # 主网格间距上限 8%
AUX_GAP_CAP = 0.04      # 辅助网格间距上限 4%
BACKTEST_DAYS = 120     # 展示与回测窗口


# ---------------- 工具函数 ----------------
def parse_code(code: str) -> tuple[str, str]:
    """识别市场前缀与6位代码。"""
    code = (code or "").strip().lower()
    m = re.match(r"^(sh|sz|bj)?(\d{6})$", code)
    if not m:
        raise HTTPException(400, "股票代码格式错误，请输入6位数字或带 sh/sz/bj 前缀，如 600000 / sz000001")
    prefix, digits = m.group(1), m.group(2)
    if not prefix:
        if digits[0] in "659":
            prefix = "sh"
        elif digits[0] in "023":
            prefix = "sz"
        elif digits[0] in "48":
            prefix = "bj"
        else:
            prefix = "sh"
    return prefix, digits


def fetch_quote(prefix: str, code: str) -> dict:
    """腾讯实时行情。"""
    url = f"https://qt.gtimg.cn/q={prefix}{code}"
    resp = requests.get(url, timeout=10)
    resp.encoding = "gbk"
    m = re.search(r'="(.*)"', resp.text)
    if not m or not m.group(1) or len(m.group(1).split("~")) < 50:
        raise HTTPException(404, f"未获取到 {prefix}{code} 的行情，请确认代码是否正确")
    parts = m.group(1).split("~")

    def num(idx: int) -> float:
        try:
            return float(parts[idx] or 0)
        except (ValueError, IndexError):
            return 0.0

    price = num(3)
    if price <= 0:
        raise HTTPException(404, f"未获取到 {prefix}{code} 的有效行情（可能已退市或停牌过久）")
    total_mv = num(45)   # 总市值（亿）
    float_mv = num(44)   # 流通市值（亿）
    if total_mv <= 0:
        total_mv = float_mv
    return {
        "name": parts[1],
        "code": parts[2],
        "price": price,
        "prev_close": num(4),
        "change": num(31),
        "change_pct": num(32),
        "high": num(33),
        "low": num(34),
        "amount_wan": num(37),      # 成交额（万元）
        "turnover_pct": num(38),
        "pe_ttm": num(39),
        "amplitude_pct": num(43),
        "total_mv": total_mv,
        "float_mv": float_mv,
        "bid": [{"p": num(9 + i * 2), "v": num(10 + i * 2)} for i in range(5)],
        "ask": [{"p": num(19 + i * 2), "v": num(20 + i * 2)} for i in range(5)],
    }


def fetch_kline(prefix: str, code: str, days: int = 250) -> list[dict]:
    """腾讯前复权日K线（date, open, close, high, low, volume）。"""
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={prefix}{code},day,,,{days},qfq"
    resp = requests.get(url, timeout=10)
    data = resp.json()
    node = (data.get("data") or {}).get(f"{prefix}{code}") or {}
    rows = node.get("qfqday") or node.get("day") or []
    if not rows:
        raise HTTPException(404, f"未获取到 {prefix}{code} 的历史K线数据")
    result = []
    for r in rows:
        try:
            result.append({
                "date": r[0],
                "open": float(r[1]),
                "close": float(r[2]),
                "high": float(r[3]),
                "low": float(r[4]),
                "volume": float(r[5] or 0),
            })
        except (ValueError, IndexError):
            continue
    return result


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


# ---------------- 指标计算 ----------------
def compute_axis(closes: list[float]) -> dict:
    if not closes:
        raise HTTPException(400, "历史数据为空，无法计算中轴")
    n20 = closes[-min(20, len(closes)):]
    n60 = closes[-min(60, len(closes)):]
    median60 = statistics.median(n60)
    return {
        "median60": median60,
        "mean60": sum(n60) / len(n60),
        "ma20": sum(n20) / len(n20),
        "ma60": sum(n60) / len(n60),
        "recommended": median60,
    }


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


def linreg_slope(vals: list[float]) -> float:
    n = len(vals)
    if n < 2:
        return 0.0
    x_mean = (n - 1) / 2
    y_mean = sum(vals) / n
    num = sum((i - x_mean) * (vals[i] - y_mean) for i in range(n))
    den = sum((i - x_mean) ** 2 for i in range(n))
    return num / den if den else 0.0


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


def fit_score(trend20: float, trend60: float, pct_b: float, atr_pct: float,
              squeeze: bool = False) -> int:
    score = 70
    a60 = abs(trend60)
    if a60 < 5:
        score += 15
    elif a60 <= 12:
        score += 5
    elif a60 <= 20:
        score -= 20
    else:
        score -= 35
    if 0.2 <= pct_b <= 0.8:
        score += 10
    elif pct_b < 0.05 or pct_b > 0.95:
        score -= 10
    if 1.5 <= atr_pct <= 4:
        score += 10
    elif atr_pct < 0.8:
        score -= 10
    elif atr_pct > 6:
        score -= 5
    if squeeze:
        score = min(score - 25, 45)
    return max(5, min(95, score))


def liquidity_grade(spread_pct: float, amount_wan: float) -> tuple[str, str]:
    """返回 (综合评级, 评级依据)。"""
    if spread_pct <= 0.15:
        s = "好"
    elif spread_pct <= 0.5:
        s = "中"
    else:
        s = "差"
    amt = amount_wan * 1e4
    if amt >= 3e8:
        a = "好"
    elif amt >= 1e8:
        a = "中"
    else:
        a = "差"
    if s == "差" or a == "差":
        grade = "差"
    elif s == "好" and a == "好":
        grade = "好"
    else:
        grade = "中"
    return grade, f"价差{s} / 成交额{a}"


# ---------------- 网格设计 ----------------
def design_grid(lower: float, upper: float, price: float, capital: float,
                sigma_daily: float, atr_pct: float, spread_pct: float,
                fee_pct: float, gap_ratio: float, sigma_mult: float,
                atr_anchor: float, gap_cap: float, min_fee: float = 0.0) -> dict:
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
    gap = max(gap_ratio * min_gap, atr_gap, sigma_gap)
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
    }


def build_grids(klines: list[dict], price: float, capital: float, single: bool,
                main_ratio: float, spread_pct: float, fee_pct: float,
                min_fee: float, history_closes: list[float] | None = None
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
        MAIN_GAP_CAP, min_fee,
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
                AUX_GAP_CAP, min_fee,
            )
        except HTTPException:
            aux_grid = {**main_grid, "capital": aux_capital, "shares_per_grid": 0,
                        "grid_cost": 0, "capital_required": 0, "capital_utilization_pct": 0}

    return main_grid, aux_grid, axis, vol


# ---------------- 回测引擎 ----------------
def _empty_backtest() -> dict:
    return {
        "rounds": 0,
        "buy_count": 0,
        "sell_count": 0,
        "net_profit": 0.0,
        "return_pct": 0.0,
        "annual_pct": 0.0,
        "max_holding_cnt": 0,
        "max_position_cost": 0.0,
        "max_drawdown_pct": 0.0,
        "end_holding": 0,
        "end_holding_qty": 0,
        "end_holding_value": 0.0,
        "end_cash": 0.0,
        "min_float_pnl": 0.0,
        "min_equity_pnl": 0.0,
        "total_fees": 0.0,
        "realized_pnl": 0.0,
        "unrealized_pnl": 0.0,
        "skipped_buys": 0,
        "stop_triggered": False,
        "stop_date": None,
        "stop_price": 0.0,
        "stop_fill_price": 0.0,
        "init_cost": 0.0,
        "turnover": 0.0,
        "equity_curve": [],
    }


def run_backtest(klines: list[dict], grid: dict, fee_pct: float,
                 min_fee: float = 0.0, init_position_pct: float = 0.0,
                 stop_loss_pct: float = 5.0) -> dict:
    """
    事件驱动回测。
    - 现金约束：买入必须由可用现金支付，现金不足则跳过该格买单
    - T+1：当日买入的仓位当日不可卖出
    - 跳空：以上一日收盘价为日内路径起点，处理隔夜跳空
    - 初始底仓：按首日开盘价真实扣款（默认 0，即中性零底仓启动）
    - 破网止损：价格击穿 lower×(1-stop_loss_pct%) 后清仓并停止交易
    """
    out = _empty_backtest()
    if not klines:
        return out
    capital = float(grid.get("capital") or 0)
    shares = int(grid.get("shares_per_grid") or 0)
    levels = list(grid.get("levels") or [])
    if capital <= 0 or shares <= 0 or len(levels) < 2:
        return out

    gap_frac = float(grid.get("gap_pct") or 0) / 100.0
    buyable = levels[:-1]
    cash = capital
    positions: dict[int, dict] = {}
    base_lot: dict | None = None
    total_fees = 0.0
    realized_pnl = 0.0
    turnover = 0.0
    buy_count = 0
    sell_count = 0
    rounds = 0
    skipped_buys = 0
    max_holding = 0
    max_position_cost = 0.0
    min_equity_pnl = 0.0
    min_unrealized_pnl = 0.0
    stop_triggered = False
    stop_date = None
    stop_fill_price = 0.0
    trading_stopped = False
    equity_curve: list[dict] = []

    stop_price = levels[0] * (1 - stop_loss_pct / 100.0) if stop_loss_pct and stop_loss_pct > 0 else None

    def holding_count() -> int:
        return len(positions) + (1 if base_lot else 0)

    def position_value(price: float) -> float:
        value = sum(p["shares"] * price for p in positions.values())
        if base_lot:
            value += base_lot["shares"] * price
        return value

    def cost_basis() -> float:
        value = sum(p["price"] * p["shares"] for p in positions.values())
        if base_lot:
            value += base_lot["price"] * base_lot["shares"]
        return value

    def update_high_water() -> None:
        nonlocal max_holding, max_position_cost
        max_holding = max(max_holding, holding_count())
        max_position_cost = max(max_position_cost, cost_basis())

    def do_buy(idx: int, day_idx: int) -> None:
        nonlocal cash, total_fees, turnover, buy_count, skipped_buys
        if idx in positions:
            return
        lv = buyable[idx]
        amount = lv * shares
        fee = commission(amount, fee_pct, min_fee)
        cost = amount + fee
        if cost > cash + 1e-9:
            skipped_buys += 1
            return
        cash -= cost
        total_fees += fee
        turnover += amount
        buy_count += 1
        positions[idx] = {"price": lv, "day": day_idx, "shares": shares, "buy_fee": fee}
        update_high_water()

    def do_sell(idx: int, fill: float, day_idx: int) -> None:
        nonlocal cash, total_fees, turnover, sell_count, rounds, realized_pnl
        pos = positions.pop(idx)
        amount = fill * pos["shares"]
        fee = commission(amount, fee_pct, min_fee)
        stamp = amount * STAMP_TAX
        proceeds = amount - fee - stamp
        cash += proceeds
        total_fees += fee + stamp
        turnover += amount
        sell_count += 1
        rounds += 1
        realized_pnl += proceeds - (pos["price"] * pos["shares"] + pos["buy_fee"])

    def do_sell_base(fill: float, day_idx: int) -> None:
        nonlocal cash, total_fees, turnover, sell_count, realized_pnl, base_lot
        if not base_lot:
            return
        lot = base_lot
        amount = fill * lot["shares"]
        fee = commission(amount, fee_pct, min_fee)
        stamp = amount * STAMP_TAX
        proceeds = amount - fee - stamp
        cash += proceeds
        total_fees += fee + stamp
        turnover += amount
        sell_count += 1
        realized_pnl += proceeds - (lot["price"] * lot["shares"] + lot["buy_fee"])
        base_lot = None

    def liquidate(fill: float, day_idx: int) -> None:
        for idx in sorted(list(positions.keys())):
            if positions[idx]["day"] < day_idx:
                do_sell(idx, fill, day_idx)
        if base_lot and base_lot["day"] < day_idx:
            do_sell_base(fill, day_idx)

    first_open = klines[0]["open"]
    if init_position_pct > 0 and first_open > 0:
        budget = capital * min(init_position_pct, 1.0)
        init_shares = math.floor(budget / (first_open * (1 + fee_pct / 100.0)) / 100) * 100
        if init_shares > 0:
            amount = first_open * init_shares
            fee = commission(amount, fee_pct, min_fee)
            cost = amount + fee
            if cost <= cash + 1e-9:
                cash -= cost
                total_fees += fee
                turnover += amount
                target = next(
                    (lv for lv in levels if lv >= first_open * (1 + gap_frac)),
                    max(levels[-1], first_open * (1 + gap_frac)),
                )
                base_lot = {
                    "price": first_open,
                    "day": -1,
                    "shares": init_shares,
                    "buy_fee": fee,
                    "target": target,
                }
                buy_count += 1
                out["init_cost"] = cost
                update_high_water()

    prev_close: float | None = None

    def record_day(k: dict) -> None:
        nonlocal min_equity_pnl, min_unrealized_pnl
        close = k["close"]
        pv = position_value(close)
        equity = cash + pv
        min_equity_pnl = min(min_equity_pnl, equity - capital)
        unreal = sum((close - p["price"]) * p["shares"] for p in positions.values())
        if base_lot:
            unreal += (close - base_lot["price"]) * base_lot["shares"]
        min_unrealized_pnl = min(min_unrealized_pnl, unreal)
        equity_curve.append({
            "date": k["date"],
            "equity": round(equity, 2),
            "price": close,
            "position_value": round(pv, 2),
        })
        update_high_water()

    for day_idx, k in enumerate(klines):
        o, c, h, l = k["open"], k["close"], k["high"], k["low"]

        if trading_stopped:
            if positions or base_lot:
                liquidate(o, day_idx)
            record_day(k)
            prev_close = c
            continue

        # 开盘即跌破止损线：按开盘价清仓
        if stop_price is not None and o <= stop_price:
            liquidate(o, day_idx)
            trading_stopped = True
            stop_triggered = True
            stop_date = k["date"]
            stop_fill_price = o
            record_day(k)
            prev_close = c
            continue

        # 开盘时，已持有仓位的卖价若已低于开盘价（含 T+1 解锁与隔夜跳空），立即按开盘价卖出
        for i in range(len(buyable)):
            pos = positions.get(i)
            if pos and pos["day"] < day_idx and levels[i + 1] <= o:
                do_sell(i, o, day_idx)
        if base_lot and base_lot["day"] < day_idx and base_lot["target"] <= o:
            do_sell_base(o, day_idx)

        start = prev_close if prev_close is not None else o
        if c >= o:
            path = [start, o, l, h, c]
        else:
            path = [start, o, h, l, c]

        stopped_today = False
        for prev, p in zip(path, path[1:]):
            if p < prev:
                # 下跌段：先处理止损线以上的买单，再触发止损
                if stop_price is not None and p <= stop_price < prev:
                    for i in range(len(buyable) - 1, -1, -1):
                        lv = buyable[i]
                        if stop_price < lv <= prev and i not in positions:
                            do_buy(i, day_idx)
                    liquidate(stop_price, day_idx)
                    trading_stopped = True
                    stop_triggered = True
                    stop_date = k["date"]
                    stop_fill_price = stop_price
                    stopped_today = True
                    break
                # 正常下跌：价格穿越的每个档位都可以买入，直至现金耗尽
                for i in range(len(buyable) - 1, -1, -1):
                    lv = buyable[i]
                    if p <= lv <= prev and i not in positions:
                        do_buy(i, day_idx)
            elif p > prev:
                # 上涨段：卖出已持有且满足 T+1 的档位
                for i in range(len(buyable)):
                    target = levels[i + 1]
                    pos = positions.get(i)
                    if pos and pos["day"] < day_idx and prev < target <= p:
                        do_sell(i, target, day_idx)
                if base_lot and base_lot["day"] < day_idx:
                    target = base_lot["target"]
                    if prev < target <= p:
                        do_sell_base(target, day_idx)

        record_day(k)
        prev_close = c
        if stopped_today:
            # 当日买入的仓位受 T+1 限制，留待后续交易日清仓
            continue

    final_close = klines[-1]["close"]
    final_pv = position_value(final_close)
    final_equity = cash + final_pv
    net_profit = final_equity - capital
    n_days = len(klines)

    peak = capital
    max_drawdown_pct = 0.0
    for pt in equity_curve:
        eq = pt["equity"]
        peak = max(peak, eq)
        if peak > 0:
            max_drawdown_pct = max(max_drawdown_pct, (peak - eq) / peak * 100)

    if capital > 0 and final_equity > 0 and n_days > 0:
        annual_pct = ((final_equity / capital) ** (TRADING_DAYS / n_days) - 1) * 100
    else:
        annual_pct = -100.0 if final_equity <= 0 else 0.0

    out.update({
        "rounds": rounds,
        "buy_count": buy_count,
        "sell_count": sell_count,
        "net_profit": net_profit,
        "return_pct": net_profit / capital * 100 if capital else 0,
        "annual_pct": annual_pct,
        "max_holding_cnt": max_holding,
        "max_position_cost": max_position_cost,
        "max_drawdown_pct": max_drawdown_pct,
        "end_holding": holding_count(),
        "end_holding_qty": sum(p["shares"] for p in positions.values())
        + (base_lot["shares"] if base_lot else 0),
        "end_holding_value": final_pv,
        "end_cash": cash,
        "min_float_pnl": min_unrealized_pnl,
        "min_equity_pnl": min_equity_pnl,
        "total_fees": total_fees,
        "realized_pnl": realized_pnl,
        "unrealized_pnl": net_profit - realized_pnl,
        "skipped_buys": skipped_buys,
        "stop_triggered": stop_triggered,
        "stop_date": stop_date,
        "stop_price": stop_price or 0.0,
        "stop_fill_price": stop_fill_price,
        "turnover": turnover,
        "equity_curve": equity_curve,
    })
    return out


# ---------------- 风险规则 ----------------
def collect_risks(d: dict) -> list[str]:
    risks: list[str] = []
    q = d["quote"]
    t = d["trend"]
    v = d["volatility"]
    liq = d["liquidity"]
    g1, g2 = d["main_grid"], d["aux_grid"]
    axis = d["axis"]
    single = d["params"]["single_grid"]
    stop_loss = d["params"].get("stop_loss_pct", 0)

    if abs(t["trend60_pct"]) >= 12 and abs(t["trend20_pct"]) >= 8 and t["trend20_pct"] * t["trend60_pct"] > 0:
        risks.append(f"近60日趋势 {t['trend60_pct']:+.1f}%，近20日趋势 {t['trend20_pct']:+.1f}%，呈单边行情，网格易单边接飞刀或提前卖飞，建议谨慎")
    elif abs(t["trend20_pct"]) >= 8:
        risks.append(f"近20日短期趋势明显（{t['trend20_pct']:+.1f}%），注意区间可能被击穿")

    if v.get("squeeze"):
        reason = "TTM Squeeze 双通道内嵌" if v.get("ttm_squeeze") else f"带宽处于历史 {v.get('boll_width_percentile', 50):.0f}% 分位"
        risks.append(f"布林带宽 {v.get('boll_width_pct', 0):.2f}%（{reason}），疑似极度挤压。挤压期网格套利空间被摩擦成本吞噬，且随时可能单边突破，属于开网格禁区")

    off = q["price"] / axis["recommended"] - 1
    if abs(off) > 0.2:
        risks.append(f"当前价偏离推荐中轴 {off * 100:+.0f}%，可能已进入超跌/超涨区，区间参考性下降")
    if v["atr_pct"] > 6:
        risks.append(f"ATR 高达 {v['atr_pct']:.1f}%，波动剧烈，网格单格利润可能被滑点侵蚀")
    if v["atr_pct"] < 0.8:
        risks.append(f"ATR 仅 {v['atr_pct']:.2f}%，波动过小，网格触发频率低，资金利用率不高")
    if v.get("vol_of_vol_pct", 0) >= 30:
        risks.append(f"波动率方差 {v['vol_of_vol_pct']:.1f}%（年化），波动率自身离散度高，市场易由震荡切换为单边，建议拉宽格距或降低仓位")
    if liq["grade"] == "差":
        risks.append("流动性评级为「差」，盘口薄、价差大，网格成交滑点风险高")
    if g1.get("capital_constrained"):
        risks.append(f"资金约束：主网格为保证每格至少一手，间距被拉宽至 {g1['gap_pct']:.1f}%，仅 {len(g1['levels']) - 1} 个可买档位，网格套利属性弱化，建议增加资金或选择低价标的")
    if not single and g2.get("capital_constrained"):
        risks.append(f"资金约束：辅助网格间距被拉宽至 {g2['gap_pct']:.1f}%，仅 {len(g2['levels']) - 1} 个可买档位")
    if g1["grid_cost"] > liq["bid_depth_yuan"] * 0.2 and liq["bid_depth_yuan"] > 0:
        risks.append(f"主网格每格金额 {g1['grid_cost'] / 1e4:.1f} 万 超过五档买盘承接的 20%，大单卖出可能砸穿盘口")
    if not single and g2["grid_cost"] > liq["bid_depth_yuan"] * 0.2 and liq["bid_depth_yuan"] > 0:
        risks.append(f"辅助网格每格金额 {g2['grid_cost'] / 1e4:.1f} 万 超过五档买盘承接的 20%，冲击成本较高")
    if not stop_loss:
        risks.append("未启用破网止损：单边下跌时持仓与单笔跌幅双重放大，浮亏近似随价格偏离度平方增长，建议设置 3%~8% 的破网清仓阈值")
    else:
        for label, bt in (("主网格", d.get("backtest", {}).get("main")),
                          ("辅助网格", d.get("backtest", {}).get("aux"))):
            if bt and bt.get("stop_triggered"):
                risks.append(f"{label}在回测期内触发破网止损（{bt.get('stop_date') or '—'}，成交价 {bt.get('stop_fill_price', 0):.2f}），说明区间下沿曾被击穿，实盘需复核区间与止损阈值")
    return risks


# ---------------- 主接口 ----------------
@app.get("/api/analyze")
def analyze(
    code: str = Query(..., description="股票代码，如 600000 / sz000001"),
    capital: float = Query(100000, ge=1000, le=1e8, description="总资金（元）"),
    fee: float = Query(0.025, ge=0, le=0.3, description="单边佣金费率（%）"),
    min_fee: float = Query(5.0, ge=0, le=100, description="单笔最低佣金（元）"),
    main_ratio: float = Query(0.7, ge=0.5, le=1.0, description="主网格资金占比"),
    init_position: float = Query(0.0, ge=0, le=1.0, description="初始底仓占总资金比例，0=中性零底仓"),
    stop_loss: float = Query(5.0, ge=0, le=50, description="跌破网格下限后的清仓止损幅度（%），0=关闭"),
):
    single = main_ratio >= 0.999
    prefix, digits = parse_code(code)
    try:
        q = fetch_quote(prefix, digits)
        all_klines = fetch_kline(prefix, digits, 250)
    except requests.RequestException:
        raise HTTPException(502, "行情服务暂时不可用，请稍后重试")
    except ValueError:
        raise HTTPException(502, "行情服务返回数据异常，请稍后重试")
    if len(all_klines) < 30:
        raise HTTPException(400, f"{q['name']} 历史K线不足30个交易日，不适合做网格分析")

    klines = all_klines[-BACKTEST_DAYS:]
    history_closes = [k["close"] for k in all_klines]
    high_52w = max(k["high"] for k in all_klines)
    low_52w = min(k["low"] for k in all_klines)

    mid = (q["ask"][0]["p"] + q["bid"][0]["p"]) / 2 if q["ask"][0]["p"] > 0 and q["bid"][0]["p"] > 0 else q["price"]
    spread = (q["ask"][0]["p"] - q["bid"][0]["p"]) / mid if mid else 0
    spread_pct = max(spread, 0.0) * 100
    bid_depth = sum(b["p"] * b["v"] * 100 for b in q["bid"])
    grade, grade_reason = liquidity_grade(spread_pct, q["amount_wan"])

    main_grid, aux_grid, axis, vol = build_grids(
        klines, q["price"], capital, single, main_ratio,
        spread_pct, fee, min_fee, history_closes=history_closes,
    )
    if main_grid["shares_per_grid"] <= 0:
        raise HTTPException(400, f"主网格每格资金不足一手（100股）约需 {100 * q['price']:.0f} 元/格，请增大总资金或换低价标的")

    trend20, trend60 = compute_trend(klines)
    boll_range = vol["boll_upper"] - vol["boll_lower"]
    if boll_range > 0:
        pct_b = (q["price"] - vol["boll_lower"]) / boll_range
    else:
        pct_b = 0.5
    pct_b = max(0.0, min(1.0, pct_b))

    if abs(trend20) >= 8 and abs(trend60) >= 12 and trend20 * trend60 > 0:
        regime = "单边趋势 ⚠️"
    elif abs(trend20) >= 8:
        regime = "短期趋势"
    elif vol["squeeze"]:
        regime = "波动挤压 ⚠️"
    else:
        regime = "区间震荡 ✅"

    score = fit_score(trend20, trend60, pct_b, vol["atr_pct"], vol["squeeze"])

    # 回测参数只用回测起点之前的数据校准，避免未来函数
    bt_start_idx = max(0, len(all_klines) - len(klines))
    calib = all_klines[:bt_start_idx]
    used_calibration = len(calib) >= 60
    if used_calibration:
        bt_main_grid, bt_aux_grid, _, _ = build_grids(
            calib, calib[-1]["close"], capital, single, main_ratio,
            spread_pct, fee, min_fee,
            history_closes=[k["close"] for k in calib],
        )
    else:
        bt_main_grid, bt_aux_grid = main_grid, aux_grid

    bt_main = run_backtest(klines, bt_main_grid, fee, min_fee, init_position, stop_loss)
    bt_aux = None if (single or bt_aux_grid["shares_per_grid"] <= 0) else run_backtest(
        klines, bt_aux_grid, fee, min_fee, init_position, stop_loss
    )
    backtest_meta = {
        "used_calibration": used_calibration,
        "calibration_days": len(calib),
        "start_date": klines[0]["date"],
        "end_date": klines[-1]["date"],
        "main_lower": bt_main_grid["lower"],
        "main_upper": bt_main_grid["upper"],
        "main_gap_pct": bt_main_grid["gap_pct"],
        "main_shares_per_grid": bt_main_grid["shares_per_grid"],
        "lookahead_free": used_calibration,
    }

    params = {
        "capital": capital,
        "fee_pct": fee,
        "min_fee": min_fee,
        "main_ratio": main_ratio,
        "single_grid": single,
        "init_position_pct": init_position,
        "stop_loss_pct": stop_loss,
        "backtest_days": len(klines),
    }
    data = {
        "params": params,
        "quote": {
            "name": q["name"], "code": q["code"], "market_code": prefix,
            "price": q["price"], "change": q["change"], "change_pct": q["change_pct"],
            "amount_wan": q["amount_wan"], "turnover_pct": q["turnover_pct"],
            "amplitude_pct": q["amplitude_pct"], "high": q["high"], "low": q["low"],
            "high_52w": high_52w, "low_52w": low_52w,
            "total_mv": q["total_mv"], "pe_ttm": q["pe_ttm"],
        },
        "liquidity": {
            "grade": grade, "grade_reason": grade_reason,
            "spread_pct": spread_pct, "bid_depth_yuan": bid_depth,
        },
        "kline_tail": klines,
        "axis": axis,
        "volatility": vol,
        "trend": {
            "trend20_pct": trend20, "trend60_pct": trend60,
            "pct_b": pct_b, "regime": regime, "fit_score": score,
        },
        "main_grid": main_grid,
        "aux_grid": aux_grid,
        "round_trip_cost_pct": main_grid["round_trip_cost_pct"],
        "min_gap_pct": main_grid["min_gap_pct"],
        "backtest": {"main": bt_main, "aux": bt_aux},
        "backtest_meta": backtest_meta,
        "risks": [],
        "version": app.version,
    }
    data["risks"] = collect_risks(data)
    return {"ok": True, "data": data}


# ---------------- 静态文件（index.html） ----------------
@app.get("/", response_class=HTMLResponse)
def index():
    idx = Path(__file__).parent / "index.html"
    if idx.exists():
        return HTMLResponse(idx.read_text(encoding="utf-8"))
    return {"message": "A股网格交易参数分析器后端运行中，请将 index.html 放在同目录"}


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000)
