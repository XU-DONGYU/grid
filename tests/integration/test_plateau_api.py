from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Iterator

import pytest
from fastapi.testclient import TestClient

from grid_analyzer.api.routes import get_intraday_repository, get_market_data_provider
from grid_analyzer.api.schemas import PlateauResponse
from grid_analyzer.main import app


class FixtureProvider:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def get_quote(self, code: str) -> dict:
        return self.payload["quote"]

    def get_klines(self, code: str, days: int = 250) -> list[dict]:
        return self.payload["klines"]


class FakeIntradayRepository:
    def __init__(self, bars_5m: list[dict], daily_bars: list[dict]) -> None:
        self.bars_5m = bars_5m
        self.daily_bars = daily_bars

    def get_bars(self, code: str, frequency: str, start_date: str, end_date: str) -> list[dict]:
        return self.bars_5m if frequency == "5" else self.daily_bars


def trading_days(count: int) -> list[str]:
    days = []
    current = date(2025, 1, 2)
    while len(days) < count:
        if current.weekday() < 5:
            days.append(current.isoformat())
        current += timedelta(days=1)
    return days


def intraday_times() -> list[str]:
    times = []
    current = datetime(2025, 1, 2, 9, 35)
    while current <= datetime(2025, 1, 2, 11, 30):
        times.append(current.strftime("%H:%M"))
        current += timedelta(minutes=5)
    current = datetime(2025, 1, 2, 13, 5)
    while current <= datetime(2025, 1, 2, 15, 0):
        times.append(current.strftime("%H:%M"))
        current += timedelta(minutes=5)
    return times


def make_bars(days: list[str]) -> tuple[list[dict], list[dict]]:
    times = intraday_times()
    daily = []
    bars_5m = []
    for day in days:
        daily.append(
            {
                "trading_day": day,
                "open": 100.0,
                "high": 102.0,
                "low": 98.0,
                "close": 100.0,
            }
        )
        for time in times:
            bars_5m.append(
                {
                    "timestamp": f"{day} {time}",
                    "trading_day": day,
                    "open": 100.0,
                    "high": 103.0,
                    "low": 97.0,
                    "close": 100.0,
                }
            )
    return bars_5m, daily


@pytest.fixture
def plateau_client(fixture_002541: dict) -> Iterator[TestClient]:
    days = trading_days(50)
    bars_5m, daily = make_bars(days)
    app.dependency_overrides[get_market_data_provider] = lambda: FixtureProvider(fixture_002541)
    app.dependency_overrides[get_intraday_repository] = lambda: FakeIntradayRepository(bars_5m, daily)
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_plateau_contract(plateau_client: TestClient) -> None:
    response = plateau_client.post(
        "/api/plateau",
        json={
            "code": "002541",
            "capital": 1_000_000,
            "fee": 0,
            "min_fee": 0,
            "spread_pct": 0,
            "k_start": 0.2,
            "k_end": 1.0,
            "k_step": 0.1,
            "plateau_window": 3,
            "history_days": 60,
            "mode": "dynamic",
            "compare_anchor_policies": True,
        },
    )
    assert response.status_code == 200
    contract = PlateauResponse.model_validate(response.json())
    assert contract.schema_version == 2
    assert contract.data.context.name == "鸿路钢构"
    assert len(contract.data.k_values) == 9
    assert len(contract.data.curve) == 9
    assert contract.data.plateau is not None
    assert contract.data.live is not None
    assert contract.data.live.k_star == contract.data.plateau.k_star
    assert contract.data.prior_validation.prior_anchor == 0.70
    assert contract.data.summary.trading_days == 35
    assert contract.data.summary.in_sample_days == 35
    assert contract.data.summary.oos_days == 15
    assert contract.data.summary.total_days == 50
    assert contract.data.summary.max_positions == 8
    assert contract.data.summary.shares_per_grid == 100
    assert contract.data.context.max_positions == 8
    assert contract.data.context.shares_per_grid == 100
    assert contract.data.context.capital == 1_000_000
    assert contract.data.context.anchor_policy == "fixed"
    assert contract.data.context.band_lower > 0
    assert contract.data.context.band_upper > contract.data.context.band_lower
    assert contract.data.curve[0].max_positions == 8
    assert contract.data.plateau.k_star_max_positions_used >= 1
    assert contract.data.holdout.enabled is True
    assert contract.data.holdout.k_star == contract.data.plateau.k_star
    assert contract.data.holdout.net_return_pct is not None
    assert len(contract.data.policy_comparison) == 4
    assert {row.anchor_policy for row in contract.data.policy_comparison} == {
        "daily_roll", "fixed_band", "fixed", "periodic"
    }
    assert contract.data.data_snapshot["source"] == "BaoStock"


def test_plateau_rejects_invalid_k_range(plateau_client: TestClient) -> None:
    response = plateau_client.post(
        "/api/plateau",
        json={"code": "002541", "k_start": 2.0, "k_end": 1.0},
    )
    assert response.status_code == 422
