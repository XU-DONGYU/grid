from __future__ import annotations

import pytest

from grid_analyzer.backtest.calibration import rolling_windows
from grid_analyzer.services.research import (
    SweepParams,
    run_parameter_sweep,
    run_walk_forward,
)


def test_rolling_windows_do_not_overlap() -> None:
    windows = rolling_windows(251, calib_days=120, test_days=60, step=60)
    assert len(windows) == 2
    for window in windows:
        assert window.calib_end == window.test_start
        assert window.test_start < window.test_end
        assert window.calib_start < window.calib_end


def test_walk_forward_returns_metrics(fixture_002541: dict) -> None:
    klines = fixture_002541["klines"]
    result = run_walk_forward(
        klines,
        SweepParams(gap_scale=1.0, stop_loss=5.0, init_position=0.0),
        capital=100_000,
        fee=0.025,
        min_fee=5.0,
        main_ratio=1.0,
        spread_pct=0.05,
        calib_days=120,
        test_days=60,
        step=60,
        single=True,
    )
    assert len(result.folds) == 2
    assert all(fold.valid for fold in result.folds)
    assert result.max_drawdown_pct >= 0
    assert result.mean_return_pct == pytest.approx(
        sum(fold.return_pct for fold in result.folds) / 2
    )


def test_parameter_sweep_is_sorted(fixture_002541: dict) -> None:
    results = run_parameter_sweep(
        fixture_002541["klines"],
        gap_scales=[0.9, 1.0],
        stop_losses=[0.0, 5.0],
        init_positions=[0.0],
        capital=100_000,
        fee=0.025,
        min_fee=5.0,
        main_ratio=1.0,
        spread_pct=0.05,
        calib_days=120,
        test_days=60,
        step=60,
        single=True,
    )
    assert len(results) == 4
    scores = [result.plateau_score for result in results]
    assert scores == sorted(scores, reverse=True)


def test_insufficient_history_returns_empty_folds(fixture_002541: dict) -> None:
    result = run_walk_forward(
        fixture_002541["klines"][:100],
        SweepParams(),
        calib_days=120,
        test_days=60,
        step=60,
    )
    assert result.folds == []
    assert result.mean_return_pct == 0
