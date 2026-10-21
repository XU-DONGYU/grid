from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from grid_analyzer.api.routes import get_market_data_provider
from grid_analyzer.api.schemas import AnalyzeResponse, HeatmapResponse
from grid_analyzer.main import app


class FixtureProvider:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def get_quote(self, code: str) -> dict:
        return self.payload["quote"]

    def get_klines(self, code: str, days: int = 250) -> list[dict]:
        return self.payload["klines"]


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def client_for() -> Iterator[Any]:
    def make(payload: dict[str, Any]) -> TestClient:
        app.dependency_overrides[get_market_data_provider] = lambda: FixtureProvider(payload)
        return TestClient(app)

    yield make
    app.dependency_overrides.clear()


def get_analysis(client: TestClient, code: str) -> dict:
    response = client.get(
        "/api/analyze",
        params={
            "code": code,
            "capital": 100_000,
            "fee": 0.025,
            "min_fee": 5,
            "main_ratio": 0.7,
            "init_position": 0,
            "stop_loss": 5,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["schema_version"] == 2
    contract = AnalyzeResponse.model_validate(body)
    assert contract.schema_version == 2
    assert contract.data.version == "2.5.0"
    return contract.data.model_dump()


def test_analyze_002541_snapshot(client_for: Any, fixture_002541: dict) -> None:
    client = client_for(fixture_002541)
    data = get_analysis(client, "002541")

    assert data["version"] == "2.5.0"
    assert data["quote"]["name"] == "鸿路钢构"
    assert data["quote"]["total_mv"] == pytest.approx(153.87)
    assert data["volatility"]["vol_of_vol_pct"] == pytest.approx(9.325212, abs=1e-5)
    assert data["volatility"]["boll_width_percentile"] == pytest.approx(49.784483, abs=1e-5)
    assert data["volatility"]["squeeze"] is False

    assert len(data["kline_tail"]) == 120
    assert data["main_grid"]["shares_per_grid"] > 0
    assert data["backtest_meta"]["used_calibration"] is True
    assert data["backtest_meta"]["lookahead_free"] is True
    assert data["backtest_meta"]["main_lower"] == pytest.approx(19.391)
    assert data["backtest_meta"]["main_upper"] == pytest.approx(24.472)
    assert data["backtest_meta"]["main_gap_pct"] == pytest.approx(3.465745, abs=1e-5)

    main = data["backtest"]["main"]
    assert main["rounds"] == 4
    assert main["stop_triggered"] is True
    assert main["stop_date"] == "2026-05-13"
    assert main["return_pct"] == pytest.approx(-1.161367, abs=1e-5)
    assert len(main["equity_curve"]) == 120


def test_analyze_600000_snapshot(client_for: Any, fixture_600000: dict) -> None:
    client = client_for(fixture_600000)
    data = get_analysis(client, "600000")

    assert data["quote"]["name"] == "浦发银行"
    assert data["quote"]["total_mv"] == pytest.approx(3257.31)
    assert data["volatility"]["vol_of_vol_pct"] == pytest.approx(3.247843, abs=1e-5)
    assert data["volatility"]["boll_width_percentile"] == pytest.approx(69.827586, abs=1e-5)
    assert data["backtest_meta"]["main_lower"] == pytest.approx(9.19)
    assert data["backtest_meta"]["main_upper"] == pytest.approx(10.633)

    main = data["backtest"]["main"]
    assert main["rounds"] == 2
    assert main["stop_triggered"] is True
    assert main["stop_date"] == "2026-05-07"


def test_health_and_version(client: TestClient) -> None:
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["ok"] is True
    assert health.json()["version"] == "2.5.0"

    version = client.get("/api/version")
    assert version.status_code == 200
    assert version.json() == {"version": "2.5.0", "schema_version": 2}


def test_root_serves_html(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "A股网格交易参数分析器" in response.text
    assert "/static/js/main.js" in response.text
    assert "no-store" in response.headers["cache-control"]


def test_static_assets_are_served(client: TestClient) -> None:
    css = client.get("/static/css/styles.css")
    assert css.status_code == 200
    assert ":root" in css.text

    js = client.get("/static/js/main.js")
    assert js.status_code == 200
    assert "analyzeMarket" in js.text


def test_invalid_code_returns_400(client: TestClient) -> None:
    response = client.get("/api/analyze", params={"code": "abc"})
    assert response.status_code == 400


def test_heatmap_api_contract(client_for: Any, fixture_002541: dict) -> None:
    client = client_for(fixture_002541)
    response = client.get(
        "/api/heatmap",
        params={
            "code": "002541",
            "capital": 100_000,
            "fee": 0.025,
            "min_fee": 5,
            "history_days": 250,
            "calib_days": 120,
            "test_days": 60,
            "step": 60,
            "gap_scales": "0.9,1.0",
            "stop_losses": "0,5",
            "init_positions": "0",
            "metric": "mean_return_pct",
        },
    )
    assert response.status_code == 200
    body = response.json()
    contract = HeatmapResponse.model_validate(body)
    assert contract.schema_version == 2
    assert contract.data.code == "002541"
    assert contract.data.metric == "mean_return_pct"
    assert contract.data.gap_scales == [0.9, 1.0]
    assert contract.data.stop_losses == [0.0, 5.0]
    assert contract.data.init_positions == [0.0]
    assert len(contract.data.cells) == 4
    assert contract.data.sample_count == 4
    assert contract.data.best is not None


def test_heatmap_rejects_unknown_metric(client: TestClient) -> None:
    response = client.get(
        "/api/heatmap",
        params={"code": "002541", "metric": "not-a-metric"},
    )
    assert response.status_code == 422
