from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

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
