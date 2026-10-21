from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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


class IntradayJobCreateData(ApiModel):
    job_id: str
    status: str


class IntradayJobCreateResponse(ApiModel):
    ok: bool = True
    schema_version: int = SCHEMA_VERSION
    data: IntradayJobCreateData


class IntradayJobStatusData(ApiModel):
    job_id: str
    status: str
    error: str | None = None
    result: IntradayHeatmapData | None = None
    created_at: str
    updated_at: str


class IntradayJobStatusResponse(ApiModel):
    ok: bool = True
    schema_version: int = SCHEMA_VERSION
    data: IntradayJobStatusData


class PlateauRequest(ApiModel):
    code: str
    capital: float = Field(100_000, ge=1000, le=1e8)
    shares_per_grid: int = Field(100, ge=1, le=10000)
    max_positions: int = Field(8, ge=1, le=50)
    penetration_abs: float = Field(0.01, ge=0, le=10)
    fee: float = Field(0.025, ge=0, le=0.3)
    min_fee: float = Field(5.0, ge=0, le=100)
    spread_pct: float = Field(0.05, ge=0, le=5)
    slippage_pct: float = Field(0.02, ge=0, le=5)
    friction_pct: float | None = Field(None, ge=0, le=10)
    k_start: float = Field(0.20, gt=0, le=10)
    k_end: float = Field(2.50, gt=0, le=10)
    k_step: float = Field(0.05, gt=0, le=1)
    mode: Literal["dynamic", "static_mean"] = "dynamic"
    anchor_policy: Literal["daily_roll", "fixed_band", "fixed", "periodic"] = "fixed"
    band_lower: float | None = Field(None, gt=0)
    band_upper: float | None = Field(None, gt=0)
    band_lookback_days: int = Field(60, ge=5, le=500)
    band_buffer_pct: float = Field(2.0, ge=0, le=20)
    reanchor_period_days: int = Field(20, ge=1, le=250)
    atr_period: int = Field(14, ge=2, le=100)
    plateau_window: int = Field(5, ge=2, le=21)
    plateau_stability_penalty: float = Field(0.5, ge=0, le=5)
    plateau_center_left_ratio: float = Field(0.35, ge=0, le=1)
    min_loops: int = Field(10, ge=0, le=10000)
    open_loss_penalty: float = Field(0.5, ge=0, le=5)
    island_drop_ratio: float = Field(0.25, ge=0, le=2)
    island_min_drop_pct: float = Field(0.20, ge=0, le=100)
    front_run_thresholds: list[float] = Field(
        default_factory=lambda: [1.0, 2.0, 3.0, 5.0]
    )
    front_run_band_pct: float = Field(0.08, ge=0, le=1)
    front_run_offset_pct: float = Field(0.20, ge=0, le=1)
    pullback_sell_pct: float = Field(0.30, ge=0, le=5)
    rebound_buy_pct: float = Field(0.30, ge=0, le=5)
    price_limit_pct: float = Field(10.0, ge=0, le=50)
    min_bars_per_day: int = Field(1, ge=1, le=100)
    holdout_ratio: float = Field(0.30, ge=0, le=0.8)
    stop_loss_pct: float = Field(5.0, ge=0, le=50)
    restart_cooldown_days: int = Field(0, ge=0, le=60)
    compare_anchor_policies: bool = False
    history_days: int = Field(500, ge=60, le=3000)

    @field_validator("front_run_thresholds")
    @classmethod
    def validate_front_run_thresholds(cls, value: list[float]) -> list[float]:
        cleaned = sorted({float(item) for item in value if float(item) > 0})
        if not cleaned:
            raise ValueError("front_run_thresholds 不能为空")
        return cleaned

    @model_validator(mode="after")
    def validate_k_range(self) -> "PlateauRequest":
        if self.k_end <= self.k_start:
            raise ValueError("k_end 必须大于 k_start")
        if (self.band_lower is None) != (self.band_upper is None):
            raise ValueError("band_lower 和 band_upper 必须同时提供或同时留空")
        if (
            self.band_lower is not None
            and self.band_upper is not None
            and self.band_upper <= self.band_lower
        ):
            raise ValueError("band_upper 必须大于 band_lower")
        return self


class PlateauPoint(ApiModel):
    k: float
    net_return_pct: float
    annualized_net_return_pct: float
    gross_return_pct: float
    friction_paid_pct: float
    loops: int
    winning_loops: int
    avg_loop_return_pct: float
    open_position_pnl_pct: float
    total_return_pct: float
    max_open_loss_pct: float
    risk_adjusted_return_pct: float
    selection_value: float
    capital_return_pct: float
    used_capital_return_pct: float
    capital_utilization_pct: float
    max_positions: int
    max_positions_used: int
    avg_positions: float
    open_position_count: int
    net_profit_yuan: float
    realized_profit_yuan: float
    open_position_pnl_yuan: float
    total_pnl_yuan: float
    ending_equity_yuan: float
    realized_return_pct: float
    open_position_return_pct: float
    ending_equity_return_pct: float
    slippage_paid_pct: float
    cash_remaining: float
    peak_invested: float
    capital_constrained_buys: int
    limit_locked_days: int
    incomplete_days: int
    stop_count: int
    restart_count: int
    stopped_days: int
    last_stop_day: str | None = None
    upper_breakout_days: int
    lower_breakout_days: int
    below_safe: bool
    is_island: bool
    in_plateau: bool
    is_optimal: bool


class PlateauIsland(ApiModel):
    k: float
    net_return_pct: float
    left_drop_pct: float
    right_drop_pct: float
    threshold_pct: float


class PlateauBand(ApiModel):
    k_left: float
    k_right: float
    k_star: float
    window_points: int
    window_requested: int
    window_adjusted: bool
    mean_net_return_pct: float
    mean_selection_value: float
    stdev_net_return_pct: float
    variance: float
    plateau_score: float
    mean_loops: float
    total_loops: int
    k_star_net_return_pct: float
    k_star_loops: int
    k_star_open_position_pnl_pct: float
    k_star_total_return_pct: float
    k_star_capital_return_pct: float
    k_star_max_positions_used: int
    k_star_open_position_count: int
    k_star_stop_count: int
    k_star_restart_count: int
    k_star_realized_profit_yuan: float
    k_star_open_position_pnl_yuan: float
    k_star_total_pnl_yuan: float
    k_star_ending_equity_yuan: float
    k_star_ending_equity_return_pct: float
    profitable: bool


class PlateauPriorValidation(ApiModel):
    prior_left: float
    prior_right: float
    prior_anchor: float
    overlap_left: float | None = None
    overlap_right: float | None = None
    overlap_width: float
    overlap_ratio: float
    contains_anchor: bool
    matches: bool
    k_star_relation: str
    warning: str | None = None


class PlateauFrontRun(ApiModel):
    adjusted: bool
    threshold_pct: float | None = None
    offset_pct: float
    d_exec_pct: float
    reason: str | None = None


class PlateauBreakout(ApiModel):
    base_step_pct: float
    rebound_buy_pct: float
    pullback_sell_pct: float
    stretch_step_pct: float
    buy_trigger_price: float
    sell_trigger_price: float


class PlateauLive(ApiModel):
    k_star: float
    latest_atr_pct: float
    latest_price: float
    d_raw_pct: float
    d_raw_abs: float
    d_exec_pct: float
    d_exec_abs: float
    k_exec: float
    friction_pct: float
    effective_friction_pct: float
    net_edge_pct: float
    safe_floor_pct: float
    front_run: PlateauFrontRun
    breakout: PlateauBreakout
    warnings: list[str] = Field(default_factory=list)


class PlateauHoldout(ApiModel):
    enabled: bool
    reason: str | None = None
    in_sample_start: str | None = None
    in_sample_end: str | None = None
    oos_start: str | None = None
    oos_end: str | None = None
    in_sample_days: int
    oos_days: int
    k_star: float | None = None
    net_return_pct: float | None = None
    capital_return_pct: float | None = None
    loops: int | None = None
    open_position_pnl_pct: float | None = None
    max_positions_used: int | None = None
    max_open_loss_pct: float | None = None
    upper_breakout_days: int | None = None
    lower_breakout_days: int | None = None
    realized_profit_yuan: float | None = None
    open_position_pnl_yuan: float | None = None
    total_pnl_yuan: float | None = None
    ending_equity_yuan: float | None = None
    ending_equity_return_pct: float | None = None
    positive: bool | None = None


class PlateauSummary(ApiModel):
    k_count: int
    bar_count: int
    trading_days: int
    in_sample_days: int
    oos_days: int
    total_days: int
    mean_atr_pct: float
    friction_pct: float
    k_min_safe: float
    max_positions: int
    grid_capital: float
    anchor_policy: str
    band_lower: float
    band_upper: float
    band_source: str
    min_loops: int
    shares_per_grid: int
    penetration_abs: float
    slippage_pct: float
    price_limit_pct: float
    stop_loss_pct: float
    restart_cooldown_days: int
    open_loss_penalty: float
    holdout_enabled: bool
    holdout_reason: str | None = None
    incomplete_days: int
    missing_5m_days: int
    forbidden_k_count: int
    all_forbidden: bool
    island_count: int
    plateau_found: bool
    positive_plateau: bool
    raw_best_k: float
    raw_best_net_return_pct: float
    best_inside_forbidden: bool
    plateau_at_safe_boundary: bool
    plateau_at_right_edge: bool
    live_unavailable_reason: str | None = None
    sample_note: str


class PlateauContext(ApiModel):
    code: str
    name: str = ""
    data_start: str
    data_end: str
    latest_daily_day: str
    latest_price: float
    latest_atr: float
    latest_atr_pct: float
    capital: float
    shares_per_grid: int
    penetration_abs: float
    max_positions: int
    grid_capital: float
    fee: float
    min_fee: float
    spread_pct: float
    slippage_pct: float
    friction_pct: float
    mean_atr_pct: float
    k_min_safe: float
    mode: str
    anchor_policy: str
    price_limit_pct: float
    stop_loss_pct: float
    restart_cooldown_days: int
    bar_count: int
    daily_count: int


class PlateauPolicyComparison(ApiModel):
    anchor_policy: str
    status: str
    error: str | None = None
    k_left: float | None = None
    k_right: float | None = None
    k_star: float | None = None
    profitable: bool | None = None
    in_sample_net_return_pct: float | None = None
    in_sample_capital_return_pct: float | None = None
    holdout_net_return_pct: float | None = None
    holdout_positive: bool | None = None
    live_d_exec_pct: float | None = None
    stop_count: int | None = None
    restart_count: int | None = None
    plateau_at_right_edge: bool | None = None
    plateau_at_safe_boundary: bool | None = None
    note: str | None = None


class PlateauData(ApiModel):
    context: PlateauContext
    k_values: list[float]
    curve: list[PlateauPoint]
    islands: list[PlateauIsland]
    plateau: PlateauBand | None = None
    prior_validation: PlateauPriorValidation
    holdout: PlateauHoldout
    live: PlateauLive | None = None
    summary: PlateauSummary
    policy_comparison: list[PlateauPolicyComparison] = Field(default_factory=list)
    config: dict
    data_snapshot: dict


class PlateauResponse(ApiModel):
    ok: bool = True
    schema_version: int = SCHEMA_VERSION
    data: PlateauData
