from __future__ import annotations

import statistics
from dataclasses import asdict, dataclass, field
from itertools import product
from typing import Iterable

from fastapi import HTTPException

from grid_analyzer.backtest.calibration import rolling_windows
from grid_analyzer.backtest.engine import run_backtest
from grid_analyzer.grid.designer import build_grids


@dataclass(frozen=True)
class SweepParams:
    gap_scale: float = 1.0
    stop_loss: float = 5.0
    init_position: float = 0.0


@dataclass(frozen=True)
class FoldResult:
    calib_start: str
    calib_end: str
    test_start: str
    test_end: str
    return_pct: float
    max_drawdown_pct: float
    rounds: int
    buy_count: int
    total_fees: float
    stop_triggered: bool
    valid: bool


@dataclass(frozen=True)
class SweepResult:
    params: SweepParams
    folds: list[FoldResult] = field(default_factory=list)
    mean_return_pct: float = 0.0
    stdev_return_pct: float = 0.0
    worst_return_pct: float = 0.0
    compounded_return_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    positive_folds: int = 0
    stop_count: int = 0
    plateau_score: float = 0.0

    def to_record(self) -> dict:
        record = asdict(self.params)
        record.update(
            {
                "mean_return_pct": self.mean_return_pct,
                "stdev_return_pct": self.stdev_return_pct,
                "worst_return_pct": self.worst_return_pct,
                "compounded_return_pct": self.compounded_return_pct,
                "max_drawdown_pct": self.max_drawdown_pct,
                "positive_folds": self.positive_folds,
                "stop_count": self.stop_count,
                "plateau_score": self.plateau_score,
                "fold_count": len(self.folds),
            }
        )
        return record


def _aggregate(params: SweepParams, folds: list[FoldResult]) -> SweepResult:
    valid = [f for f in folds if f.valid]
    returns = [f.return_pct for f in valid]
    mean_return = sum(returns) / len(returns) if returns else 0.0
    stdev = statistics.stdev(returns) if len(returns) > 1 else 0.0
    worst = min(returns) if returns else 0.0
    compounded = 1.0
    for ret in returns:
        compounded *= 1.0 + ret / 100.0
    compounded_pct = (compounded - 1.0) * 100.0 if returns else 0.0
    max_dd = max((f.max_drawdown_pct for f in valid), default=0.0)
    positive = sum(1 for ret in returns if ret > 0)
    stop_count = sum(1 for f in valid if f.stop_triggered)
    plateau_score = mean_return - stdev
    return SweepResult(
        params=params,
        folds=folds,
        mean_return_pct=mean_return,
        stdev_return_pct=stdev,
        worst_return_pct=worst,
        compounded_return_pct=compounded_pct,
        max_drawdown_pct=max_dd,
        positive_folds=positive,
        stop_count=stop_count,
        plateau_score=plateau_score,
    )


def run_walk_forward(
    all_klines: list[dict],
    params: SweepParams,
    *,
    capital: float = 100_000,
    fee: float = 0.025,
    min_fee: float = 5.0,
    main_ratio: float = 1.0,
    spread_pct: float = 0.05,
    calib_days: int = 250,
    test_days: int = 60,
    step: int = 60,
    single: bool = True,
) -> SweepResult:
    """Run one parameter set across rolling calibration/test windows."""
    windows = rolling_windows(len(all_klines), calib_days, test_days, step)
    folds: list[FoldResult] = []

    for window in windows:
        calib = all_klines[window.calib_start:window.calib_end]
        test = all_klines[window.test_start:window.test_end]
        calib_start = calib[0]["date"] if calib else ""
        calib_end = calib[-1]["date"] if calib else ""
        test_start = test[0]["date"] if test else ""
        test_end = test[-1]["date"] if test else ""

        try:
            main_grid, _, _, _ = build_grids(
                calib,
                calib[-1]["close"],
                capital,
                single,
                main_ratio,
                spread_pct,
                fee,
                min_fee,
                history_closes=[k["close"] for k in calib],
                gap_scale=params.gap_scale,
            )
        except (HTTPException, IndexError, ValueError):
            folds.append(
                FoldResult(
                    calib_start=calib_start,
                    calib_end=calib_end,
                    test_start=test_start,
                    test_end=test_end,
                    return_pct=0.0,
                    max_drawdown_pct=0.0,
                    rounds=0,
                    buy_count=0,
                    total_fees=0.0,
                    stop_triggered=False,
                    valid=False,
                )
            )
            continue

        if main_grid["shares_per_grid"] <= 0:
            valid = False
            bt = None
        else:
            valid = True
            bt = run_backtest(
                test,
                main_grid,
                fee,
                min_fee,
                params.init_position,
                params.stop_loss,
            )

        folds.append(
            FoldResult(
                calib_start=calib_start,
                calib_end=calib_end,
                test_start=test_start,
                test_end=test_end,
                return_pct=bt["return_pct"] if bt else 0.0,
                max_drawdown_pct=bt["max_drawdown_pct"] if bt else 0.0,
                rounds=bt["rounds"] if bt else 0,
                buy_count=bt["buy_count"] if bt else 0,
                total_fees=bt["total_fees"] if bt else 0.0,
                stop_triggered=bt["stop_triggered"] if bt else False,
                valid=valid,
            )
        )

    return _aggregate(params, folds)


def run_parameter_sweep(
    all_klines: list[dict],
    gap_scales: Iterable[float],
    stop_losses: Iterable[float],
    init_positions: Iterable[float],
    **walk_forward_kwargs,
) -> list[SweepResult]:
    """Run a cartesian parameter sweep and sort by robust plateau score."""
    results: list[SweepResult] = []
    for gap_scale, stop_loss, init_position in product(
        gap_scales, stop_losses, init_positions
    ):
        params = SweepParams(
            gap_scale=gap_scale,
            stop_loss=stop_loss,
            init_position=init_position,
        )
        results.append(run_walk_forward(all_klines, params, **walk_forward_kwargs))
    return sorted(results, key=lambda item: item.plateau_score, reverse=True)
