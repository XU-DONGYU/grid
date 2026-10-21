from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta

from grid_analyzer.api.schemas import PlateauRequest
from grid_analyzer.backtest.plateau import PlateauConfig, run_plateau_scan
from grid_analyzer.data.base import MarketDataProvider
from grid_analyzer.data.intraday import IntradayRepository

ANCHOR_POLICIES = ("fixed", "fixed_band", "periodic", "daily_roll")


def _comparison_row(policy: str, result: dict) -> dict:
    plateau = result.get("plateau")
    holdout = result.get("holdout") or {}
    summary = result.get("summary") or {}
    live = result.get("live")
    note = None
    if plateau is None:
        note = "未识别到合规高原"
    elif not plateau.get("profitable"):
        note = "合规高原没有正选参值"
    elif summary.get("plateau_at_right_edge"):
        note = "高原顶到 k 右边界"
    return {
        "anchor_policy": policy,
        "status": "ok",
        "error": None,
        "k_left": plateau.get("k_left") if plateau else None,
        "k_right": plateau.get("k_right") if plateau else None,
        "k_star": plateau.get("k_star") if plateau else None,
        "profitable": plateau.get("profitable") if plateau else None,
        "in_sample_net_return_pct": plateau.get("k_star_net_return_pct") if plateau else None,
        "in_sample_capital_return_pct": plateau.get("k_star_capital_return_pct") if plateau else None,
        "holdout_net_return_pct": holdout.get("net_return_pct"),
        "holdout_positive": holdout.get("positive"),
        "live_d_exec_pct": live.get("d_exec_pct") if live else None,
        "stop_count": plateau.get("k_star_stop_count") if plateau else None,
        "restart_count": plateau.get("k_star_restart_count") if plateau else None,
        "plateau_at_right_edge": summary.get("plateau_at_right_edge"),
        "plateau_at_safe_boundary": summary.get("plateau_at_safe_boundary"),
        "note": note,
    }


class PlateauService:
    """Data orchestration for the experimental ATR-normalised plateau."""

    def __init__(
        self,
        repository: IntradayRepository,
        quote_provider: MarketDataProvider | None = None,
    ) -> None:
        self.repository = repository
        self.quote_provider = quote_provider

    def run(self, request: PlateauRequest) -> dict:
        end_date = date.today()
        start_date = end_date - timedelta(days=int(request.history_days * 1.6))
        daily_start_date = start_date - timedelta(
            days=int(request.band_lookback_days * 1.6)
        )
        start_text = start_date.isoformat()
        daily_start_text = daily_start_date.isoformat()
        end_text = end_date.isoformat()

        bars_5m = self.repository.get_bars(request.code, "5", start_text, end_text)
        daily_bars = self.repository.get_bars(request.code, "d", daily_start_text, end_text)

        config = PlateauConfig(
            capital=request.capital,
            shares_per_grid=request.shares_per_grid,
            max_positions=request.max_positions,
            fee=request.fee,
            min_fee=request.min_fee,
            spread_pct=request.spread_pct,
            slippage_pct=request.slippage_pct,
            friction_pct=request.friction_pct,
            k_start=request.k_start,
            k_end=request.k_end,
            k_step=request.k_step,
            mode=request.mode,
            anchor_policy=request.anchor_policy,
            band_lower=request.band_lower,
            band_upper=request.band_upper,
            band_lookback_days=request.band_lookback_days,
            band_buffer_pct=request.band_buffer_pct,
            reanchor_period_days=request.reanchor_period_days,
            atr_period=request.atr_period,
            plateau_window=request.plateau_window,
            plateau_stability_penalty=request.plateau_stability_penalty,
            plateau_center_left_ratio=request.plateau_center_left_ratio,
            min_loops=request.min_loops,
            open_loss_penalty=request.open_loss_penalty,
            island_drop_ratio=request.island_drop_ratio,
            island_min_drop_pct=request.island_min_drop_pct,
            front_run_thresholds=tuple(request.front_run_thresholds),
            front_run_band_pct=request.front_run_band_pct,
            front_run_offset_pct=request.front_run_offset_pct,
            pullback_sell_pct=request.pullback_sell_pct,
            rebound_buy_pct=request.rebound_buy_pct,
            price_limit_pct=request.price_limit_pct,
            min_bars_per_day=request.min_bars_per_day,
            holdout_ratio=request.holdout_ratio,
            stop_loss_pct=request.stop_loss_pct,
            restart_cooldown_days=request.restart_cooldown_days,
        )
        result = run_plateau_scan(bars_5m, daily_bars, config)
        comparison = [_comparison_row(config.anchor_policy, result)]
        if request.compare_anchor_policies:
            for policy in ANCHOR_POLICIES:
                if policy == config.anchor_policy:
                    continue
                try:
                    compared = run_plateau_scan(
                        bars_5m,
                        daily_bars,
                        replace(config, anchor_policy=policy),
                    )
                    comparison.append(_comparison_row(policy, compared))
                except Exception as exc:  # one policy must not break the table
                    comparison.append(
                        {
                            "anchor_policy": policy,
                            "status": "error",
                            "error": str(exc),
                            "k_left": None,
                            "k_right": None,
                            "k_star": None,
                            "profitable": None,
                            "in_sample_net_return_pct": None,
                            "in_sample_capital_return_pct": None,
                            "holdout_net_return_pct": None,
                            "holdout_positive": None,
                            "live_d_exec_pct": None,
                            "stop_count": None,
                            "restart_count": None,
                            "plateau_at_right_edge": None,
                            "plateau_at_safe_boundary": None,
                            "note": "该策略计算失败",
                        }
                    )
            order = {policy: index for index, policy in enumerate(ANCHOR_POLICIES)}
            comparison.sort(key=lambda row: order.get(row["anchor_policy"], 99))

        name = request.code
        if self.quote_provider is not None:
            try:
                quote = self.quote_provider.get_quote(request.code)
                name = quote.get("name") or request.code
            except Exception:
                name = request.code

        data = result["data"]
        summary = result["summary"]
        context = {
            "code": request.code,
            "name": name,
            "data_start": data["full_start"],
            "data_end": data["full_end"],
            "latest_daily_day": data["latest_daily_day"],
            "latest_price": data["latest_price"],
            "latest_atr": data["latest_atr"],
            "latest_atr_pct": data["latest_atr_pct"],
            "capital": request.capital,
            "shares_per_grid": request.shares_per_grid,
            "max_positions": request.max_positions,
            "grid_capital": request.capital,
            "fee": request.fee,
            "min_fee": request.min_fee,
            "spread_pct": request.spread_pct,
            "slippage_pct": request.slippage_pct,
            "friction_pct": summary["friction_pct"],
            "mean_atr_pct": summary["mean_atr_pct"],
            "k_min_safe": summary["k_min_safe"],
            "mode": request.mode,
            "anchor_policy": request.anchor_policy,
            "band_lower": summary["band_lower"],
            "band_upper": summary["band_upper"],
            "band_source": summary["band_source"],
            "price_limit_pct": request.price_limit_pct,
            "stop_loss_pct": request.stop_loss_pct,
            "restart_cooldown_days": request.restart_cooldown_days,
            "bar_count": len(bars_5m),
            "daily_count": len(daily_bars),
        }
        data_snapshot = {
            "source": "BaoStock",
            "code": request.code,
            "start": start_text,
            "daily_start": daily_start_text,
            "end": end_text,
            "full_start": data["full_start"],
            "full_end": data["full_end"],
            "band_lower": summary["band_lower"],
            "band_upper": summary["band_upper"],
            "band_source": summary["band_source"],
            "bar_count": len(bars_5m),
            "daily_count": len(daily_bars),
            "latest_atr14": data["latest_atr"],
            "latest_atr_pct": data["latest_atr_pct"],
            "max_positions": request.max_positions,
            "shares_per_grid": request.shares_per_grid,
            "grid_capital": request.capital,
            "stop_loss_pct": request.stop_loss_pct,
            "restart_cooldown_days": request.restart_cooldown_days,
            "atr_lookahead_free": True,
            "static_mean_basis": "expanding trailing mean of prior ATR14%",
        }
        result.pop("data", None)
        return {
            "context": context,
            **result,
            "policy_comparison": comparison,
            "data_snapshot": data_snapshot,
        }
