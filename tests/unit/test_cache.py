from __future__ import annotations

from grid_analyzer.cache import TTLCache, cached


def test_cache_round_trip_and_expiry() -> None:
    cache = TTLCache()
    cache.set("a", {"value": 1}, ttl=60)
    assert cache.get("a") == {"value": 1}
    cache.set("expired", 1, ttl=0)
    assert cache.get("expired") is None
    cache.clear()
    assert cache.get("a") is None


def test_cached_loader_called_once() -> None:
    from grid_analyzer import cache as cache_module

    cache_module.market_cache.clear()
    calls = {"count": 0}

    def loader() -> dict:
        calls["count"] += 1
        return {"value": 2}

    first = cached("test-key", 60, loader)
    second = cached("test-key", 60, loader)
    assert first == second == {"value": 2}
    assert calls["count"] == 1
    cache_module.market_cache.clear()
