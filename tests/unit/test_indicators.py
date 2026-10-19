from __future__ import annotations

import math

import app


def make_bars(closes: list[float], spread: float = 1.0) -> list[dict]:
    return [
        {
            "date": f"d{i}",
            "open": close,
            "close": close,
            "high": close + spread,
            "low": close - spread,
            "volume": 1000,
        }
        for i, close in enumerate(closes)
    ]


def test_compute_axis_uses_available_window() -> None:
    closes = [10, 20, 30, 40, 50]
    axis = app.compute_axis(closes)
    assert axis["median60"] == 30
    assert axis["mean60"] == 30
    assert axis["ma20"] == 30
    assert axis["ma60"] == 30
    assert axis["recommended"] == 30


def test_compute_atr_constant_range() -> None:
    bars = make_bars([10] * 20, spread=1.0)
    assert app.compute_atr(bars, 14) == 2.0


def test_percentile_rank() -> None:
    assert app.percentile_rank([1, 2, 3, 4], 4) == 87.5
    assert app.percentile_rank([], 1) == 50.0


def test_bollinger_constant_price_has_zero_bandwidth() -> None:
    result = app.bollinger([10] * 20)
    assert result["bandwidth_pct"] == 0.0
    assert result["upper"] == 10.0
    assert result["lower"] == 10.0


def test_compute_volatility_contract() -> None:
    closes = [10 + 0.4 * math.sin(i / 3) for i in range(120)]
    bars = make_bars(closes)
    vol = app.compute_volatility(bars, history_closes=closes * 2)
    expected = {
        "sigma_daily_pct",
        "sigma_annual_pct",
        "vol_of_vol_pct",
        "atr",
        "atr_pct",
        "boll_upper",
        "boll_lower",
        "boll_width_pct",
        "boll_width_percentile",
        "squeeze",
        "ttm_squeeze",
        "keltner_upper",
        "keltner_lower",
    }
    assert expected.issubset(vol)
    assert vol["sigma_daily_pct"] > 0
    assert vol["vol_of_vol_pct"] >= 0
    assert 0 <= vol["boll_width_percentile"] <= 100
    assert isinstance(vol["squeeze"], bool)


def test_compute_trend_positive_for_rising_prices() -> None:
    closes = [100 + i for i in range(60)]
    trend20, trend60 = app.compute_trend(make_bars(closes))
    assert trend20 > 0
    assert trend60 > 0


def test_fit_score_penalizes_squeeze() -> None:
    normal = app.fit_score(0, 0, 0.5, 2.0, squeeze=False)
    squeezed = app.fit_score(0, 0, 0.5, 2.0, squeeze=True)
    assert squeezed < normal
    assert squeezed <= 45


def test_liquidity_grade() -> None:
    assert app.liquidity_grade(0.05, 50000)[0] == "好"
    assert app.liquidity_grade(1.0, 50000)[0] == "差"
