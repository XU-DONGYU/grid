from __future__ import annotations

from datetime import date, timedelta

from grid_analyzer.api.schemas import IntradayHeatmapRequest
from grid_analyzer.data.base import MarketDataProvider
from grid_analyzer.data.intraday import IntradayRepository
from grid_analyzer.indicators.axis import compute_axis
from grid_analyzer.indicators.volatility import compute_volatility
from grid_analyzer.services.intraday_research import (
    IntradayValidationConfig,
    run_intraday_validation,
)


class IntradayHeatmapService:
    def __init__(
        self,
        repository: IntradayRepository,
        quote_provider: MarketDataProvider | None = None,
    ) -> None:
        self.repository = repository
        self.quote_provider = quote_provider

    def run(self, request: IntradayHeatmapRequest) -> dict:
        end_date = date.today()
        start_date = end_date - timedelta(days=int(request.history_days * 1.6))
        start_text = start_date.isoformat()
        end_text = end_date.isoformat()

        bars_5m = self.repository.get_bars(request.code, "5", start_text, end_text)
        daily_bars = self.repository.get_bars(request.code, "d", start_text, end_text)
        if not bars_5m or not daily_bars:
            raise ValueError("没有可用的 5 分钟或日线数据")

        config = IntradayValidationConfig(
            capital=request.capital,
            fee=request.fee,
            min_fee=request.min_fee,
            init_position=request.init_position,
            stop_losses=tuple(request.stop_losses),
            k_start=request.k_start,
            k_end=request.k_end,
            k_step=request.k_step,
            window_days=request.window_days,
            in_sample_ratio=request.in_sample_ratio,
            final_blind_days=request.final_blind_days,
            min_oos_days=request.min_oos_days,
            primary_metric=request.primary_metric,
        )
        result = run_intraday_validation(bars_5m, daily_bars, config)

        closes = [bar["close"] for bar in daily_bars]
        axis = compute_axis(closes)
        vol = compute_volatility(daily_bars)
        window = daily_bars[-min(60, len(daily_bars)):]
        lower = min(bar["low"] for bar in window) * 1.02
        upper = max(bar["high"] for bar in window) * 0.98
        name = request.code
        if self.quote_provider is not None:
            try:
                quote = self.quote_provider.get_quote(request.code)
                name = quote.get("name") or request.code
            except Exception:
                name = request.code

        context = {
            "code": request.code,
            "name": name,
            "atr_pct": vol["atr_pct"],
            "range_lower": lower,
            "range_upper": upper,
            "capital": request.capital,
            "fee": request.fee,
            "min_fee": request.min_fee,
            "init_position": request.init_position,
            "data_start": bars_5m[0].get("trading_day", start_text),
            "data_end": bars_5m[-1].get("trading_day", end_text),
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
            "atr14": vol["atr"],
            "axis": axis["recommended"],
        }
        return {
            "context": context,
            "data_snapshot": data_snapshot,
            **result,
        }
