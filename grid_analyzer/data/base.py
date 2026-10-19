from __future__ import annotations

from typing import Protocol


class MarketDataProvider(Protocol):
    def get_quote(self, code: str) -> dict:
        ...

    def get_klines(self, code: str, days: int = 250) -> list[dict]:
        ...
