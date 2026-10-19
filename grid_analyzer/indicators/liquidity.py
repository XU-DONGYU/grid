from __future__ import annotations


def liquidity_grade(spread_pct: float, amount_wan: float) -> tuple[str, str]:
    """返回 (综合评级, 评级依据)。"""
    if spread_pct <= 0.15:
        s = "好"
    elif spread_pct <= 0.5:
        s = "中"
    else:
        s = "差"
    amt = amount_wan * 1e4
    if amt >= 3e8:
        a = "好"
    elif amt >= 1e8:
        a = "中"
    else:
        a = "差"
    if s == "差" or a == "差":
        grade = "差"
    elif s == "好" and a == "好":
        grade = "好"
    else:
        grade = "中"
    return grade, f"价差{s} / 成交额{a}"
