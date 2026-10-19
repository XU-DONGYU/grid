from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from typing import Any, Iterator

import pytest
from fastapi.testclient import TestClient

from grid_analyzer.api.routes import get_intraday_repository, get_market_data_provider
from grid_analyzer.api.schemas import IntradayHeatmapResponse
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
    for i, day in enumerate(days):
        close = 100 + 5 * math.sin(i / 5)
        daily.append(
            {
                "timestamp": day,
                "trading_day": day,
                "open": close - 0.5,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close,
                "volume": 100000,
                "amount": 10000000,
            }
        )
        for j, time in enumerate(times):
            price = close + 0.8 * math.sin(j / 3 + i)
            bars_5m.append(
                {
                    "timestamp": f"{day} {time}",
                    "trading_day": day,
                    "open": price,
                    "high": price + 0.2,
                    "low": price - 0.2,
                    "close": price,
                    "volume": 1000,
                    "amount": 10000,
                }
            )
    return bars_5m, daily


@pytest.fixture
def intraday_client(fixture_002541: dict) -> Iterator[TestClient]:
    days = trading_days(60)
    bars_5m, daily = make_bars(days)
    app.dependency_overrides[get_market_data_provider] = lambda: FixtureProvider(fixture_002541)
    app.dependency_overrides[get_intraday_repository] = lambda: FakeIntradayRepository(bars_5m, daily)
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_intraday_heatmap_contract(intraday_client: TestClient) -> None:
    response = intraday_client.post(
        "/api/intraday-heatmap",
        json={
            "code": "002541",
            "capital": 1_000_000,
            "fee": 0.025,
            "min_fee": 5,
            "init_position": 0,
            "stop_losses": [0],
            "window_days": 10,
            "in_sample_ratio": 0.7,
            "final_blind_days": 3,
            "min_oos_days": 0,
            "history_days": 60,
            "primary_metric": "realized_annual_pct",
        },
    )
    assert response.status_code == 200
    body = response.json()
    contract = IntradayHeatmapResponse.model_validate(body)
    assert contract.schema_version == 2
    assert contract.data.context.name == "鸿路钢构"
    assert len(contract.data.k_values) == 21
    assert len(contract.data.cells) == 21
    assert contract.data.folds
    assert contract.data.locked.blind is not None
    assert contract.data.summary.oos_coverage_days > 0


def test_intraday_heatmap_rejects_empty_stop_losses(intraday_client: TestClient) -> None:
    response = intraday_client.post(
        "/api/intraday-heatmap",
        json={"code": "002541", "stop_losses": []},
    )
    assert response.status_code == 422


def test_intraday_heatmap_job_contract(intraday_client: TestClient) -> None:
    import time

    response = intraday_client.post(
        "/api/intraday-heatmap/jobs",
        json={
            "code": "002541",
            "capital": 1_000_000,
            "stop_losses": [0],
            "window_days": 10,
            "in_sample_ratio": 0.7,
            "final_blind_days": 3,
            "min_oos_days": 0,
            "history_days": 60,
        },
    )
    assert response.status_code == 200
    job = response.json()
    assert job["schema_version"] == 2
    job_id = job["data"]["job_id"]
    assert job_id

    deadline = time.time() + 30
    status = None
    while time.time() < deadline:
        poll = intraday_client.get(f"/api/intraday-heatmap/jobs/{job_id}")
        assert poll.status_code == 200
        status = poll.json()["data"]
        if status["status"] in {"completed", "failed"}:
            break
        time.sleep(0.1)
    assert status is not None
    assert status["status"] == "completed", status
    assert status["result"]["k_values"]
