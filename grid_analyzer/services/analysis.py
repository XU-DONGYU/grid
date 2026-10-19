from __future__ import annotations

import requests
from fastapi import HTTPException

from grid_analyzer import __version__
from grid_analyzer.backtest.engine import run_backtest
from grid_analyzer.constants import BACKTEST_DAYS
from grid_analyzer.data.base import MarketDataProvider
from grid_analyzer.data.tencent import parse_code
from grid_analyzer.grid.designer import build_grids
from grid_analyzer.indicators.liquidity import liquidity_grade
from grid_analyzer.indicators.scoring import fit_score
from grid_analyzer.indicators.trend import compute_trend
from grid_analyzer.risk.rules import collect_risks


class AnalysisService:
    """Orchestrates data, indicators, grid design, backtest, and risk rules."""

    def __init__(self, provider: MarketDataProvider) -> None:
        self.provider = provider

    def analyze(
        self,
        code: str,
        capital: float = 100_000,
        fee: float = 0.025,
        min_fee: float = 5.0,
        main_ratio: float = 0.7,
        init_position: float = 0.0,
        stop_loss: float = 5.0,
    ) -> dict:
        single = main_ratio >= 0.999
        prefix, _ = parse_code(code)
        try:
            quote = self.provider.get_quote(code)
            all_klines = self.provider.get_klines(code, 250)
        except requests.RequestException:
            raise HTTPException(502, "行情服务暂时不可用，请稍后重试")
        except ValueError:
            raise HTTPException(502, "行情服务返回数据异常，请稍后重试")
        if len(all_klines) < 30:
            raise HTTPException(
                400,
                f"{quote['name']} 历史K线不足30个交易日，不适合做网格分析",
            )

        klines = all_klines[-BACKTEST_DAYS:]
        history_closes = [k["close"] for k in all_klines]
        high_52w = max(k["high"] for k in all_klines)
        low_52w = min(k["low"] for k in all_klines)

        mid = (
            (quote["ask"][0]["p"] + quote["bid"][0]["p"]) / 2
            if quote["ask"][0]["p"] > 0 and quote["bid"][0]["p"] > 0
            else quote["price"]
        )
        spread = (quote["ask"][0]["p"] - quote["bid"][0]["p"]) / mid if mid else 0
        spread_pct = max(spread, 0.0) * 100
        bid_depth = sum(b["p"] * b["v"] * 100 for b in quote["bid"])
        grade, grade_reason = liquidity_grade(spread_pct, quote["amount_wan"])

        main_grid, aux_grid, axis, vol = build_grids(
            klines,
            quote["price"],
            capital,
            single,
            main_ratio,
            spread_pct,
            fee,
            min_fee,
            history_closes=history_closes,
        )
        if main_grid["shares_per_grid"] <= 0:
            raise HTTPException(
                400,
                f"主网格每格资金不足一手（100股）约需 {100 * quote['price']:.0f} 元/格，请增大总资金或换低价标的",
            )

        trend20, trend60 = compute_trend(klines)
        boll_range = vol["boll_upper"] - vol["boll_lower"]
        pct_b = (quote["price"] - vol["boll_lower"]) / boll_range if boll_range > 0 else 0.5
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
                calib,
                calib[-1]["close"],
                capital,
                single,
                main_ratio,
                spread_pct,
                fee,
                min_fee,
                history_closes=[k["close"] for k in calib],
            )
        else:
            bt_main_grid, bt_aux_grid = main_grid, aux_grid

        bt_main = run_backtest(klines, bt_main_grid, fee, min_fee, init_position, stop_loss)
        bt_aux = (
            None
            if (single or bt_aux_grid["shares_per_grid"] <= 0)
            else run_backtest(klines, bt_aux_grid, fee, min_fee, init_position, stop_loss)
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
                "name": quote["name"],
                "code": quote["code"],
                "market_code": prefix,
                "price": quote["price"],
                "change": quote["change"],
                "change_pct": quote["change_pct"],
                "amount_wan": quote["amount_wan"],
                "turnover_pct": quote["turnover_pct"],
                "amplitude_pct": quote["amplitude_pct"],
                "high": quote["high"],
                "low": quote["low"],
                "high_52w": high_52w,
                "low_52w": low_52w,
                "total_mv": quote["total_mv"],
                "pe_ttm": quote["pe_ttm"],
            },
            "liquidity": {
                "grade": grade,
                "grade_reason": grade_reason,
                "spread_pct": spread_pct,
                "bid_depth_yuan": bid_depth,
            },
            "kline_tail": klines,
            "axis": axis,
            "volatility": vol,
            "trend": {
                "trend20_pct": trend20,
                "trend60_pct": trend60,
                "pct_b": pct_b,
                "regime": regime,
                "fit_score": score,
            },
            "main_grid": main_grid,
            "aux_grid": aux_grid,
            "round_trip_cost_pct": main_grid["round_trip_cost_pct"],
            "min_gap_pct": main_grid["min_gap_pct"],
            "backtest": {"main": bt_main, "aux": bt_aux},
            "backtest_meta": backtest_meta,
            "risks": [],
            "version": __version__,
        }
        data["risks"] = collect_risks(data)
        return data
