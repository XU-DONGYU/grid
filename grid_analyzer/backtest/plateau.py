from __future__ import annotations

import bisect
import math
import statistics
from dataclasses import asdict, dataclass
from typing import Any, Literal

from grid_analyzer.constants import STAMP_TAX, TRADING_DAYS
from grid_analyzer.utils.finance import commission

AnchorMode = Literal["dynamic", "static_mean"]

PRIOR_K_LEFT = 0.65
PRIOR_K_RIGHT = 0.80
PRIOR_K_ANCHOR = 0.70


class InsufficientPlateauDataError(RuntimeError):
    """Raised when the intraday history cannot support a plateau scan."""


@dataclass(frozen=True)
class PlateauConfig:
    """Configuration for the ATR-normalised parameter-plateau scan."""

    capital: float = 100_000.0
    shares_per_grid: int = 100
    max_positions: int = 8
    fee: float = 0.025
    min_fee: float = 5.0
    spread_pct: float = 0.05
    slippage_pct: float = 0.02
    friction_pct: float | None = None
    k_start: float = 0.20
    k_end: float = 2.50
    k_step: float = 0.05
    mode: AnchorMode = "dynamic"
    anchor_policy: str = "fixed"
    band_lower: float | None = None
    band_upper: float | None = None
    band_lookback_days: int = 60
    band_buffer_pct: float = 2.0
    reanchor_period_days: int = 20
    atr_period: int = 14
    plateau_window: int = 5
    plateau_stability_penalty: float = 0.5
    plateau_center_left_ratio: float = 0.35
    min_loops: int = 10
    open_loss_penalty: float = 0.5
    island_drop_ratio: float = 0.25
    island_min_drop_pct: float = 0.20
    front_run_thresholds: tuple[float, ...] = (1.0, 2.0, 3.0, 5.0)
    front_run_band_pct: float = 0.08
    front_run_offset_pct: float = 0.20
    pullback_sell_pct: float = 0.30
    rebound_buy_pct: float = 0.30
    price_limit_pct: float = 10.0
    min_bars_per_day: int = 1
    holdout_ratio: float = 0.30
    stop_loss_pct: float = 0.0
    restart_cooldown_days: int = 0


@dataclass(frozen=True)
class AtrPoint:
    trading_day: str
    close: float
    atr: float
    atr_pct: float
    high: float = 0.0
    low: float = 0.0


@dataclass(frozen=True)
class _DayStep:
    trading_day: str
    step_pct: float
    step_abs: float
    atr_pct: float
    anchor: float
    prev_close: float = 0.0
    band_lower: float | None = None
    band_upper: float | None = None


def plateau_k_values(start: float, end: float, step: float) -> list[float]:
    """Build the inclusive k grid with two-decimal precision."""
    if step <= 0 or end < start:
        raise ValueError("k 范围和步长不合法")
    values: list[float] = []
    current = start
    while current <= end + 1e-9:
        values.append(round(current, 4))
        current += step
    values = sorted({round(value, 4) for value in values})
    if len(values) < 2:
        raise ValueError("k 扫描至少需要两个值")
    return values


def compute_atr_series(daily_bars: list[dict], period: int = 14) -> list[AtrPoint]:
    """Compute a Wilder ATR(14) series using only bars up to each point."""
    if period <= 0:
        raise ValueError("ATR 周期必须为正")
    bars = sorted(
        daily_bars,
        key=lambda bar: str(bar.get("trading_day") or bar.get("date") or ""),
    )
    if not bars:
        return []

    points: list[AtrPoint] = []
    trs: list[float] = []
    atr = 0.0
    for index, bar in enumerate(bars):
        high = float(bar["high"])
        low = float(bar["low"])
        close = float(bar["close"])
        if index == 0:
            atr = max(0.0, high - low)
        else:
            previous_close = float(bars[index - 1]["close"])
            tr = max(high - low, abs(high - previous_close), abs(low - previous_close))
            trs.append(tr)
            if index <= period:
                atr = statistics.mean(trs)
            else:
                atr = (atr * (period - 1) + tr) / period
        atr = max(0.0, atr)
        day = str(bar.get("trading_day") or bar.get("date") or "")
        points.append(
            AtrPoint(
                trading_day=day,
                close=close,
                atr=atr,
                atr_pct=(atr / close * 100.0) if close > 0 else 0.0,
                high=high,
                low=low,
            )
        )
    return points


def effective_friction_pct(
    config: PlateauConfig,
    reference_price: float | None = None,
) -> float:
    """Rate-based round-trip friction for the theoretical k floor.

    The minimum commission is size-dependent and is deducted in the actual
    per-trade P&L, not in this theoretical percentage.
    """
    if config.friction_pct is not None:
        return max(0.0, float(config.friction_pct))
    return (
        2.0 * float(config.fee)
        + STAMP_TAX * 100.0
        + max(0.0, float(config.spread_pct))
    )


def safe_k_floor(friction_pct: float, mean_atr_pct: float) -> float:
    """k below this value is the high-frequency fee-grinding zone."""
    if mean_atr_pct <= 0:
        return math.inf
    return 10.0 * friction_pct / mean_atr_pct


def _bar_day(bar: dict) -> str:
    return str(bar.get("trading_day") or bar.get("date") or "")


def _bar_path(bar: dict) -> list[float]:
    open_price = float(bar["open"])
    close = float(bar["close"])
    high = float(bar["high"])
    low = float(bar["low"])
    if close >= open_price:
        return [open_price, low, high, close]
    return [open_price, high, low, close]


def _group_bars(bars_5m: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for bar in bars_5m:
        grouped.setdefault(_bar_day(bar), []).append(bar)
    for day in grouped:
        grouped[day].sort(key=lambda item: str(item.get("timestamp") or ""))
    return grouped


def build_daily_anchors(
    atr_series: list[AtrPoint],
    days: list[str],
    config: PlateauConfig,
) -> dict[str, float]:
    """Build day anchors using only data known before each trading day."""
    if config.anchor_policy not in {"daily_roll", "fixed_band", "fixed", "periodic"}:
        raise ValueError(f"不支持的锚定策略：{config.anchor_policy}")
    atr_days = [point.trading_day for point in atr_series]
    anchors: dict[str, float] = {}
    first_anchor: float | None = None
    current_anchor: float | None = None
    for day_index, day in enumerate(days):
        index = bisect.bisect_left(atr_days, day)
        if index <= 0:
            continue
        previous = atr_series[index - 1]
        if previous.close <= 0:
            continue
        if config.anchor_policy == "daily_roll":
            anchor = previous.close
        elif config.anchor_policy == "fixed":
            if first_anchor is None:
                first_anchor = previous.close
            anchor = first_anchor
        elif config.anchor_policy == "periodic":
            period = max(1, int(config.reanchor_period_days))
            if current_anchor is None or day_index % period == 0:
                current_anchor = previous.close
            anchor = current_anchor
        else:
            if current_anchor is None:
                current_anchor = previous.close
            lookback = max(1, int(config.band_lookback_days))
            # Exclude the immediate prior day so a new high/low can actually
            # break out of the older band; otherwise the prior close is always
            # inside its own band and re-anchoring can never trigger.
            band = atr_series[max(0, index - lookback - 1): max(0, index - 1)]
            if band:
                band_high = max((point.high or point.close) for point in band)
                band_low = min((point.low or point.close) for point in band)
                buffer = max(0.0, float(config.band_buffer_pct)) / 100.0
                if previous.close > band_high * (1.0 + buffer) or previous.close < band_low * (1.0 - buffer):
                    current_anchor = previous.close
            anchor = current_anchor
        anchors[day] = anchor
    return anchors


def _build_day_steps(
    atr_series: list[AtrPoint],
    days: list[str],
    config: PlateauConfig,
    k_value: float,
    anchors: dict[str, float] | None = None,
    band: tuple[float, float] | None = None,
    start_step_pct: float | None = None,
) -> dict[str, _DayStep]:
    atr_days = [point.trading_day for point in atr_series]
    prefix_pct = [0.0]
    for point in atr_series:
        prefix_pct.append(prefix_pct[-1] + point.atr_pct)
    if anchors is None:
        anchors = build_daily_anchors(atr_series, days, config)

    steps: dict[str, _DayStep] = {}
    for day in days:
        index = bisect.bisect_left(atr_days, day)
        if index <= 0:
            # The same day's ATR is only known after the close; use the prior day.
            continue
        previous = atr_series[index - 1]
        if config.anchor_policy == "fixed" and band is not None and start_step_pct:
            step_pct = start_step_pct
            anchor = (band[0] + band[1]) / 2.0
            steps[day] = _DayStep(
                trading_day=day,
                step_pct=step_pct,
                step_abs=anchor * step_pct / 100.0,
                atr_pct=previous.atr_pct,
                anchor=anchor,
                prev_close=previous.close,
                band_lower=band[0],
                band_upper=band[1],
            )
            continue
        anchor = anchors.get(day, previous.close)
        if anchor <= 0:
            continue
        if config.mode == "dynamic":
            step_pct = k_value * previous.atr_pct
            step_abs = k_value * previous.atr
        else:
            trailing_mean_pct = prefix_pct[index] / index
            step_pct = k_value * trailing_mean_pct
            step_abs = anchor * step_pct / 100.0
        if step_pct <= 0 or step_abs <= 0:
            continue
        steps[day] = _DayStep(
            trading_day=day,
            step_pct=step_pct,
            step_abs=step_abs,
            atr_pct=previous.atr_pct,
            anchor=anchor,
            prev_close=previous.close,
        )
    return steps


def _day_levels(anchor: float, step_abs: float, max_positions: int) -> list[tuple[int, float]]:
    levels: list[tuple[int, float]] = []
    for index in range(max_positions):
        level = anchor - (index + 1) * step_abs
        if level > 0:
            levels.append((index, level))
    return levels


def _band_levels(lower: float, upper: float, step_pct: float) -> list[tuple[int, float]]:
    """Build a geometric ladder across a fixed price band."""
    if lower <= 0 or upper <= lower or step_pct <= 0:
        return []
    growth = 1.0 + step_pct / 100.0
    levels: list[tuple[int, float]] = []
    level = lower
    while level <= upper * (1.0 + 1e-9) and len(levels) < 1000:
        levels.append((len(levels), level))
        level *= growth
    return levels


def resolve_band(
    atr_series: list[AtrPoint],
    first_day: str,
    config: PlateauConfig,
) -> tuple[float, float, str]:
    """Resolve the fixed band from manual inputs or prior daily highs/lows."""
    if config.band_lower is not None and config.band_upper is not None:
        if config.band_lower <= 0 or config.band_upper <= config.band_lower:
            raise ValueError("手动区间必须满足 0 < 下限 < 上限")
        return float(config.band_lower), float(config.band_upper), "manual"
    lookback = max(5, int(config.band_lookback_days))
    prior = [point for point in atr_series if point.trading_day < first_day][-lookback:]
    if prior:
        raw_lower = min(point.low or point.close for point in prior)
        raw_upper = max(point.high or point.close for point in prior)
        buffer = max(0.0, float(config.band_buffer_pct)) / 100.0
        lower = raw_lower * (1.0 + buffer)
        upper = raw_upper * (1.0 - buffer)
        if lower < upper:
            return lower, upper, "auto"
        return raw_lower, raw_upper, "auto"
    first = next(
        (point for point in atr_series if point.trading_day >= first_day),
        atr_series[0] if atr_series else None,
    )
    if first is None or first.close <= 0:
        raise InsufficientPlateauDataError("无法确定固定区间")
    return first.close * 0.9, first.close * 1.1, "fallback"


def fixed_step_pct(
    atr_series: list[AtrPoint],
    first_day: str,
    config: PlateauConfig,
    k_value: float,
) -> float:
    """Density computed once at the start of a fixed-band grid."""
    lookback = max(5, int(config.band_lookback_days))
    prior = [point for point in atr_series if point.trading_day < first_day][-lookback:]
    if not prior:
        prior = [point for point in atr_series if point.trading_day >= first_day][:1]
    if not prior:
        return 0.0
    base = (
        prior[-1].atr_pct
        if config.mode == "dynamic"
        else statistics.mean(point.atr_pct for point in prior)
    )
    return k_value * base


def _slot_shares(price: float, config: PlateauConfig) -> float:
    """Every filled trigger buys the same fixed number of shares."""
    if price <= 0 or config.shares_per_grid <= 0:
        return 0.0
    return float(config.shares_per_grid)


def simulate_k(
    bars_by_day: dict[str, list[dict]],
    day_steps: dict[str, _DayStep],
    config: PlateauConfig,
    normalization_price: float = 0.0,
) -> dict[str, Any]:
    """Simulate a rolling normalised ladder grid with 0/1 line fills.

    Each day places up to ``max_positions`` buy levels below the configured
    anchor.  Every filled level is an independent slot with budget
    ``shares_per_grid`` shares.  Positions are sold one step above their fill, subject to
    T+1.  A-share lot rounding, cash, slippage, price-limit locks and
    incomplete 5-minute days are handled explicitly.
    """
    days = sorted(bars_by_day)
    day_index = {day: index for index, day in enumerate(days)}
    max_positions = max(1, int(config.max_positions))
    grid_capital = config.capital
    normalization_notional = (
        float(config.shares_per_grid) * normalization_price
        if normalization_price > 0
        else config.capital
    )
    cash = grid_capital
    open_lots: list[dict[str, Any]] = []
    loops = 0
    winning_loops = 0
    gross_return_pct = 0.0
    net_return_pct = 0.0
    net_profit_total = 0.0
    loop_returns: list[float] = []
    max_open_loss_pct = 0.0
    max_positions_used = 0
    position_sum = 0
    position_samples = 0
    first_trade_day: str | None = None
    last_trade_day: str | None = None
    last_price = 0.0
    last_day = days[-1] if days else ""
    actual_fees = 0.0
    slippage_paid = 0.0
    peak_invested = 0.0
    capital_constrained_buys = 0
    limit_locked_days = 0
    incomplete_days = 0
    stopped = False
    post_stop_rolling = False
    restart_day_index = 0
    stop_count = 0
    restart_count = 0
    stopped_days = 0
    last_stop_day: str | None = None
    upper_breakout_days = 0
    lower_breakout_days = 0
    # Half-spread on each side plus explicit slippage/impact proxy.
    slip = (
        max(0.0, float(config.slippage_pct))
        + max(0.0, float(config.spread_pct)) / 2.0
    ) / 100.0

    def invested() -> float:
        return sum(float(lot["cost"]) for lot in open_lots)

    def close_lot(
        lot: dict[str, Any],
        target: float,
        count_loop: bool = True,
    ) -> None:
        nonlocal loops, winning_loops, gross_return_pct, net_return_pct
        nonlocal last_trade_day, cash, actual_fees, slippage_paid, net_profit_total
        sell_price = max(0.01, target * (1.0 - slip))
        shares = float(lot["shares"])
        amount = shares * sell_price
        fee = commission(amount, config.fee, config.min_fee)
        stamp = amount * STAMP_TAX
        proceeds = amount - fee - stamp
        cash += proceeds
        gross = amount - float(lot["amount"])
        net = proceeds - float(lot["cost"])
        fees = float(lot["buy_fee"]) + fee + stamp
        actual_fees += fees
        slippage_paid += float(lot["buy_slippage"]) + shares * (target - sell_price)
        gross_return_pct += gross / normalization_notional * 100.0
        net_return_pct += net / normalization_notional * 100.0
        net_profit_total += net
        if count_loop:
            loop_return = net / float(lot["amount"]) * 100.0 if float(lot["amount"]) > 0 else 0.0
            loop_returns.append(loop_return)
            loops += 1
            if loop_return > 0:
                winning_loops += 1
        last_trade_day = day
        open_lots.remove(lot)

    def open_lot(
        level: float,
        level_index: int,
        step_abs: float,
        target: float | None = None,
    ) -> bool:
        nonlocal first_trade_day, max_positions_used, cash
        nonlocal capital_constrained_buys, peak_invested
        buy_price = level * (1.0 + slip)
        if any(abs(float(lot["price"]) - buy_price) < 1e-9 for lot in open_lots):
            return False
        shares = _slot_shares(buy_price, config)
        if shares <= 0:
            capital_constrained_buys += 1
            return False
        amount = shares * buy_price
        fee = commission(amount, config.fee, config.min_fee)
        cost = amount + fee
        if cost > cash + 1e-9:
            capital_constrained_buys += 1
            return False
        cash -= cost
        open_lots.append(
            {
                "price": buy_price,
                "buy_day": day,
                "target": target if target is not None else buy_price + step_abs,
                "level_index": level_index,
                "shares": shares,
                "amount": amount,
                "cost": cost,
                "buy_fee": fee,
                "buy_slippage": shares * (buy_price - level),
            }
        )
        if first_trade_day is None:
            first_trade_day = day
        max_positions_used = max(max_positions_used, len(open_lots))
        peak_invested = max(peak_invested, invested())
        return True

    def trigger_stop(fill_price: float) -> None:
        nonlocal stopped, post_stop_rolling, restart_day_index
        nonlocal stop_count, last_stop_day
        for lot in list(open_lots):
            if lot["buy_day"] < day:
                close_lot(lot, fill_price, count_loop=False)
        stopped = True
        post_stop_rolling = True
        restart_day_index = day_index.get(day, 0) + max(1, int(config.restart_cooldown_days) + 1)
        stop_count += 1
        last_stop_day = day

    for day in days:
        bars = bars_by_day.get(day) or []
        if not bars:
            incomplete_days += 1
            continue
        if len(bars) < max(1, int(config.min_bars_per_day)):
            incomplete_days += 1
            continue

        step = day_steps.get(day)
        step_abs = step.step_abs if step is not None else 0.0
        open_price = float(bars[0]["open"])
        prev_close = step.prev_close if step is not None else 0.0
        day_number = day_index.get(day, 0)

        if stopped:
            if day_number < restart_day_index:
                stopped_days += 1
                last_price = float(bars[-1]["close"])
                last_day = day
                for lot in list(open_lots):
                    if lot["buy_day"] < day:
                        close_lot(lot, open_price, count_loop=False)
                mark_to_market = sum(
                    (last_price - float(lot["price"])) * float(lot["shares"])
                    for lot in open_lots
                ) / normalization_notional * 100.0
                max_open_loss_pct = min(max_open_loss_pct, mark_to_market)
                continue
            stopped = False
            restart_count += 1

        if post_stop_rolling and prev_close > 0:
            anchor = prev_close
        else:
            anchor = step.anchor if step is not None else open_price
        band_mode = (
            step is not None
            and step.band_lower is not None
            and step.band_upper is not None
            and step.step_pct > 0
            and config.anchor_policy == "fixed"
            and not post_stop_rolling
        )
        if band_mode:
            assert step is not None and step.band_lower is not None and step.band_upper is not None
            levels = _band_levels(float(step.band_lower), float(step.band_upper), step.step_pct)
        else:
            levels = _day_levels(anchor, step_abs, max_positions) if step_abs > 0 else []
        level_values = [level for _, level in levels]
        if band_mode:
            assert step is not None and step.band_lower is not None and step.band_upper is not None
            day_close = float(bars[-1]["close"])
            if day_close > float(step.band_upper):
                upper_breakout_days += 1
            elif day_close < float(step.band_lower):
                lower_breakout_days += 1
        used_levels: set[int] = set()
        stop_price = None
        if config.stop_loss_pct > 0 and levels:
            lower_bound = (
                float(step.band_lower)
                if band_mode and step is not None and step.band_lower is not None
                else min(level for _, level in levels)
            )
            stop_price = lower_bound * (1.0 - max(0.0, float(config.stop_loss_pct)) / 100.0)

        limit_locked = False
        if config.price_limit_pct > 0 and prev_close > 0:
            flat = all(abs(float(bar["high"]) - float(bar["low"])) < 1e-9 for bar in bars)
            move = abs(float(bars[0]["close"]) / prev_close - 1.0) * 100.0
            limit_locked = flat and move >= float(config.price_limit_pct) - 1e-9
        if limit_locked:
            limit_locked_days += 1
            last_price = float(bars[-1]["close"])
            last_day = day
            mark_to_market = sum(
                (last_price - float(lot["price"])) * float(lot["shares"])
                for lot in open_lots
            ) / normalization_notional * 100.0
            max_open_loss_pct = min(max_open_loss_pct, mark_to_market)
            continue

        if stop_price is not None and open_price <= stop_price:
            trigger_stop(open_price)
            last_price = float(bars[-1]["close"])
            last_day = day
            continue

        # Gap handling: sell filled lots whose target is below the open, then
        # fill any buy levels that the open already gapped through.
        for lot in list(open_lots):
            if lot["buy_day"] < day and open_price >= float(lot["target"]):
                close_lot(lot, float(lot["target"]))
        if band_mode:
            start = bisect.bisect_left(level_values, open_price)
            end = (
                bisect.bisect_right(level_values, prev_close)
                if prev_close > 0
                else len(levels)
            )
            for index in range(end - 1, start - 1, -1):
                if len(open_lots) >= max_positions:
                    break
                level_index, level = levels[index]
                target = (
                    levels[index + 1][1]
                    if index + 1 < len(levels)
                    else level * (1.0 + (step.step_pct if step else 0.0) / 100.0)
                )
                if open_lot(level, level_index, step_abs, target):
                    used_levels.add(level_index)
        elif step_abs > 0:
            for level_index, level in levels:
                if len(open_lots) >= max_positions:
                    break
                if open_price <= level and open_lot(level, level_index, step_abs):
                    used_levels.add(level_index)
        max_positions_used = max(max_positions_used, len(open_lots))

        stopped_today = False
        for bar in bars:
            path = _bar_path(bar)
            last_price = float(bar["close"])
            last_day = day

            for previous, current in zip(path, path[1:]):
                if current > previous:
                    for lot in list(open_lots):
                        target = float(lot["target"])
                        if lot["buy_day"] < day and previous < target <= current:
                            close_lot(lot, target)
                elif current < previous:
                    if stop_price is not None and current <= stop_price:
                        trigger_stop(stop_price)
                        stopped_today = True
                        break
                    if band_mode:
                        start = bisect.bisect_left(level_values, current)
                        end = bisect.bisect_left(level_values, previous)
                        for index in range(end - 1, start - 1, -1):
                            if len(open_lots) >= max_positions:
                                break
                            level_index, level = levels[index]
                            if level_index in used_levels:
                                continue
                            target = (
                                levels[index + 1][1]
                                if index + 1 < len(levels)
                                else level * (1.0 + (step.step_pct if step else 0.0) / 100.0)
                            )
                            if open_lot(level, level_index, step_abs, target):
                                used_levels.add(level_index)
                    elif step_abs > 0:
                        for level_index, level in levels:
                            if len(open_lots) >= max_positions:
                                break
                            if level_index in used_levels:
                                continue
                            if current <= level < previous and open_lot(level, level_index, step_abs):
                                used_levels.add(level_index)

            max_positions_used = max(max_positions_used, len(open_lots))
            position_sum += len(open_lots)
            position_samples += 1
            mark_to_market = sum(
                (last_price - float(lot["price"])) * float(lot["shares"])
                for lot in open_lots
            ) / normalization_notional * 100.0
            max_open_loss_pct = min(max_open_loss_pct, mark_to_market)
            if stopped_today:
                break

    open_positions = [
        {
            "buy_day": lot["buy_day"],
            "buy_price": float(lot["price"]),
            "target_price": float(lot["target"]),
            "shares": float(lot["shares"]),
            "last_price": last_price,
            "unrealized_pct": (
                (last_price - float(lot["price"])) * float(lot["shares"])
                / normalization_notional * 100.0
            ),
            "holding_days": day_index.get(last_day, 0) - day_index.get(lot["buy_day"], 0) + 1,
        }
        for lot in open_lots
    ]
    open_position_pnl_pct = sum(float(item["unrealized_pct"]) for item in open_positions)
    open_position_count = len(open_positions)
    trading_days = len(days)
    annualized = net_return_pct * TRADING_DAYS / trading_days if trading_days > 0 else 0.0
    average_loop = statistics.mean(loop_returns) if loop_returns else 0.0
    average_positions = position_sum / position_samples if position_samples else 0.0
    net_profit_yuan = net_profit_total
    open_position_pnl_yuan = sum(
        (last_price - float(lot["price"])) * float(lot["shares"])
        for lot in open_lots
    )
    return {
        "loops": loops,
        "winning_loops": winning_loops,
        "gross_return_pct": gross_return_pct,
        "net_return_pct": net_return_pct,
        "annualized_net_return_pct": annualized,
        "friction_paid_pct": actual_fees / normalization_notional * 100.0,
        "slippage_paid_pct": slippage_paid / normalization_notional * 100.0,
        "avg_loop_return_pct": average_loop,
        "open_position_pnl_pct": open_position_pnl_pct,
        "total_return_pct": net_return_pct + open_position_pnl_pct,
        "max_open_loss_pct": max_open_loss_pct,
        "capital_return_pct": (
            net_profit_total / config.capital * 100.0 if config.capital > 0 else 0.0
        ),
        "used_capital_return_pct": (
            net_profit_total / peak_invested * 100.0 if peak_invested > 0 else 0.0
        ),
        "capital_utilization_pct": peak_invested / config.capital * 100.0 if config.capital else 0.0,
        "max_positions": max_positions,
        "max_positions_used": max_positions_used,
        "avg_positions": average_positions,
        "open_position_count": open_position_count,
        "grid_capital": grid_capital,
        "cash_remaining": cash,
        "peak_invested": peak_invested,
        "net_profit_yuan": net_profit_yuan,
        "open_position_pnl_yuan": open_position_pnl_yuan,
        "capital_constrained_buys": capital_constrained_buys,
        "limit_locked_days": limit_locked_days,
        "incomplete_days": incomplete_days,
        "stop_count": stop_count,
        "restart_count": restart_count,
        "stopped_days": stopped_days,
        "last_stop_day": last_stop_day,
        "upper_breakout_days": upper_breakout_days,
        "lower_breakout_days": lower_breakout_days,
        "first_trade_day": first_trade_day,
        "last_trade_day": last_trade_day,
        "open_positions": open_positions,
        "trading_days": trading_days,
    }


def detect_islands(points: list[dict[str, Any]], config: PlateauConfig) -> list[dict[str, Any]]:
    """Flag isolated spikes whose two neighbours fall off sharply."""
    islands: list[dict[str, Any]] = []
    for index in range(1, len(points) - 1):
        point = points[index]
        if point.get("below_safe"):
            continue
        value = float(point["net_return_pct"])
        left = value - float(points[index - 1]["net_return_pct"])
        right = value - float(points[index + 1]["net_return_pct"])
        threshold = max(
            config.island_min_drop_pct,
            abs(value) * config.island_drop_ratio,
        )
        if value > 0 and left >= threshold and right >= threshold:
            point["is_island"] = True
            islands.append(
                {
                    "k": float(point["k"]),
                    "net_return_pct": value,
                    "left_drop_pct": left,
                    "right_drop_pct": right,
                    "threshold_pct": threshold,
                }
            )
    return islands


def select_plateau(
    points: list[dict[str, Any]],
    config: PlateauConfig,
) -> dict[str, Any] | None:
    """Select the flattest high-return contiguous window, then pick centre-left."""
    if len(points) < 2:
        return None
    for item in points:
        item["in_plateau"] = False
        item["is_optimal"] = False
    window = min(max(2, config.plateau_window), len(points))
    best: tuple[float, float, float, int, int] | None = None
    best_selection: list[float] = []
    best_net: list[float] = []
    while window >= 2 and best is None:
        for start in range(0, len(points) - window + 1):
            candidates = points[start:start + window]
            if any(
                item.get("below_safe")
                or item.get("is_island")
                or int(item.get("loops", 0)) < config.min_loops
                for item in candidates
            ):
                continue
            selection_values = [
                float(item.get("selection_value", item["net_return_pct"]))
                for item in candidates
            ]
            net_values = [float(item["net_return_pct"]) for item in candidates]
            mean = statistics.mean(selection_values)
            stdev = statistics.pstdev(selection_values)
            score = mean - config.plateau_stability_penalty * stdev
            rank = (score, -stdev, -float(candidates[0]["k"]), start, window)
            if best is None or rank > best:
                best = rank
                best_selection = selection_values
                best_net = net_values
        if best is None:
            window -= 1
    if best is None:
        return None

    _, _, _, start, used_window = best
    plateau_points = points[start:start + used_window]
    for index in range(start, start + used_window):
        points[index]["in_plateau"] = True
    center_index = start + round((used_window - 1) * config.plateau_center_left_ratio)
    center_index = min(max(start, center_index), start + used_window - 1)
    points[center_index]["is_optimal"] = True
    center = points[center_index]
    mean = statistics.mean(best_selection)
    net_mean = statistics.mean(best_net)
    stdev = statistics.pstdev(best_selection)
    return {
        "k_left": float(plateau_points[0]["k"]),
        "k_right": float(plateau_points[-1]["k"]),
        "k_star": float(center["k"]),
        "window_points": used_window,
        "window_requested": config.plateau_window,
        "window_adjusted": used_window != config.plateau_window,
        "mean_net_return_pct": net_mean,
        "mean_selection_value": mean,
        "stdev_net_return_pct": stdev,
        "variance": stdev * stdev,
        "plateau_score": mean - config.plateau_stability_penalty * stdev,
        "mean_loops": statistics.mean(float(item["loops"]) for item in plateau_points),
        "total_loops": sum(int(item["loops"]) for item in plateau_points),
        "k_star_net_return_pct": float(center["net_return_pct"]),
        "k_star_loops": int(center["loops"]),
        "k_star_open_position_pnl_pct": float(center["open_position_pnl_pct"]),
        "k_star_total_return_pct": float(center["total_return_pct"]),
        "k_star_capital_return_pct": float(center.get("capital_return_pct", 0.0)),
        "k_star_max_positions_used": int(center.get("max_positions_used", 0)),
        "k_star_open_position_count": int(center.get("open_position_count", 0)),
        "k_star_stop_count": int(center.get("stop_count", 0)),
        "k_star_restart_count": int(center.get("restart_count", 0)),
        "profitable": mean > 0 and net_mean > 0,
    }


def prior_overlap(plateau: dict[str, Any] | None) -> dict[str, Any]:
    """Compare the measured plateau with the 0.65-0.80 x ATR prior."""
    if plateau is None:
        return {
            "prior_left": PRIOR_K_LEFT,
            "prior_right": PRIOR_K_RIGHT,
            "prior_anchor": PRIOR_K_ANCHOR,
            "overlap_left": None,
            "overlap_right": None,
            "overlap_width": 0.0,
            "overlap_ratio": 0.0,
            "contains_anchor": False,
            "matches": False,
            "k_star_relation": "no_plateau",
            "warning": "未识别到参数高原，无法与理论先验区间比对。",
        }

    left = float(plateau["k_left"])
    right = float(plateau["k_right"])
    k_star = float(plateau["k_star"])
    overlap_left = max(left, PRIOR_K_LEFT)
    overlap_right = min(right, PRIOR_K_RIGHT)
    overlap_width = max(0.0, overlap_right - overlap_left)
    plateau_width = max(0.0, right - left)
    contains_anchor = left <= PRIOR_K_ANCHOR <= right
    if k_star < PRIOR_K_LEFT:
        relation = "below_prior"
    elif k_star > PRIOR_K_RIGHT:
        relation = "above_prior"
    else:
        relation = "inside_prior"
    return {
        "prior_left": PRIOR_K_LEFT,
        "prior_right": PRIOR_K_RIGHT,
        "prior_anchor": PRIOR_K_ANCHOR,
        "overlap_left": overlap_left if overlap_width > 0 else None,
        "overlap_right": overlap_right if overlap_width > 0 else None,
        "overlap_width": overlap_width,
        "overlap_ratio": overlap_width / plateau_width if plateau_width > 0 else 0.0,
        "contains_anchor": contains_anchor,
        "matches": overlap_width > 0,
        "k_star_relation": relation,
        "warning": None if overlap_width > 0 else "实测高原与理论先验区间不重合，需要额外谨慎。",
    }


def front_running_adjust(
    d_raw_pct: float,
    latest_atr_pct: float,
    k_min_safe: float,
    config: PlateauConfig,
) -> dict[str, Any]:
    """Nudge a step sitting on a round-number wall downward."""
    safe_floor_pct = k_min_safe * latest_atr_pct
    if not config.front_run_thresholds:
        return {
            "adjusted": False,
            "threshold_pct": None,
            "offset_pct": 0.0,
            "d_exec_pct": d_raw_pct,
            "reason": None,
        }
    nearest = min(config.front_run_thresholds, key=lambda item: abs(d_raw_pct - item))
    distance = abs(d_raw_pct - nearest)
    if distance > config.front_run_band_pct:
        return {
            "adjusted": False,
            "threshold_pct": None,
            "offset_pct": 0.0,
            "d_exec_pct": d_raw_pct,
            "reason": None,
        }
    candidate = d_raw_pct - config.front_run_offset_pct
    if candidate <= 0.05 or candidate < safe_floor_pct:
        return {
            "adjusted": False,
            "threshold_pct": nearest,
            "offset_pct": 0.0,
            "d_exec_pct": d_raw_pct,
            "reason": "向下微调会跌破安全底线，保持原步长。",
        }
    return {
        "adjusted": True,
        "threshold_pct": nearest,
        "offset_pct": d_raw_pct - candidate,
        "d_exec_pct": candidate,
        "reason": f"检测到 {nearest:.1f}% 整数关口，向下微调以抢跑挂单墙。",
    }


def build_live_output(
    k_star: float,
    latest_atr_pct: float,
    latest_price: float,
    friction_pct: float,
    k_min_safe: float,
    config: PlateauConfig,
) -> dict[str, Any]:
    """Turn the dimensionless k* into today's executable step."""
    d_raw_pct = k_star * latest_atr_pct
    front_run = front_running_adjust(d_raw_pct, latest_atr_pct, k_min_safe, config)
    d_exec_pct = float(front_run["d_exec_pct"])
    k_exec = d_exec_pct / latest_atr_pct if latest_atr_pct > 0 else 0.0
    trade_notional = float(config.shares_per_grid) * latest_price
    fee_effective_pct = (
        max(float(config.fee), float(config.min_fee) / trade_notional * 100.0)
        if trade_notional > 0
        else float(config.fee)
    )
    effective_friction_pct = (
        2.0 * fee_effective_pct
        + STAMP_TAX * 100.0
        + max(0.0, float(config.spread_pct))
    )
    net_edge_pct = (
        d_exec_pct
        - effective_friction_pct
        - 2.0 * max(0.0, float(config.slippage_pct))
    )
    safe_floor_pct = k_min_safe * latest_atr_pct
    breakout_step = d_exec_pct + max(config.pullback_sell_pct, config.rebound_buy_pct)
    warnings: list[str] = []
    if net_edge_pct <= 0:
        warnings.append("执行步长未覆盖往返费用、价差与滑点，闭环套利没有正边际。")
    if front_run["reason"] and not front_run["adjusted"]:
        warnings.append(str(front_run["reason"]))
    if d_exec_pct < safe_floor_pct:
        warnings.append("执行步长低于 10 倍双边成本安全底线。")
    return {
        "k_star": k_star,
        "latest_atr_pct": latest_atr_pct,
        "latest_price": latest_price,
        "d_raw_pct": d_raw_pct,
        "d_raw_abs": latest_price * d_raw_pct / 100.0,
        "d_exec_pct": d_exec_pct,
        "d_exec_abs": latest_price * d_exec_pct / 100.0,
        "k_exec": k_exec,
        "friction_pct": friction_pct,
        "effective_friction_pct": effective_friction_pct,
        "net_edge_pct": net_edge_pct,
        "safe_floor_pct": safe_floor_pct,
        "front_run": front_run,
        "breakout": {
            "base_step_pct": d_exec_pct,
            "rebound_buy_pct": config.rebound_buy_pct,
            "pullback_sell_pct": config.pullback_sell_pct,
            "stretch_step_pct": breakout_step,
            "buy_trigger_price": latest_price * (1.0 - d_exec_pct / 100.0),
            "sell_trigger_price": latest_price * (1.0 + d_exec_pct / 100.0),
        },
        "warnings": warnings,
    }


def run_plateau_scan(
    bars_5m: list[dict],
    daily_bars: list[dict],
    config: PlateauConfig | None = None,
) -> dict[str, Any]:
    """Run the ATR-normalised k scan and return a chart-ready payload."""
    config = config or PlateauConfig()
    if not bars_5m or not daily_bars:
        raise InsufficientPlateauDataError("缺少 5 分钟或日线数据")
    if config.capital <= 0:
        raise ValueError("单格资金必须为正")
    if config.mode not in {"dynamic", "static_mean"}:
        raise ValueError(f"不支持的锚定模式：{config.mode}")

    k_values = plateau_k_values(config.k_start, config.k_end, config.k_step)
    atr_series = compute_atr_series(daily_bars, config.atr_period)
    if len(atr_series) < 2:
        raise InsufficientPlateauDataError("日线数据不足以计算 ATR 序列")

    bars_by_day = _group_bars(bars_5m)
    days = sorted(bars_by_day)
    if len(days) < 2:
        raise InsufficientPlateauDataError("5 分钟数据不足以形成交易日序列")
    anchors = build_daily_anchors(atr_series, days, config)
    holdout_count = int(round(len(days) * config.holdout_ratio))
    holdout_reason: str | None = None
    if holdout_count <= 0:
        in_days = days
        oos_days: list[str] = []
        holdout_reason = "holdout_ratio=0，未启用留出验证。"
    elif holdout_count < 10 or len(days) - holdout_count < 20:
        in_days = days
        oos_days = []
        holdout_reason = "数据不足以切分至少 20 个样本内交易日和 10 个留出交易日。"
    else:
        in_days = days[:-holdout_count]
        oos_days = days[-holdout_count:]
    in_days_set = set(in_days)
    valid_atr = [
        point.atr_pct
        for point in atr_series
        if point.atr_pct > 0 and point.trading_day in in_days_set
    ]
    if not valid_atr:
        raise InsufficientPlateauDataError("样本内 ATR 序列没有有效值")
    mean_atr_pct = statistics.mean(valid_atr)
    in_sample_closes = [
        point.close
        for point in atr_series
        if point.trading_day in in_days_set and point.close > 0
    ]
    reference_price = (
        statistics.mean(in_sample_closes) if in_sample_closes else atr_series[-1].close
    )
    friction_pct = effective_friction_pct(config, reference_price)
    k_min_safe = safe_k_floor(friction_pct, mean_atr_pct)
    in_bars_by_day = {day: bars_by_day[day] for day in in_days}
    first_day = in_days[0] if in_days else days[0]
    band_lower, band_upper, band_source = resolve_band(atr_series, first_day, config)

    points: list[dict[str, Any]] = []
    for k_value in k_values:
        start_pct = (
            fixed_step_pct(atr_series, first_day, config, k_value)
            if config.anchor_policy == "fixed"
            else None
        )
        day_steps = _build_day_steps(
            atr_series,
            days,
            config,
            k_value,
            anchors,
            band=(band_lower, band_upper),
            start_step_pct=start_pct,
        )
        simulation = simulate_k(in_bars_by_day, day_steps, config, reference_price)
        below_safe = k_value < k_min_safe
        points.append(
            {
                "k": k_value,
                "net_return_pct": simulation["net_return_pct"],
                "annualized_net_return_pct": simulation["annualized_net_return_pct"],
                "gross_return_pct": simulation["gross_return_pct"],
                "friction_paid_pct": simulation["friction_paid_pct"],
                "loops": simulation["loops"],
                "winning_loops": simulation["winning_loops"],
                "avg_loop_return_pct": simulation["avg_loop_return_pct"],
                "open_position_pnl_pct": simulation["open_position_pnl_pct"],
                "total_return_pct": simulation["total_return_pct"],
                "max_open_loss_pct": simulation["max_open_loss_pct"],
                "risk_adjusted_return_pct": simulation["net_return_pct"]
                + min(0.0, float(simulation["open_position_pnl_pct"])),
                "selection_value": simulation["net_return_pct"]
                - config.open_loss_penalty * max(0.0, -float(simulation["open_position_pnl_pct"])),
                "capital_return_pct": simulation["capital_return_pct"],
                "used_capital_return_pct": simulation["used_capital_return_pct"],
                "capital_utilization_pct": simulation["capital_utilization_pct"],
                "max_positions": simulation["max_positions"],
                "max_positions_used": simulation["max_positions_used"],
                "avg_positions": simulation["avg_positions"],
                "open_position_count": simulation["open_position_count"],
                "net_profit_yuan": simulation["net_profit_yuan"],
                "open_position_pnl_yuan": simulation["open_position_pnl_yuan"],
                "slippage_paid_pct": simulation["slippage_paid_pct"],
                "cash_remaining": simulation["cash_remaining"],
                "peak_invested": simulation["peak_invested"],
                "capital_constrained_buys": simulation["capital_constrained_buys"],
                "limit_locked_days": simulation["limit_locked_days"],
                "incomplete_days": simulation["incomplete_days"],
                "stop_count": simulation["stop_count"],
                "restart_count": simulation["restart_count"],
                "stopped_days": simulation["stopped_days"],
                "last_stop_day": simulation["last_stop_day"],
                "upper_breakout_days": simulation["upper_breakout_days"],
                "lower_breakout_days": simulation["lower_breakout_days"],
                "below_safe": below_safe,
                "is_island": False,
                "in_plateau": False,
                "is_optimal": False,
            }
        )

    islands = detect_islands(points, config)
    plateau = select_plateau(points, config)
    prior = prior_overlap(plateau)

    holdout: dict[str, Any] = {
        "enabled": bool(oos_days and plateau is not None),
        "reason": holdout_reason,
        "in_sample_start": in_days[0] if in_days else None,
        "in_sample_end": in_days[-1] if in_days else None,
        "oos_start": oos_days[0] if oos_days else None,
        "oos_end": oos_days[-1] if oos_days else None,
        "in_sample_days": len(in_days),
        "oos_days": len(oos_days),
        "k_star": None,
        "net_return_pct": None,
        "capital_return_pct": None,
        "loops": None,
        "open_position_pnl_pct": None,
        "max_positions_used": None,
        "max_open_loss_pct": None,
        "upper_breakout_days": None,
        "lower_breakout_days": None,
        "positive": None,
    }
    if oos_days and plateau is not None:
        oos_steps = _build_day_steps(
            atr_series,
            oos_days,
            config,
            float(plateau["k_star"]),
            anchors,
        )
        oos_simulation = simulate_k(
            {day: bars_by_day[day] for day in oos_days},
            oos_steps,
            config,
            reference_price,
        )
        holdout.update(
            {
                "k_star": float(plateau["k_star"]),
                "net_return_pct": oos_simulation["net_return_pct"],
                "capital_return_pct": oos_simulation["capital_return_pct"],
                "loops": oos_simulation["loops"],
                "open_position_pnl_pct": oos_simulation["open_position_pnl_pct"],
                "max_positions_used": oos_simulation["max_positions_used"],
                "max_open_loss_pct": oos_simulation["max_open_loss_pct"],
                "upper_breakout_days": oos_simulation["upper_breakout_days"],
                "lower_breakout_days": oos_simulation["lower_breakout_days"],
                "positive": oos_simulation["net_return_pct"] > 0,
            }
        )
    elif oos_days and plateau is None:
        holdout["reason"] = "样本内未识别到参数高原，无法进行留出验证。"

    latest = atr_series[-1]
    sorted_daily = sorted(
        daily_bars,
        key=lambda bar: str(bar.get("trading_day") or bar.get("date") or ""),
    )
    latest_price = float(sorted_daily[-1]["close"]) if sorted_daily else latest.close
    live = None
    live_unavailable_reason: str | None = None
    if all(point["below_safe"] for point in points):
        live_unavailable_reason = "所有 k 均低于 10 倍双边成本安全底线。"
    elif plateau is None:
        live_unavailable_reason = "未识别到参数高原。"
    elif not plateau["profitable"]:
        live_unavailable_reason = "识别到的合规高原没有正收益，无法给出实盘步长。"
    elif float(plateau["k_right"]) >= k_values[-1] - config.k_step - 1e-9:
        live_unavailable_reason = "合规高原顶到 k 扫描右边界，无法确认真实最优，请扩大 k 终点。"
    elif latest.atr_pct <= 0 or latest_price <= 0:
        live_unavailable_reason = "最新 ATR 或价格无效，无法还原实盘步长。"
    else:
        live = build_live_output(
            k_star=float(plateau["k_star"]),
            latest_atr_pct=latest.atr_pct,
            latest_price=latest_price,
            friction_pct=friction_pct,
            k_min_safe=k_min_safe,
            config=config,
        )

    raw_best = max(points, key=lambda item: float(item["net_return_pct"]))
    forbidden_count = sum(1 for point in points if point["below_safe"])
    min_bars = max(1, int(config.min_bars_per_day))
    incomplete_days = sum(1 for day in in_days if len(bars_by_day.get(day, [])) < min_bars)
    daily_days = {point.trading_day for point in atr_series}
    window_start = in_days[0] if in_days else ""
    window_end = in_days[-1] if in_days else ""
    missing_5m_days = sum(
        1
        for day in daily_days
        if window_start <= day <= window_end and day not in bars_by_day
    )
    anchor_description = {
        "daily_roll": "prior trading day close, re-anchored daily",
        "fixed_band": "prior close only after price exits the rolling band",
        "fixed": "first available prior close, fixed for the whole scan",
        "periodic": f"prior close every {config.reanchor_period_days} trading days",
    }.get(config.anchor_policy, config.anchor_policy)
    summary = {
        "k_count": len(k_values),
        "bar_count": len(bars_5m),
        "trading_days": len(in_days),
        "in_sample_days": len(in_days),
        "oos_days": len(oos_days),
        "total_days": len(days),
        "mean_atr_pct": mean_atr_pct,
        "friction_pct": friction_pct,
        "k_min_safe": k_min_safe,
        "max_positions": max(1, int(config.max_positions)),
        "grid_capital": config.capital,
        "anchor_policy": config.anchor_policy,
        "band_lower": band_lower,
        "band_upper": band_upper,
        "band_source": band_source,
        "min_loops": config.min_loops,
        "shares_per_grid": config.shares_per_grid,
        "slippage_pct": config.slippage_pct,
        "price_limit_pct": config.price_limit_pct,
        "stop_loss_pct": config.stop_loss_pct,
        "restart_cooldown_days": config.restart_cooldown_days,
        "open_loss_penalty": config.open_loss_penalty,
        "holdout_enabled": bool(oos_days and plateau is not None),
        "holdout_reason": holdout["reason"],
        "incomplete_days": incomplete_days,
        "missing_5m_days": missing_5m_days,
        "forbidden_k_count": forbidden_count,
        "all_forbidden": forbidden_count == len(points),
        "island_count": len(islands),
        "plateau_found": plateau is not None,
        "positive_plateau": bool(plateau and plateau["profitable"]),
        "raw_best_k": float(raw_best["k"]),
        "raw_best_net_return_pct": float(raw_best["net_return_pct"]),
        "best_inside_forbidden": bool(raw_best["below_safe"]),
        "plateau_at_safe_boundary": bool(
            plateau is not None
            and float(plateau["k_left"]) <= k_min_safe + config.k_step + 1e-9
        ),
        "plateau_at_right_edge": bool(
            plateau is not None
            and float(plateau["k_right"]) >= k_values[-1] - config.k_step - 1e-9
        ),
        "live_unavailable_reason": live_unavailable_reason,
        "sample_note": (
            f"前 {len(in_days)} 个交易日样本内选参，后 {len(oos_days)} 个交易日留出验证；"
            "不替代滚动样本外验证和最终盲测。"
        ),
    }
    config_payload = asdict(config)
    config_payload.update(
        {
            "friction_pct": friction_pct,
            "static_mean_basis": "expanding trailing mean of prior ATR14%",
            "atr_lookahead_free": True,
            "anchor": anchor_description,
            "fill_policy": "grid_line, A-share lot, slippage, price-limit lock guard",
        }
    )
    return {
        "config": config_payload,
        "k_values": k_values,
        "curve": points,
        "islands": islands,
        "plateau": plateau,
        "prior_validation": prior,
        "holdout": holdout,
        "live": live,
        "summary": summary,
        "data": {
            "start": in_days[0] if in_days else days[0],
            "end": in_days[-1] if in_days else days[-1],
            "full_start": days[0],
            "full_end": days[-1],
            "oos_start": oos_days[0] if oos_days else None,
            "oos_end": oos_days[-1] if oos_days else None,
            "latest_daily_day": latest.trading_day,
            "latest_price": latest_price,
            "latest_atr": latest.atr,
            "latest_atr_pct": latest.atr_pct,
            "atr_series_count": len(atr_series),
        },
    }
