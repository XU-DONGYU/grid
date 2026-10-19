from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from grid_analyzer.data.intraday import BaoStockProvider


class FakeResult:
    error_code = "0"
    error_msg = ""

    def __init__(self, fields: list[str], rows: list[list[str]]) -> None:
        self.fields = fields
        self.rows = rows
        self.index = -1

    def next(self) -> bool:
        self.index += 1
        return self.index < len(self.rows)

    def get_row_data(self) -> list[str]:
        return self.rows[self.index]


class FakeBaoStock:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def login(self) -> SimpleNamespace:
        return SimpleNamespace(error_code="0", error_msg="")

    def logout(self) -> None:
        return None

    def query_history_k_data_plus(self, code, fields, start_date, end_date, frequency, adjustflag):
        self.calls.append((code, fields, start_date, end_date, frequency, adjustflag))
        if frequency == "5":
            rows = [["2026-10-19", "20261019093500000", code, "10", "10.2", "9.8", "10.1", "1000", "10000", "2"]]
            return FakeResult(
                ["date", "time", "code", "open", "high", "low", "close", "volume", "amount", "adjustflag"],
                rows,
            )
        rows = [["2026-10-19", code, "10", "10.2", "9.8", "10.1", "1000", "10000", "2"]]
        return FakeResult(
            ["date", "code", "open", "high", "low", "close", "volume", "amount", "adjustflag"],
            rows,
        )


def test_baostock_provider_parses_intraday(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeBaoStock()
    monkeypatch.setitem(sys.modules, "baostock", fake)
    provider = BaoStockProvider()
    bars = provider.get_bars("sz.002541", "5", "2026-10-01", "2026-10-19")
    assert len(bars) == 1
    assert bars[0]["trading_day"] == "2026-10-19"
    assert bars[0]["timestamp"] == "2026-10-19 09:35:00"
    assert bars[0]["close"] == pytest.approx(10.1)
    assert fake.calls[0][4] == "5"


def test_baostock_provider_parses_daily(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeBaoStock()
    monkeypatch.setitem(sys.modules, "baostock", fake)
    provider = BaoStockProvider()
    bars = provider.get_bars("sz.002541", "d", "2026-10-01", "2026-10-19")
    assert len(bars) == 1
    assert bars[0]["timestamp"] == "2026-10-19"
    assert bars[0]["trading_day"] == "2026-10-19"
    assert fake.calls[0][4] == "d"
