from __future__ import annotations

from datetime import date, timedelta

from grid_analyzer.api.schemas import PlateauRequest
from grid_analyzer.backtest.plateau import PlateauConfig, run_plateau_scan
from grid_analyzer.data.base import MarketDataProvider
from grid_analyzer.data.intraday import IntradayRepository


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
        start_text = start_date.isoformat()
        end_text = end_date.isoformat()

        bars_5m = self.repository.get_bars(request.code, "5", start_text, end_text)
        daily_bars = self.repository.get_bars(request.code, "d", start_text, end_text)

        config = PlateauConfig(
            grid_amount=request.grid_amount,
            fee=request.fee,
            min_fee=request.min_fee,
            spread_pct=request.spread_pct,
            friction_pct=request.friction_pct,
            k_start=request.k_start,
            k_end=request.k_end,
            k_step=request.k_step,
            mode=request.mode,
            atr_period=request.atr_period,
            plateau_window=request.plateau_window,
            plateau_stability_penalty=request.plateau_stability_penalty,
            plateau_center_left_ratio=request.plateau_center_left_ratio,
            island_drop_ratio=request.island_drop_ratio,
            island_min_drop_pct=request.island_min_drop_pct,
            front_run_thresholds=tuple(request.front_run_thresholds),
            front_run_band_pct=request.front_run_band_pct,
            front_run_offset_pct=request.front_run_offset_pct,
            pullback_sell_pct=request.pullback_sell_pct,
            rebound_buy_pct=request.rebound_buy_pct,
        )
        result = run_plateau_scan(bars_5m, daily_bars, config)

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
            "data_start": data["start"],
            "data_end": data["end"],
            "latest_daily_day": data["latest_daily_day"],
            "latest_price": data["latest_price"],
            "latest_atr": data["latest_atr"],
            "latest_atr_pct": data["latest_atr_pct"],
            "grid_amount": request.grid_amount,
            "fee": request.fee,
            "min_fee": request.min_fee,
            "spread_pct": request.spread_pct,
            "friction_pct": summary["friction_pct"],
            "mean_atr_pct": summary["mean_atr_pct"],
            "k_min_safe": summary["k_min_safe"],
            "mode": request.mode,
            "bar_count": len(bars_5m),
            "daily_count": len(daily_bars),
        }
        data_snapshot = {
            "source": "BaoStock",
            "code": request.code,
            "start": start_text,
            "end": end_text,
            "bar_count": len(bars_5m),
            "daily_count": len(daily_bars),
            "latest_atr14": data["latest_atr"],
            "latest_atr_pct": data["latest_atr_pct"],
            "atr_lookahead_free": True,
            "static_mean_basis": "expanding trailing mean of prior ATR14%",
        }
        result.pop("data", None)
        return {
            "context": context,
            **result,
            "data_snapshot": data_snapshot,
        }
