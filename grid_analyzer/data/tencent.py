from __future__ import annotations

import re

import requests
from fastapi import HTTPException

from grid_analyzer.cache import cached
from grid_analyzer.config import get_settings


def parse_code(code: str) -> tuple[str, str]:
    """识别市场前缀与6位代码。"""
    code = (code or "").strip().lower()
    m = re.match(r"^(sh|sz|bj)?(\d{6})$", code)
    if not m:
        raise HTTPException(400, "股票代码格式错误，请输入6位数字或带 sh/sz/bj 前缀，如 600000 / sz000001")
    prefix, digits = m.group(1), m.group(2)
    if not prefix:
        if digits[0] in "659":
            prefix = "sh"
        elif digits[0] in "023":
            prefix = "sz"
        elif digits[0] in "48":
            prefix = "bj"
        else:
            prefix = "sh"
    return prefix, digits


def fetch_quote(prefix: str, code: str) -> dict:
    """腾讯实时行情（带短 TTL 内存缓存）。"""
    ttl = get_settings().quote_cache_ttl
    return cached(f"quote:{prefix}:{code}", ttl, lambda: _fetch_quote(prefix, code))


def _fetch_quote(prefix: str, code: str) -> dict:
    url = f"https://qt.gtimg.cn/q={prefix}{code}"
    resp = requests.get(url, timeout=get_settings().request_timeout)
    resp.encoding = "gbk"
    m = re.search(r'="(.*)"', resp.text)
    if not m or not m.group(1) or len(m.group(1).split("~")) < 50:
        raise HTTPException(404, f"未获取到 {prefix}{code} 的行情，请确认代码是否正确")
    parts = m.group(1).split("~")

    def num(idx: int) -> float:
        try:
            return float(parts[idx] or 0)
        except (ValueError, IndexError):
            return 0.0

    price = num(3)
    if price <= 0:
        raise HTTPException(404, f"未获取到 {prefix}{code} 的有效行情（可能已退市或停牌过久）")
    total_mv = num(45)  # 总市值（亿）
    float_mv = num(44)  # 流通市值（亿）
    if total_mv <= 0:
        total_mv = float_mv
    return {
        "name": parts[1],
        "code": parts[2],
        "price": price,
        "prev_close": num(4),
        "change": num(31),
        "change_pct": num(32),
        "high": num(33),
        "low": num(34),
        "amount_wan": num(37),  # 成交额（万元）
        "turnover_pct": num(38),
        "pe_ttm": num(39),
        "amplitude_pct": num(43),
        "total_mv": total_mv,
        "float_mv": float_mv,
        "bid": [{"p": num(9 + i * 2), "v": num(10 + i * 2)} for i in range(5)],
        "ask": [{"p": num(19 + i * 2), "v": num(20 + i * 2)} for i in range(5)],
    }


def fetch_kline(prefix: str, code: str, days: int = 250) -> list[dict]:
    """腾讯前复权日K线（带短 TTL 内存缓存）。"""
    ttl = get_settings().kline_cache_ttl
    return cached(
        f"kline:{prefix}:{code}:{days}",
        ttl,
        lambda: _fetch_kline(prefix, code, days),
    )


def _fetch_kline(prefix: str, code: str, days: int) -> list[dict]:
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={prefix}{code},day,,,{days},qfq"
    resp = requests.get(url, timeout=get_settings().request_timeout)
    data = resp.json()
    node = (data.get("data") or {}).get(f"{prefix}{code}") or {}
    rows = node.get("qfqday") or node.get("day") or []
    if not rows:
        raise HTTPException(404, f"未获取到 {prefix}{code} 的历史K线数据")
    result = []
    for r in rows:
        try:
            result.append(
                {
                    "date": r[0],
                    "open": float(r[1]),
                    "close": float(r[2]),
                    "high": float(r[3]),
                    "low": float(r[4]),
                    "volume": float(r[5] or 0),
                }
            )
        except (ValueError, IndexError):
            continue
    return result
