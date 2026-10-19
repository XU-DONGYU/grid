# -*- coding: utf-8 -*-
"""A股网格交易参数分析器 · 兼容入口。

业务逻辑位于 grid_analyzer 包；此文件保持 `uvicorn app:app` 的启动方式不变，
并继续导出旧版函数，方便脚本和测试平滑迁移。
"""

from __future__ import annotations

import uvicorn

from grid_analyzer.api.routes import analyze, health, version
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
from grid_analyzer.main import app
from grid_analyzer.risk.rules import collect_risks
from grid_analyzer.utils.finance import commission, round_trip_cost_pct
from grid_analyzer.utils.stats import ema, linreg_slope, percentile_rank

__all__ = [
    "app",
    "analyze",
    "health",
    "version",
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


if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run("app:app", host=settings.host, port=settings.port)
