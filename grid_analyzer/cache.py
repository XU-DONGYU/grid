from __future__ import annotations

import copy
import threading
import time
from typing import Any, Callable, TypeVar

T = TypeVar("T")


class TTLCache:
    """Small thread-safe in-memory TTL cache for external market data."""

    def __init__(self) -> None:
        self._data: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        now = time.monotonic()
        with self._lock:
            item = self._data.get(key)
            if item is None:
                return None
            expires_at, value = item
            if expires_at <= now:
                self._data.pop(key, None)
                return None
            return copy.deepcopy(value)

    def set(self, key: str, value: Any, ttl: int) -> None:
        if ttl <= 0:
            return
        with self._lock:
            self._data[key] = (time.monotonic() + ttl, copy.deepcopy(value))

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


market_cache = TTLCache()


def cached(key: str, ttl: int, loader: Callable[[], T]) -> T:
    hit = market_cache.get(key)
    if hit is not None:
        return hit
    value = loader()
    market_cache.set(key, value, ttl)
    return value
