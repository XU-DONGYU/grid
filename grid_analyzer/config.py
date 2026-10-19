from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    app_env: str = "development"
    host: str = "127.0.0.1"
    port: int = 8000
    request_timeout: float = 10.0
    quote_cache_ttl: int = 30
    kline_cache_ttl: int = 300
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            app_env=os.getenv("APP_ENV", "development"),
            host=os.getenv("APP_HOST", "127.0.0.1"),
            port=_env_int("APP_PORT", 8000),
            request_timeout=_env_float("REQUEST_TIMEOUT_SECONDS", 10.0),
            quote_cache_ttl=_env_int("QUOTE_CACHE_TTL_SECONDS", 30),
            kline_cache_ttl=_env_int("KLINE_CACHE_TTL_SECONDS", 300),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_env()
