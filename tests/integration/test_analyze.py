from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app.app)


def patch_market(monkeypatch: pytest.MonkeyPatch, payload: dict) -> None:
    monkeypatch.setattr(app, "fetch_quote", lambda prefix, digits: payload["quote"])
    monkeypatch.setattr(
        app,
        "fetch_kline",
        lambda prefix, digits, days=250: payload["klines"],
    )


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
    return body["data"]


def test_analyze_002541_snapshot(
    client: TestClient,
    fixture_002541: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_market(monkeypatch, fixture_002541)
    data = get_analysis(client, "002541")

    assert data["version"] == "2.1"
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


def test_analyze_600000_snapshot(
    client: TestClient,
    fixture_600000: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_market(monkeypatch, fixture_600000)
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


def test_root_serves_html(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "A股网格交易参数分析器" in response.text
    assert "no-store" in response.headers["cache-control"]


def test_invalid_code_returns_400(client: TestClient) -> None:
    response = client.get("/api/analyze", params={"code": "abc"})
    assert response.status_code == 400
