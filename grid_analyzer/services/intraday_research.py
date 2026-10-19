from __future__ import annotations

import statistics
from dataclasses import asdict, dataclass
from typing import Any

from grid_analyzer.backtest.calibration import rolling_windows
from grid_analyzer.backtest.engine import run_backtest
from grid_analyzer.backtest.metrics import METRIC_KEYS, aggregate_metrics, compute_metrics
from grid_analyzer.grid.designer import build_grids
from grid_analyzer.indicators.volatility import compute_volatility


class InsufficientIntradayDataError(RuntimeError):
    """Raised when intraday history cannot support the requested validation."""


@dataclass(frozen=True)
class IntradayValidationConfig:
    capital: float = 100_000
    fee: float = 0.025
    min_fee: float = 5.0
    spread_pct: float = 0.05
    init_position: float = 0.0
    stop_losses: tuple[float, ...] = (0.0, 3.0, 5.0, 8.0)
    k_start: float = 0.5
    k_end: float = 1.5
    k_step: float = 0.05
    window_days: int = 126
    in_sample_ratio: float = 0.70
    final_blind_days: int = 63
    min_oos_days: int = 252
    primary_metric: str = "realized_annual_pct"
    adjustflag: str = "2"


def intraday_k_values(start: float = 0.5, end: float = 1.5, step: float = 0.05) -> list[float]:
    if step <= 0 or end < start:
        raise ValueError("K 范围和步长不合法")
    values: list[float] = []
    current = start
    while current <= end + 1e-9:
        values.append(round(current, 2))
        current += step
    if len(values) != 21:
        raise ValueError(f"默认 K 扫描应产生 21 个值，实际 {len(values)} 个")
    return values


def _metric_number(value: Any) -> float:
    return float(value) if value is not None else 0.0


def _select_plateau(
    fold_metrics: dict[tuple[float, float], dict],
    k_values: list[float],
    stop_losses: list[float],
    primary_metric: str,
) -> tuple[float, float, float]:
    lower_is_better = primary_metric == "max_drawdown_pct"
    best: tuple[float, float, float] | None = None
    for stop in stop_losses:
        available = [
            (k, fold_metrics[(k, stop)])
            for k in k_values
            if (k, stop) in fold_metrics
        ]
        if not available:
            continue
        raw = [
            _metric_number(metrics.get(primary_metric))
            for _, metrics in available
        ]
        smoothed = []
        for idx in range(len(raw)):
            window = raw[max(0, idx - 1): min(len(raw), idx + 2)]
            smoothed.append(statistics.mean(window))
        for idx, score in enumerate(smoothed):
            candidate = (available[idx][0], stop, score)
            if best is None:
                best = candidate
                continue
            if lower_is_better:
                better = score < best[2] or (
                    score == best[2] and (stop < best[1] or (stop == best[1] and k_values[idx] < best[0]))
                )
            else:
                better = score > best[2] or (
                    score == best[2] and (stop < best[1] or (stop == best[1] and k_values[idx] > best[0]))
                )
            if better:
                best = candidate
    if best is None:
        raise InsufficientIntradayDataError("没有可用于选择的参数组合")
    return best


def _flatten_bars(bars_by_day: dict[str, list[dict]], days: list[str]) -> list[dict]:
    return [bar for day in days for bar in bars_by_day.get(day, [])]


def _daily_context(daily_bars: list[dict], end_day: str) -> list[dict]:
    return [bar for bar in daily_bars if str(bar.get("trading_day") or bar.get("date")) <= end_day]


def _build_grid(
    daily_context: list[dict],
    config: IntradayValidationConfig,
    k_value: float,
    atr_pct: float,
) -> dict:
    gap_override = k_value * atr_pct / 100.0
    main_grid, _, _, _ = build_grids(
        daily_context,
        daily_context[-1]["close"],
        config.capital,
        True,
        1.0,
        config.spread_pct,
        config.fee,
        config.min_fee,
        history_closes=[bar["close"] for bar in daily_context],
        gap_override=gap_override,
    )
    return main_grid


def run_intraday_validation(
    bars_5m: list[dict],
    daily_bars: list[dict],
    config: IntradayValidationConfig | None = None,
) -> dict:
    """Run 6-month 70/30 rolling validation with K x stop-loss scanning."""
    config = config or IntradayValidationConfig()
    if not bars_5m or not daily_bars:
        raise InsufficientIntradayDataError("缺少 5 分钟或日线数据")
    if config.primary_metric not in METRIC_KEYS:
        raise ValueError(f"unsupported primary metric: {config.primary_metric}")

    k_values = intraday_k_values(config.k_start, config.k_end, config.k_step)
    stop_losses = sorted({float(item) for item in config.stop_losses})

    bars_by_day: dict[str, list[dict]] = {}
    for bar in bars_5m:
        bars_by_day.setdefault(str(bar["trading_day"]), []).append(bar)
    days = sorted(bars_by_day)
    in_sample_days = round(config.window_days * config.in_sample_ratio)
    oos_days = config.window_days - in_sample_days
    if in_sample_days <= 0 or oos_days <= 0:
        raise ValueError("窗口切分结果不合法")

    rolling_end = len(days) - max(config.final_blind_days, 0)
    if rolling_end <= 0:
        raise InsufficientIntradayDataError("历史数据不足以预留最终盲测段")
    windows = rolling_windows(
        rolling_end,
        calib_days=in_sample_days,
        test_days=oos_days,
        step=oos_days,
    )
    if not windows:
        raise InsufficientIntradayDataError("没有足够的 5 分钟历史数据生成滚动窗口")
    oos_coverage_days = sum(window.test_end - window.test_start for window in windows)
    if oos_coverage_days < config.min_oos_days:
        raise InsufficientIntradayDataError(
            f"样本外覆盖不足：需要 {config.min_oos_days} 个交易日，实际 {oos_coverage_days} 个"
        )

    fold_results: list[dict] = []
    cell_metrics: dict[tuple[float, float], list[dict]] = {
        (k, stop): [] for k in k_values for stop in stop_losses
    }

    for window in windows:
        in_days = days[window.calib_start:window.calib_end]
        oos_days_list = days[window.test_start:window.test_end]
        in_bars = _flatten_bars(bars_by_day, in_days)
        oos_bars = _flatten_bars(bars_by_day, oos_days_list)
        daily_context = _daily_context(daily_bars, in_days[-1])
        if len(daily_context) < 20:
            continue
        atr_pct = float(compute_volatility(daily_context)["atr_pct"])
        if atr_pct <= 0:
            continue

        fold_metrics: dict[tuple[float, float], dict] = {}
        grids: dict[float, dict] = {}
        for k_value in k_values:
            grid = _build_grid(daily_context, config, k_value, atr_pct)
            grids[k_value] = grid
            if grid["shares_per_grid"] <= 0:
                continue
            for stop in stop_losses:
                bt = run_backtest(
                    in_bars,
                    grid,
                    config.fee,
                    config.min_fee,
                    config.init_position,
                    stop,
                )
                metrics = compute_metrics(bt, config.capital)
                fold_metrics[(k_value, stop)] = metrics
                cell_metrics[(k_value, stop)].append(metrics)

        if not fold_metrics:
            continue
        selected_k, selected_stop, _ = _select_plateau(
            fold_metrics, k_values, stop_losses, config.primary_metric
        )
        selected_grid = grids[selected_k]
        oos_bt = run_backtest(
            oos_bars,
            selected_grid,
            config.fee,
            config.min_fee,
            config.init_position,
            selected_stop,
        )
        oos_metrics = compute_metrics(oos_bt, config.capital)
        fold_results.append(
            {
                "in_sample_start": in_days[0],
                "in_sample_end": in_days[-1],
                "oos_start": oos_days_list[0],
                "oos_end": oos_days_list[-1],
                "selected_k": selected_k,
                "selected_stop_loss": selected_stop,
                "atr_pct": atr_pct,
                "gap_pct": selected_grid["gap_pct"],
                "capital_constrained": selected_grid["capital_constrained"],
                "in_sample_metrics": fold_metrics[(selected_k, selected_stop)],
                "oos_metrics": oos_metrics,
            }
        )

    if not fold_results:
        raise InsufficientIntradayDataError("滚动窗口没有产生有效结果")

    cells = []
    for k_value in k_values:
        for stop in stop_losses:
            metrics_list = cell_metrics[(k_value, stop)]
            aggregated = aggregate_metrics(metrics_list)
            primary = aggregated[config.primary_metric]
            score = (
                -(primary["mean"] + primary["stdev"])
                if config.primary_metric == "max_drawdown_pct"
                else primary["mean"] - primary["stdev"]
            )
            cells.append(
                {
                    "k": k_value,
                    "stop_loss": stop,
                    "fold_count": len(metrics_list),
                    "metrics": aggregated,
                    "plateau_score": score,
                }
            )

    stability_k = [fold["selected_k"] for fold in fold_results]
    stability_stop = [fold["selected_stop_loss"] for fold in fold_results]
    change_count = sum(
        1
        for previous, current in zip(
            zip(stability_k, stability_stop),
            zip(stability_k[1:], stability_stop[1:]),
        )
        if previous != current
    )

    counts: dict[tuple[float, float], int] = {}
    for fold in fold_results:
        key = (fold["selected_k"], fold["selected_stop_loss"])
        counts[key] = counts.get(key, 0) + 1
    locked_key = max(
        counts,
        key=lambda key: (counts[key], statistics.mean(
            _metric_number(fold["oos_metrics"].get(config.primary_metric))
            for fold in fold_results
            if (fold["selected_k"], fold["selected_stop_loss"]) == key
        )),
    )
    locked_k, locked_stop = locked_key

    blind_start_index = rolling_end
    blind_days = days[blind_start_index:]
    blind_bars = _flatten_bars(bars_by_day, blind_days)
    blind_daily_context = _daily_context(daily_bars, days[blind_start_index - 1])
    blind_result = None
    if blind_bars and len(blind_daily_context) >= 20:
        blind_atr_pct = float(compute_volatility(blind_daily_context)["atr_pct"])
        blind_grid = _build_grid(blind_daily_context, config, locked_k, blind_atr_pct)
        if blind_grid["shares_per_grid"] > 0:
            blind_bt = run_backtest(
                blind_bars,
                blind_grid,
                config.fee,
                config.min_fee,
                config.init_position,
                locked_stop,
            )
            blind_result = {
                "start": blind_days[0],
                "end": blind_days[-1],
                "k": locked_k,
                "stop_loss": locked_stop,
                "gap_pct": blind_grid["gap_pct"],
                "metrics": compute_metrics(blind_bt, config.capital),
            }

    oos_primary = [
        _metric_number(fold["oos_metrics"].get(config.primary_metric))
        for fold in fold_results
    ]
    summary = {
        "fold_count": len(fold_results),
        "oos_coverage_days": oos_coverage_days,
        "oos_coverage_months": oos_coverage_days / 21.0,
        "positive_oos_ratio": sum(1 for value in oos_primary if value > 0) / len(oos_primary),
        "oos_primary_mean": statistics.mean(oos_primary),
        "oos_primary_worst": min(oos_primary),
        "oos_primary_stdev": statistics.stdev(oos_primary) if len(oos_primary) > 1 else 0.0,
    }

    return {
        "config": asdict(config),
        "k_values": k_values,
        "stop_losses": stop_losses,
        "in_sample_days": in_sample_days,
        "oos_days": oos_days,
        "folds": fold_results,
        "cells": cells,
        "parameter_stability": {
            "k_values": stability_k,
            "stop_losses": stability_stop,
            "change_count": change_count,
        },
        "locked": {
            "k": locked_k,
            "stop_loss": locked_stop,
            "blind": blind_result,
        },
        "summary": summary,
    }
