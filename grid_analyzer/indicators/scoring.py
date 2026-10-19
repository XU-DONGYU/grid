from __future__ import annotations


def fit_score(trend20: float, trend60: float, pct_b: float, atr_pct: float,
              squeeze: bool = False) -> int:
    score = 70
    a60 = abs(trend60)
    if a60 < 5:
        score += 15
    elif a60 <= 12:
        score += 5
    elif a60 <= 20:
        score -= 20
    else:
        score -= 35
    if 0.2 <= pct_b <= 0.8:
        score += 10
    elif pct_b < 0.05 or pct_b > 0.95:
        score -= 10
    if 1.5 <= atr_pct <= 4:
        score += 10
    elif atr_pct < 0.8:
        score -= 10
    elif atr_pct > 6:
        score -= 5
    if squeeze:
        score = min(score - 25, 45)
    return max(5, min(95, score))
