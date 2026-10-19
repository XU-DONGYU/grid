# -*- coding: utf-8 -*-
"""A股网格交易参数分析器 · FastAPI 兼容入口。

公式、网格设计与回测逻辑已拆分到 grid_analyzer 包。
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import requests
import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse

from grid_analyzer import __version__
from grid_analyzer.backtest.engine import _empty_backtest, run_backtest
from grid_analyzer.config import get_settings
from grid_analyzer.constants import (
    AUX_GAP_CAP,
    BACKTEST_DAYS,
    BUFFER,
    MAIN_GAP_CAP,
    STAMP_TAX,
    TRADING_DAYS,
)
from grid_analyzer.data.tencent import fetch_kline, fetch_quote, parse_code
from grid_analyzer.grid.designer import build_grids
from grid_analyzer.grid.spacing import design_grid
from grid_analyzer.indicators.axis import compute_axis
from grid_analyzer.indicators.liquidity import liquidity_grade
from grid_analyzer.indicators.scoring import fit_score
from grid_analyzer.indicators.trend import compute_trend
from grid_analyzer.indicators.volatility import (
    bollinger,
    bollinger_bandwidth_series,
    compute_atr,
    compute_volatility,
)
from grid_analyzer.logging import configure_logging
from grid_analyzer.risk.rules import collect_risks
from grid_analyzer.utils.finance import commission, round_trip_cost_pct
from grid_analyzer.utils.stats import ema, linreg_slope, percentile_rank

__all__ = [
    "app",
    "analyze",
    "health",
    "version",
    "index",
    "parse_code",
    "fetch_quote",
    "fetch_kline",
    "commission",
    "round_trip_cost_pct",
    "percentile_rank",
    "ema",
    "compute_axis",
    "compute_atr",
    "bollinger",
    "bollinger_bandwidth_series",
    "compute_volatility",
    "linreg_slope",
    "compute_trend",
    "fit_score",
    "liquidity_grade",
    "design_grid",
    "build_grids",
    "run_backtest",
    "_empty_backtest",
    "collect_risks",
    "STAMP_TAX",
    "BUFFER",
    "TRADING_DAYS",
    "MAIN_GAP_CAP",
    "AUX_GAP_CAP",
    "BACKTEST_DAYS",
]

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger("grid_analyzer.http")

app = FastAPI(title="A股网格交易参数分析器", version=__version__)


@app.middleware("http")
async def add_no_cache_headers(request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - started) * 1000
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    logger.info("%s %s -> %s %.1fms", request.method, request.url.path, response.status_code, elapsed_ms)
    return response


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "version": __version__, "env": settings.app_env}


@app.get("/api/version")
def version() -> dict:
    return {"version": __version__, "schema_version": 1}


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

@app.get("/", response_class=HTMLResponse)
def index():
    idx = Path(__file__).parent / "index.html"
    if idx.exists():
        return HTMLResponse(idx.read_text(encoding="utf-8"))
    return {"message": "A股网格交易参数分析器后端运行中，请将 index.html 放在同目录"}

if __name__ == "__main__":
    uvicorn.run("app:app", host=settings.host, port=settings.port)
