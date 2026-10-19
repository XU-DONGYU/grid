from __future__ import annotations

from pathlib import Path

import pytest

from grid_analyzer.data.intraday import (
    IntradayRepository,
    NoDataError,
    SQLiteIntradayCache,
    _normalize_timestamp,
    normalize_baostock_code,
)


class FakeProvider:
    def __init__(self, bars: list[dict]) -> None:
        self.bars = bars
        self.calls: list[tuple[str, str, str, str]] = []

    def get_bars(self, code: str, frequency: str, start_date: str, end_date: str) -> list[dict]:
        self.calls.append((code, frequency, start_date, end_date))
        return [
            bar
            for bar in self.bars
            if frequency == "5" and start_date <= bar["trading_day"] <= end_date
        ]


def make_bar(day: str, minute: str, close: float) -> dict:
    return {
        "timestamp": f"{day} {minute}:00",
        "trading_day": day,
        "open": close,
        "high": close + 0.1,
        "low": close - 0.1,
        "close": close,
        "volume": 1000,
        "amount": 10000,
    }


def test_normalize_code_and_timestamp() -> None:
    assert normalize_baostock_code("002541") == "sz.002541"
    assert normalize_baostock_code("sh.600000") == "sh.600000"
    assert _normalize_timestamp("20261019093500000", "2026-10-19") == "2026-10-19 09:35:00"
    assert _normalize_timestamp("2026-10-19T09:35:00", "2026-10-19") == "2026-10-19T09:35:00"


def test_repository_caches_and_fetches_missing_range(tmp_path: Path) -> None:
    bars = [
        make_bar("2026-01-02", "09:35", 10.0),
        make_bar("2026-01-02", "09:40", 10.1),
        make_bar("2026-01-03", "09:35", 10.2),
    ]
    provider = FakeProvider(bars)
    cache = SQLiteIntradayCache(tmp_path / "cache.db")
    repo = IntradayRepository(provider=provider, cache=cache, adjustflag="2")

    first = repo.get_bars("002541", "5", "2026-01-02", "2026-01-02")
    assert len(first) == 2
    assert len(provider.calls) == 1

    second = repo.get_bars("002541", "5", "2026-01-02", "2026-01-02")
    assert second == first
    assert len(provider.calls) == 1

    third = repo.get_bars("002541", "5", "2026-01-02", "2026-01-03")
    assert len(third) == 3
    assert len(provider.calls) == 2
    assert provider.calls[-1][2:] == ("2026-01-02", "2026-01-03")


def test_repository_raises_when_empty(tmp_path: Path) -> None:
    cache = SQLiteIntradayCache(tmp_path / "cache.db")
    repo = IntradayRepository(provider=FakeProvider([]), cache=cache, adjustflag="2")
    with pytest.raises(NoDataError):
        repo.get_bars("002541", "5", "2026-01-02", "2026-01-03")


def test_hong_kong_prefix_is_rejected() -> None:
    with pytest.raises(ValueError):
        normalize_baostock_code("bj430047")
