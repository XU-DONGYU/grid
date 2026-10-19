from __future__ import annotations

import math

from grid_analyzer.constants import STAMP_TAX, TRADING_DAYS
from grid_analyzer.utils.finance import commission


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
        o, c, h, low = k["open"], k["close"], k["high"], k["low"]

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
            path = [start, o, low, h, c]
        else:
            path = [start, o, h, low, c]

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
