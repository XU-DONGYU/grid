from __future__ import annotations

import pytest
from fastapi import HTTPException

from grid_analyzer import cache as cache_module
from grid_analyzer.data import tencent


class FakeResponse:
    def __init__(self, text: str = "", data: dict | None = None) -> None:
        self.text = text
        self.encoding = ""
        self._data = data or {}

    def json(self) -> dict:
        return self._data


def quote_text(total_mv: str = "153.87", float_mv: str = "140.0") -> str:
    parts = [""] * 60
    parts[1] = "鸿路钢构"
    parts[2] = "002541"
    parts[3] = "20.3"
    parts[4] = "20.15"
    parts[31] = "0.15"
    parts[32] = "0.74"
    parts[33] = "20.9"
    parts[34] = "19.89"
    parts[37] = "23739"
    parts[38] = "2.05"
    parts[39] = "19.69"
    parts[43] = "5.01"
    parts[44] = float_mv
    parts[45] = total_mv
    for i in range(5):
        parts[9 + i * 2] = str(20.28 - i * 0.01)
        parts[10 + i * 2] = str(1000 + i)
        parts[19 + i * 2] = str(20.31 + i * 0.01)
        parts[20 + i * 2] = str(900 + i)
    return f'v_sz002541="{"~".join(parts)}";'


@pytest.fixture(autouse=True)
def clear_market_cache() -> None:
    cache_module.market_cache.clear()
    yield
    cache_module.market_cache.clear()


def test_parse_code() -> None:
    assert tencent.parse_code("002541") == ("sz", "002541")
    assert tencent.parse_code("sh600000") == ("sh", "600000")
    assert tencent.parse_code("430047") == ("bj", "430047")
    with pytest.raises(HTTPException):
        tencent.parse_code("abc")


def test_fetch_quote_parses_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tencent.requests, "get", lambda url, timeout: FakeResponse(quote_text()))
    quote = tencent.fetch_quote("sz", "002541")
    assert quote["name"] == "鸿路钢构"
    assert quote["price"] == pytest.approx(20.3)
    assert quote["total_mv"] == pytest.approx(153.87)
    assert quote["float_mv"] == pytest.approx(140.0)
    assert len(quote["bid"]) == 5
    assert len(quote["ask"]) == 5


def test_fetch_quote_falls_back_to_float_mv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        tencent.requests,
        "get",
        lambda url, timeout: FakeResponse(quote_text(total_mv="", float_mv="140.0")),
    )
    quote = tencent.fetch_quote("sz", "002541")
    assert quote["total_mv"] == pytest.approx(140.0)


def test_fetch_kline_parses_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "data": {
            "sz002541": {
                "qfqday": [
                    ["2025-01-01", "20", "21", "22", "19", "1000"],
                    ["2025-01-02", "21", "22", "23", "20", "1200"],
                ]
            }
        }
    }
    monkeypatch.setattr(tencent.requests, "get", lambda url, timeout: FakeResponse(data=payload))
    rows = tencent.fetch_kline("sz", "002541", 2)
    assert len(rows) == 2
    assert rows[0]["date"] == "2025-01-01"
    assert rows[1]["close"] == 22


def test_fetch_quote_uses_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"count": 0}

    def fake_get(url: str, timeout: float) -> FakeResponse:
        calls["count"] += 1
        return FakeResponse(quote_text())

    monkeypatch.setattr(tencent.requests, "get", fake_get)
    first = tencent.fetch_quote("sz", "002541")
    second = tencent.fetch_quote("sz", "002541")
    assert first == second
    assert calls["count"] == 1
