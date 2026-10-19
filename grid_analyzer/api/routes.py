from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from grid_analyzer import __version__
from grid_analyzer.api.schemas import (
    AnalyzeData,
    AnalyzeResponse,
    HealthResponse,
    VersionResponse,
)
from grid_analyzer.config import get_settings
from grid_analyzer.constants import SCHEMA_VERSION
from grid_analyzer.data.base import MarketDataProvider
from grid_analyzer.data.tencent import TencentMarketDataProvider
from grid_analyzer.services.analysis import AnalysisService

router = APIRouter()


def get_market_data_provider() -> MarketDataProvider:
    return TencentMarketDataProvider()


def get_analysis_service(
    provider: MarketDataProvider = Depends(get_market_data_provider),
) -> AnalysisService:
    return AnalysisService(provider)


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
