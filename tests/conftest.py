from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import pytest

import app

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def load_fixture(code: str) -> dict[str, Any]:
    path = FIXTURE_DIR / f"{code}.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def fixture_002541() -> dict[str, Any]:
    return load_fixture("002541")


@pytest.fixture(scope="session")
def fixture_600000() -> dict[str, Any]:
    return load_fixture("600000")


@pytest.fixture
def offline_analyze(monkeypatch: pytest.MonkeyPatch) -> Callable[..., dict[str, Any]]:
    def run(code: str, **overrides: Any) -> dict[str, Any]:
        payload = load_fixture(code)
        monkeypatch.setattr(app, "fetch_quote", lambda prefix, digits: payload["quote"])
        monkeypatch.setattr(
            app,
            "fetch_kline",
            lambda prefix, digits, days=250: payload["klines"],
        )
        params: dict[str, Any] = {
            "capital": 100_000,
            "fee": 0.025,
            "min_fee": 5.0,
            "main_ratio": 0.7,
            "init_position": 0.0,
            "stop_loss": 5.0,
        }
        params.update(overrides)
        return app.analyze(code=code, **params)

    return run
