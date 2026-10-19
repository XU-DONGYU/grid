from __future__ import annotations

import math
import statistics

from grid_analyzer.constants import TRADING_DAYS

METRIC_KEYS = [
    "realized_annual_pct",
    "total_annual_pct",
    "calmar",
    "sharpe",
    "sortino",
    "max_drawdown_pct",
    "win_rate_pct",
    "profit_factor",
    "stop_count",
    "exposure_pct",
]


def daily_equity(equity_curve: list[dict]) -> list[tuple[str, float]]:
    last_by_day: dict[str, float] = {}
    for point in equity_curve:
        day = str(point.get("trading_day") or point.get("date") or "")
        if day:
            last_by_day[day] = float(point["equity"])
    return sorted(last_by_day.items())


def daily_returns(equity_curve: list[dict]) -> list[float]:
    values = [equity for _, equity in daily_equity(equity_curve)]
    returns = []
    for prev, current in zip(values, values[1:]):
        if prev > 0:
            returns.append(current / prev - 1.0)
    return returns


def annualized_return_pct(initial: float, final: float, trading_days: int) -> float:
    if initial <= 0 or final <= 0 or trading_days <= 0:
        return -100.0 if final <= 0 else 0.0
    return ((final / initial) ** (TRADING_DAYS / trading_days) - 1.0) * 100.0


def sharpe_ratio(returns: list[float], periods: int = TRADING_DAYS) -> float:
    if len(returns) < 2:
        return 0.0
    stdev = statistics.stdev(returns)
    if stdev <= 0:
        return 0.0
    return statistics.mean(returns) / stdev * math.sqrt(periods)


def sortino_ratio(returns: list[float], periods: int = TRADING_DAYS) -> float:
    if len(returns) < 2:
        return 0.0
    downside = [min(0.0, value) for value in returns]
    downside_dev = math.sqrt(sum(value * value for value in downside) / len(downside))
    if downside_dev <= 0:
        return 0.0
    return statistics.mean(returns) / downside_dev * math.sqrt(periods)


def compute_metrics(backtest: dict, capital: float) -> dict:
    trading_days = int(backtest.get("trading_days") or 0)
    realized_pnl = float(backtest.get("realized_pnl") or 0)
    realized_return_pct = realized_pnl / capital * 100.0 if capital > 0 else 0.0
    realized_annual_pct = (
        realized_return_pct * TRADING_DAYS / trading_days if trading_days > 0 else 0.0
    )
    max_drawdown_pct = float(backtest.get("max_drawdown_pct") or 0)
    total_annual_pct = float(backtest.get("annual_pct") or 0)
    calmar = total_annual_pct / max_drawdown_pct if max_drawdown_pct > 0 else 0.0

    returns = daily_returns(backtest.get("equity_curve") or [])
    realized_trades = int(backtest.get("realized_trades") or 0)
    win_count = int(backtest.get("win_count") or 0)
    gross_profit = float(backtest.get("gross_profit") or 0)
    gross_loss = float(backtest.get("gross_loss") or 0)

    return {
        "realized_annual_pct": realized_annual_pct,
        "total_annual_pct": total_annual_pct,
        "calmar": calmar,
        "sharpe": sharpe_ratio(returns),
        "sortino": sortino_ratio(returns),
        "max_drawdown_pct": max_drawdown_pct,
        "win_rate_pct": win_count / realized_trades * 100.0 if realized_trades else 0.0,
        "profit_factor": gross_profit / gross_loss if gross_loss > 0 else None,
        "stop_count": 1 if backtest.get("stop_triggered") else 0,
        "exposure_pct": (
            float(backtest.get("max_position_cost") or 0) / capital * 100.0
            if capital > 0
            else 0.0
        ),
    }


def aggregate_metrics(metrics_list: list[dict]) -> dict:
    if not metrics_list:
        return {key: {"mean": 0.0, "stdev": 0.0, "worst": 0.0} for key in METRIC_KEYS}
    result = {}
    for key in METRIC_KEYS:
        values = [
            float(item[key])
            for item in metrics_list
            if item.get(key) is not None
        ]
        if values:
            result[key] = {
                "mean": statistics.mean(values),
                "stdev": statistics.stdev(values) if len(values) > 1 else 0.0,
                "worst": min(values),
            }
        else:
            result[key] = {"mean": 0.0, "stdev": 0.0, "worst": 0.0}
    return result
