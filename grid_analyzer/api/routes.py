from __future__ import annotations

from typing import Literal

import requests
from fastapi import APIRouter, Depends, HTTPException, Query

from grid_analyzer import __version__
from grid_analyzer.api.schemas import (
    AnalyzeData,
    AnalyzeResponse,
    HealthResponse,
    HeatmapPayload,
    HeatmapResponse,
    IntradayHeatmapData,
    IntradayHeatmapRequest,
    IntradayHeatmapResponse,
    VersionResponse,
)
from grid_analyzer.config import get_settings
from grid_analyzer.constants import SCHEMA_VERSION
from grid_analyzer.data.base import MarketDataProvider
from grid_analyzer.data.intraday import IntradayRepository, NoDataError
from grid_analyzer.data.tencent import TencentMarketDataProvider
from grid_analyzer.services.analysis import AnalysisService
from grid_analyzer.services.heatmap import build_heatmap_payload
from grid_analyzer.services.intraday_heatmap import IntradayHeatmapService
from grid_analyzer.services.intraday_research import InsufficientIntradayDataError
from grid_analyzer.services.research import run_parameter_sweep

router = APIRouter()


def get_market_data_provider() -> MarketDataProvider:
    return TencentMarketDataProvider()


def get_analysis_service(
    provider: MarketDataProvider = Depends(get_market_data_provider),
) -> AnalysisService:
    return AnalysisService(provider)


def get_intraday_repository() -> IntradayRepository:
    return IntradayRepository()


@router.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(ok=True, version=__version__, env=get_settings().app_env)


@router.get("/api/version", response_model=VersionResponse)
def version() -> VersionResponse:
    return VersionResponse(version=__version__, schema_version=SCHEMA_VERSION)


@router.get("/api/analyze", response_model=AnalyzeResponse)
def analyze(
    code: str = Query(..., description="股票代码，如 600000 / sz000001"),
    capital: float = Query(100000, ge=1000, le=1e8, description="总资金（元）"),
    fee: float = Query(0.025, ge=0, le=0.3, description="单边佣金费率（%）"),
    min_fee: float = Query(5.0, ge=0, le=100, description="单笔最低佣金（元）"),
    main_ratio: float = Query(0.7, ge=0.5, le=1.0, description="主网格资金占比"),
    init_position: float = Query(0.0, ge=0, le=1.0, description="初始底仓占总资金比例，0=中性零底仓"),
    stop_loss: float = Query(5.0, ge=0, le=50, description="跌破网格下限后的清仓止损幅度（%），0=关闭"),
    service: AnalysisService = Depends(get_analysis_service),
) -> AnalyzeResponse:
    data = service.analyze(
        code=code,
        capital=capital,
        fee=fee,
        min_fee=min_fee,
        main_ratio=main_ratio,
        init_position=init_position,
        stop_loss=stop_loss,
    )
    return AnalyzeResponse(data=AnalyzeData.model_validate(data))


def _float_list(value: str, name: str) -> list[float]:
    try:
        items = [float(item.strip()) for item in value.split(",") if item.strip()]
    except ValueError:
        raise HTTPException(400, f"{name} 需要逗号分隔的数字")
    if not items:
        raise HTTPException(400, f"{name} 不能为空")
    return items


@router.get("/api/heatmap", response_model=HeatmapResponse)
def heatmap(
    code: str = Query(..., description="股票代码，如 002541"),
    capital: float = Query(100000, ge=1000, le=1e8),
    fee: float = Query(0.025, ge=0, le=0.3, description="单边佣金 %"),
    min_fee: float = Query(5.0, ge=0, le=100, description="单笔最低佣金"),
    history_days: int = Query(250, ge=120, le=2000),
    calib_days: int = Query(120, ge=60, le=1000),
    test_days: int = Query(60, ge=20, le=500),
    step: int = Query(60, ge=20, le=500),
    gap_scales: str = Query("0.8,0.9,1.0,1.1,1.2"),
    stop_losses: str = Query("0,3,5,8"),
    init_positions: str = Query("0,0.2"),
    metric: Literal[
        "plateau_score",
        "mean_return_pct",
        "compounded_return_pct",
        "worst_return_pct",
        "max_drawdown_pct",
    ] = Query("plateau_score"),
    spread_pct: float = Query(0.05, ge=0, le=5, description="历史价差代理 %"),
    provider: MarketDataProvider = Depends(get_market_data_provider),
) -> HeatmapResponse:
    try:
        quote = provider.get_quote(code)
        klines = provider.get_klines(code, history_days)
    except requests.RequestException:
        raise HTTPException(502, "行情服务暂时不可用，请稍后重试")
    except ValueError:
        raise HTTPException(502, "行情服务返回数据异常，请稍后重试")

    if len(klines) < calib_days + test_days:
        raise HTTPException(
            400,
            f"历史数据不足：需要 {calib_days + test_days} 条，实际 {len(klines)} 条",
        )

    results = run_parameter_sweep(
        klines,
        gap_scales=_float_list(gap_scales, "gap_scales"),
        stop_losses=_float_list(stop_losses, "stop_losses"),
        init_positions=_float_list(init_positions, "init_positions"),
        capital=capital,
        fee=fee,
        min_fee=min_fee,
        main_ratio=1.0,
        spread_pct=spread_pct,
        calib_days=calib_days,
        test_days=test_days,
        step=step,
        single=True,
    )
    if not results:
        raise HTTPException(400, "没有可用的 walk-forward 窗口，请增加历史数据或减小窗口")

    payload = build_heatmap_payload(results, code=code, metric=metric)
    payload["name"] = quote.get("name", "")
    return HeatmapResponse(data=HeatmapPayload.model_validate(payload))


@router.post("/api/intraday-heatmap", response_model=IntradayHeatmapResponse)
def intraday_heatmap(
    request: IntradayHeatmapRequest,
    repository: IntradayRepository = Depends(get_intraday_repository),
    quote_provider: MarketDataProvider = Depends(get_market_data_provider),
) -> IntradayHeatmapResponse:
    service = IntradayHeatmapService(repository, quote_provider)
    try:
        data = service.run(request)
    except InsufficientIntradayDataError as exc:
        raise HTTPException(400, str(exc))
    except NoDataError as exc:
        raise HTTPException(404, str(exc))
    except RuntimeError as exc:
        raise HTTPException(502, str(exc))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return IntradayHeatmapResponse(data=IntradayHeatmapData.model_validate(data))
