from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from grid_analyzer.constants import SCHEMA_VERSION


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class AnalyzeParams(ApiModel):
    capital: float
    fee_pct: float
    min_fee: float
    main_ratio: float
    single_grid: bool
    init_position_pct: float
    stop_loss_pct: float
    backtest_days: int


class QuoteInfo(ApiModel):
    name: str
    code: str
    market_code: str
    price: float
    change: float
    change_pct: float
    amount_wan: float
    turnover_pct: float
    amplitude_pct: float
    high: float
    low: float
    high_52w: float
    low_52w: float
    total_mv: float
    pe_ttm: float


class LiquidityInfo(ApiModel):
    grade: str
    grade_reason: str
    spread_pct: float
    bid_depth_yuan: float


class AxisInfo(ApiModel):
    median60: float
    mean60: float
    ma20: float
    ma60: float
    recommended: float


class VolatilityInfo(ApiModel):
    sigma_daily_pct: float
    sigma_annual_pct: float
    vol_of_vol_pct: float
    atr: float
    atr_pct: float
    boll_upper: float
    boll_lower: float
    boll_width_pct: float
    boll_width_percentile: float
    squeeze: bool
    ttm_squeeze: bool
    keltner_upper: float
    keltner_lower: float


class TrendInfo(ApiModel):
    trend20_pct: float
    trend60_pct: float
    pct_b: float
    regime: str
    fit_score: int


class Kline(ApiModel):
    date: str
    open: float
    close: float
    high: float
    low: float
    volume: float


class GridPlan(ApiModel):
    lower: float
    upper: float
    gap_pct: float
    atr_gap_pct: float
    levels: list[float]
    capital: float
    shares_per_grid: int
    grid_cost: float
    capital_required: float
    capital_utilization_pct: float
    round_trip_cost_pct: float
    min_gap_pct: float
    capital_constrained: bool
    gap_scale: float


class EquityPoint(ApiModel):
    date: str
    equity: float
    price: float
    position_value: float


class BacktestResult(ApiModel):
    rounds: int
    buy_count: int
    sell_count: int
    net_profit: float
    return_pct: float
    annual_pct: float
    max_holding_cnt: int
    max_position_cost: float
    max_drawdown_pct: float
    end_holding: int
    end_holding_qty: int
    end_holding_value: float
    end_cash: float
    min_float_pnl: float
    min_equity_pnl: float
    total_fees: float
    realized_pnl: float
    unrealized_pnl: float
    skipped_buys: int
    stop_triggered: bool
    stop_date: str | None = None
    stop_price: float
    stop_fill_price: float
    init_cost: float
    turnover: float
    equity_curve: list[EquityPoint] = Field(default_factory=list)


class BacktestPair(ApiModel):
    main: BacktestResult
    aux: BacktestResult | None = None


class BacktestMeta(ApiModel):
    used_calibration: bool
    calibration_days: int
    start_date: str
    end_date: str
    main_lower: float
    main_upper: float
    main_gap_pct: float
    main_shares_per_grid: int
    lookahead_free: bool


class AnalyzeData(ApiModel):
    params: AnalyzeParams
    quote: QuoteInfo
    liquidity: LiquidityInfo
    kline_tail: list[Kline]
    axis: AxisInfo
    volatility: VolatilityInfo
    trend: TrendInfo
    main_grid: GridPlan
    aux_grid: GridPlan
    round_trip_cost_pct: float
    min_gap_pct: float
    backtest: BacktestPair
    backtest_meta: BacktestMeta
    risks: list[str]
    version: str


class AnalyzeResponse(ApiModel):
    ok: bool = True
    schema_version: int = SCHEMA_VERSION
    data: AnalyzeData


class HealthResponse(ApiModel):
    ok: bool
    version: str
    env: str


class VersionResponse(ApiModel):
    version: str
    schema_version: int = SCHEMA_VERSION


class HeatmapCell(ApiModel):
    gap_scale: float
    stop_loss: float
    value: float
    count: int
    color: str
    is_best: bool


class HeatmapBest(ApiModel):
    gap_scale: float
    stop_loss: float
    value: float
    count: int


class HeatmapPayload(ApiModel):
    name: str = ""
    code: str
    metric: str
    metric_label: str
    direction: str
    gap_scales: list[float]
    stop_losses: list[float]
    init_positions: list[float]
    low: float
    high: float
    best: HeatmapBest | None = None
    cells: list[HeatmapCell]
    sample_count: int


class HeatmapResponse(ApiModel):
    ok: bool = True
    schema_version: int = SCHEMA_VERSION
    data: HeatmapPayload


class IntradayHeatmapRequest(ApiModel):
    code: str
    capital: float = Field(100000, ge=1000, le=1e8)
    fee: float = Field(0.025, ge=0, le=0.3)
    min_fee: float = Field(5.0, ge=0, le=100)
    init_position: float = Field(0.0, ge=0, le=1.0)
    stop_losses: list[float] = Field(default_factory=lambda: [0.0, 3.0, 5.0, 8.0])
    k_start: float = Field(0.5, gt=0)
    k_end: float = Field(1.5, gt=0)
    k_step: float = Field(0.05, gt=0)
    window_days: int = Field(126, ge=10, le=252)
    in_sample_ratio: float = Field(0.70, gt=0, lt=1)
    final_blind_days: int = Field(63, ge=0, le=252)
    min_oos_days: int = Field(252, ge=0, le=1000)
    primary_metric: Literal[
        "realized_annual_pct",
        "total_annual_pct",
        "calmar",
        "sharpe",
        "sortino",
        "max_drawdown_pct",
    ] = "realized_annual_pct"
    history_days: int = Field(500, ge=60, le=3000)

    @field_validator("stop_losses")
    @classmethod
    def validate_stop_losses(cls, value: list[float]) -> list[float]:
        if not value:
            raise ValueError("stop_losses 不能为空")
        return sorted({float(item) for item in value})


class IntradayContext(ApiModel):
    code: str
    name: str = ""
    atr_pct: float
    range_lower: float
    range_upper: float
    capital: float
    fee: float
    min_fee: float
    init_position: float
    data_start: str
    data_end: str
    bar_count: int
    daily_count: int


class AggregatedMetric(ApiModel):
    mean: float
    stdev: float
    worst: float


class IntradayCell(ApiModel):
    k: float
    stop_loss: float
    fold_count: int
    metrics: dict[str, AggregatedMetric]
    plateau_score: float


class IntradayFold(ApiModel):
    in_sample_start: str
    in_sample_end: str
    oos_start: str
    oos_end: str
    oos_days: int
    selected_k: float
    selected_stop_loss: float
    atr_pct: float
    gap_pct: float
    capital_constrained: bool
    in_sample_metrics: dict[str, float | None]
    oos_metrics: dict[str, float | None]


class ParameterStability(ApiModel):
    k_values: list[float]
    stop_losses: list[float]
    change_count: int


class BlindResult(ApiModel):
    start: str
    end: str
    k: float
    stop_loss: float
    gap_pct: float
    metrics: dict[str, float | None]


class LockedParams(ApiModel):
    k: float
    stop_loss: float
    blind: BlindResult | None = None


class IntradaySummary(ApiModel):
    fold_count: int
    oos_coverage_days: int
    oos_coverage_months: float
    positive_oos_ratio: float
    oos_primary_mean: float
    oos_primary_worst: float
    oos_primary_stdev: float


class IntradayHeatmapData(ApiModel):
    context: IntradayContext
    k_values: list[float]
    stop_losses: list[float]
    in_sample_days: int
    oos_days: int
    folds: list[IntradayFold]
    cells: list[IntradayCell]
    parameter_stability: ParameterStability
    locked: LockedParams
    summary: IntradaySummary
    config: dict
    data_snapshot: dict


class IntradayHeatmapResponse(ApiModel):
    ok: bool = True
    schema_version: int = SCHEMA_VERSION
    data: IntradayHeatmapData
