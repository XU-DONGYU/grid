from __future__ import annotations

import statistics

from fastapi import HTTPException


def compute_axis(closes: list[float]) -> dict:
    if not closes:
        raise HTTPException(400, "历史数据为空，无法计算中轴")
    n20 = closes[-min(20, len(closes)):]
    n60 = closes[-min(60, len(closes)):]
    median60 = statistics.median(n60)
    return {
        "median60": median60,
        "mean60": sum(n60) / len(n60),
        "ma20": sum(n20) / len(n20),
        "ma60": sum(n60) / len(n60),
        "recommended": median60,
    }
