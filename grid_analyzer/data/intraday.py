from __future__ import annotations

import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from grid_analyzer.config import get_settings
from grid_analyzer.data.tencent import parse_code


class NoDataError(RuntimeError):
    """Raised when no intraday or daily bars are available."""


class IntradayDataProvider(Protocol):
    def get_bars(
        self, code: str, frequency: str, start_date: str, end_date: str
    ) -> list[dict]: ...


def normalize_baostock_code(code: str) -> str:
    raw = (code or "").strip().lower().replace(".", "")
    prefix, digits = parse_code(raw)
    if prefix not in {"sh", "sz"}:
        raise ValueError(f"BaoStock 当前只支持沪深股票，收到：{code}")
    return f"{prefix}.{digits}"


def _normalize_timestamp(raw: str, trading_day: str) -> str:
    value = (raw or "").strip()
    if len(value) >= 14 and value[:14].isdigit():
        parsed = datetime.strptime(value[:14], "%Y%m%d%H%M%S")
        return parsed.strftime("%Y-%m-%d %H:%M:%S")
    if len(value) >= 10 and value[4] == "-" and value[7] == "-":
        return value[:19]
    return f"{trading_day} 00:00:00"


class _BaoStockSession:
    def __init__(self) -> None:
        self._bs: Any = None

    def __enter__(self) -> Any:
        try:
            import baostock as bs
        except ImportError as exc:
            raise RuntimeError(
                "baostock 未安装，请先安装项目依赖后再使用 5 分钟数据"
            ) from exc
        result = bs.login()
        if result.error_code != "0":
            raise RuntimeError(f"BaoStock 登录失败：{result.error_msg}")
        self._bs = bs
        return bs

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self._bs is not None:
            self._bs.logout()


_LOGIN_LOCK = threading.Lock()


class BaoStockProvider:
    """BaoStock implementation for daily and 5-minute bars."""

    def get_bars(
        self, code: str, frequency: str, start_date: str, end_date: str
    ) -> list[dict]:
        if frequency not in {"d", "5"}:
            raise ValueError(f"unsupported frequency: {frequency}")
        fields = (
            "date,code,open,high,low,close,volume,amount,adjustflag"
            if frequency == "d"
            else "date,time,code,open,high,low,close,volume,amount,adjustflag"
        )
        adjustflag = get_settings().baostock_adjustflag
        with _LOGIN_LOCK, _BaoStockSession() as bs:
            result = bs.query_history_k_data_plus(
                code,
                fields,
                start_date=start_date,
                end_date=end_date,
                frequency=frequency,
                adjustflag=adjustflag,
            )
            if result.error_code != "0":
                raise RuntimeError(f"BaoStock 查询失败：{result.error_msg}")
            rows: list[dict] = []
            while result.next():
                rows.append(dict(zip(result.fields, result.get_row_data())))
        return [bar for bar in (self._parse_row(row, frequency) for row in rows) if bar]

    def _parse_row(self, row: dict[str, str], frequency: str) -> dict | None:
        trading_day = (row.get("date") or "").strip()
        close = _to_float(row.get("close"))
        if not trading_day or close <= 0:
            return None
        if frequency == "d":
            timestamp = trading_day
        else:
            raw_time = (row.get("time") or "").strip()
            if not raw_time:
                return None
            timestamp = _normalize_timestamp(raw_time, trading_day)
        return {
            "timestamp": timestamp,
            "trading_day": trading_day,
            "open": _to_float(row.get("open")),
            "high": _to_float(row.get("high")),
            "low": _to_float(row.get("low")),
            "close": close,
            "volume": _to_float(row.get("volume")),
            "amount": _to_float(row.get("amount")),
        }


def _to_float(value: str | None) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


class SQLiteIntradayCache:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS bars (
                    code TEXT NOT NULL,
                    frequency TEXT NOT NULL,
                    adjustflag TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    trading_day TEXT NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    volume REAL NOT NULL,
                    amount REAL NOT NULL,
                    PRIMARY KEY (code, frequency, adjustflag, timestamp)
                );
                CREATE INDEX IF NOT EXISTS idx_bars_day
                    ON bars(code, frequency, adjustflag, trading_day);
                CREATE TABLE IF NOT EXISTS coverage (
                    code TEXT NOT NULL,
                    frequency TEXT NOT NULL,
                    adjustflag TEXT NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (code, frequency, adjustflag)
                );
                """
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def coverage(self, code: str, frequency: str, adjustflag: str) -> tuple[str, str] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT start_date, end_date FROM coverage "
                "WHERE code=? AND frequency=? AND adjustflag=?",
                (code, frequency, adjustflag),
            ).fetchone()
        return (row[0], row[1]) if row else None

    def upsert(self, code: str, frequency: str, adjustflag: str, rows: list[dict]) -> None:
        if not rows:
            return
        with self._lock, self._connect() as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO bars
                (code, frequency, adjustflag, timestamp, trading_day,
                 open, high, low, close, volume, amount)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        code,
                        frequency,
                        adjustflag,
                        row["timestamp"],
                        row["trading_day"],
                        row["open"],
                        row["high"],
                        row["low"],
                        row["close"],
                        row["volume"],
                        row["amount"],
                    )
                    for row in rows
                ],
            )
            days = sorted({row["trading_day"] for row in rows})
            old = conn.execute(
                "SELECT start_date, end_date FROM coverage "
                "WHERE code=? AND frequency=? AND adjustflag=?",
                (code, frequency, adjustflag),
            ).fetchone()
            start = min(days[0], old[0]) if old else days[0]
            end = max(days[-1], old[1]) if old else days[-1]
            conn.execute(
                """
                INSERT OR REPLACE INTO coverage
                (code, frequency, adjustflag, start_date, end_date, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    code,
                    frequency,
                    adjustflag,
                    start,
                    end,
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )

    def query(
        self, code: str, frequency: str, adjustflag: str, start_date: str, end_date: str
    ) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT timestamp, trading_day, open, high, low, close, volume, amount
                FROM bars
                WHERE code=? AND frequency=? AND adjustflag=?
                  AND trading_day BETWEEN ? AND ?
                ORDER BY timestamp
                """,
                (code, frequency, adjustflag, start_date, end_date),
            ).fetchall()
        return [
            {
                "timestamp": row[0],
                "trading_day": row[1],
                "open": row[2],
                "high": row[3],
                "low": row[4],
                "close": row[5],
                "volume": row[6],
                "amount": row[7],
            }
            for row in rows
        ]

    def clear(self) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM bars")
            conn.execute("DELETE FROM coverage")


class IntradayRepository:
    """Fetch from provider and persist into a local SQLite cache."""

    def __init__(
        self,
        provider: IntradayDataProvider | None = None,
        cache: SQLiteIntradayCache | None = None,
        adjustflag: str | None = None,
    ) -> None:
        settings = get_settings()
        self.provider = provider or BaoStockProvider()
        self.cache = cache or SQLiteIntradayCache(settings.intraday_cache_path)
        self.adjustflag = adjustflag or settings.baostock_adjustflag

    def get_bars(
        self, code: str, frequency: str, start_date: str, end_date: str
    ) -> list[dict]:
        if frequency not in {"d", "5"}:
            raise ValueError(f"unsupported frequency: {frequency}")
        norm_code = normalize_baostock_code(code)
        coverage = self.cache.coverage(norm_code, frequency, self.adjustflag)
        ranges: list[tuple[str, str]] = []
        if coverage is None:
            ranges.append((start_date, end_date))
        else:
            start, end = coverage
            if start_date < start:
                ranges.append((start_date, start))
            if end_date > end:
                ranges.append((end, end_date))
        for fetch_start, fetch_end in ranges:
            rows = self.provider.get_bars(norm_code, frequency, fetch_start, fetch_end)
            self.cache.upsert(norm_code, frequency, self.adjustflag, rows)
        bars = self.cache.query(
            norm_code, frequency, self.adjustflag, start_date, end_date
        )
        if not bars:
            raise NoDataError(f"{code} 在 {start_date} ~ {end_date} 没有可用数据")
        return bars
