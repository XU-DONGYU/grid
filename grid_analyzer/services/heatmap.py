from __future__ import annotations

import html
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

from grid_analyzer.services.research import SweepResult

METRIC_LABELS = {
    "plateau_score": "稳健性评分 plateau_score",
    "mean_return_pct": "样本外平均收益",
    "compounded_return_pct": "样本外复利收益",
    "worst_return_pct": "最差窗口收益",
    "max_drawdown_pct": "最大单窗口回撤",
}

LOWER_IS_BETTER = {"max_drawdown_pct"}


def _metric_value(result: SweepResult, metric: str) -> float:
    if metric not in METRIC_LABELS:
        raise ValueError(f"unsupported metric: {metric}")
    return float(getattr(result, metric))


def _format_value(value: float, metric: str) -> str:
    if metric == "plateau_score":
        return f"{value:.2f}"
    return f"{value:.2f}%"


def _color(value: float, low: float, high: float, reverse: bool) -> str:
    if high <= low:
        ratio = 0.5
    else:
        ratio = (value - low) / (high - low)
    ratio = max(0.0, min(1.0, ratio))
    if reverse:
        ratio = 1.0 - ratio
    if ratio < 0.5:
        t = ratio * 2
        r = 217 + (240 - 217) * t
        g = 48 + (195 - 48) * t
        b = 38 + (109 - 38) * t
    else:
        t = (ratio - 0.5) * 2
        r = 240 + (10 - 240) * t
        g = 195 + (138 - 195) * t
        b = 109 + (74 - 109) * t
    return f"#{int(r):02x}{int(g):02x}{int(b):02x}"


def _prepare_heatmap(
    results: list[SweepResult],
    *,
    code: str = "",
    metric: str = "plateau_score",
) -> dict[str, Any]:
    metric_label = METRIC_LABELS.get(metric)
    if metric_label is None:
        raise ValueError(f"unsupported metric: {metric}")

    if not results:
        return {
            "code": code,
            "metric": metric,
            "metric_label": metric_label,
            "direction": "lower" if metric in LOWER_IS_BETTER else "higher",
            "gap_scales": [],
            "stop_losses": [],
            "low": 0.0,
            "high": 0.0,
            "best": None,
            "cells": [],
            "sample_count": 0,
        }

    grouped: dict[tuple[float, float], list[float]] = defaultdict(list)
    for result in results:
        grouped[(result.params.gap_scale, result.params.stop_loss)].append(
            _metric_value(result, metric)
        )

    gap_scales = sorted({key[0] for key in grouped})
    stop_losses = sorted({key[1] for key in grouped})
    matrix = {
        key: (statistics.mean(values), len(values))
        for key, values in grouped.items()
    }
    all_values = [value for value, _ in matrix.values()]
    low, high = min(all_values), max(all_values)
    reverse = metric in LOWER_IS_BETTER
    best_key = min(matrix, key=lambda key: matrix[key][0]) if reverse else max(
        matrix, key=lambda key: matrix[key][0]
    )

    cells = []
    for gap in gap_scales:
        for stop in stop_losses:
            key = (gap, stop)
            if key not in matrix:
                continue
            value, count = matrix[key]
            cells.append(
                {
                    "gap_scale": gap,
                    "stop_loss": stop,
                    "value": value,
                    "count": count,
                    "color": _color(value, low, high, reverse),
                    "is_best": key == best_key,
                }
            )

    best_value, best_count = matrix[best_key]
    return {
        "code": code,
        "metric": metric,
        "metric_label": metric_label,
        "direction": "lower" if reverse else "higher",
        "gap_scales": gap_scales,
        "stop_losses": stop_losses,
        "low": low,
        "high": high,
        "best": {
            "gap_scale": best_key[0],
            "stop_loss": best_key[1],
            "value": best_value,
            "count": best_count,
        },
        "cells": cells,
        "sample_count": len(results),
    }


def build_heatmap_payload(
    results: list[SweepResult],
    *,
    code: str = "",
    metric: str = "plateau_score",
) -> dict[str, Any]:
    return _prepare_heatmap(results, code=code, metric=metric)


def render_heatmap_html(
    results: list[SweepResult],
    *,
    code: str = "",
    metric: str = "plateau_score",
    title: str | None = None,
) -> str:
    payload = _prepare_heatmap(results, code=code, metric=metric)
    title_text = title or f"{code} 参数高原热力图".strip()
    if not results:
        return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>{html.escape(title_text)}</title></head>
<body><h1>{html.escape(title_text)}</h1><p>暂无扫描结果。</p></body></html>
"""

    cell_map = {
        (cell["gap_scale"], cell["stop_loss"]): cell for cell in payload["cells"]
    }
    header = "".join(
        f"<th>{html.escape(f'{gap:.2f}')}</th>" for gap in payload["gap_scales"]
    )
    rows = []
    for stop in payload["stop_losses"]:
        cells = []
        for gap in payload["gap_scales"]:
            cell = cell_map.get((gap, stop))
            if cell is None:
                cells.append('<td class="empty">—</td>')
                continue
            css = "cell best" if cell["is_best"] else "cell"
            tooltip = (
                f"gap_scale={gap:.2f}, stop_loss={stop:.1f}, "
                f"{payload['metric_label']}={_format_value(cell['value'], metric)}, "
                f"样本数={cell['count']}"
            )
            cells.append(
                f'<td class="{css}" style="background:{cell["color"]}" '
                f'data-count="{cell["count"]}" title="{html.escape(tooltip)}">'
                f"{_format_value(cell['value'], metric)}</td>"
            )
        rows.append(
            f"<tr><th>{html.escape(f'{stop:.1f}')}</th>{''.join(cells)}</tr>"
        )

    direction = "越低越好" if payload["direction"] == "lower" else "越高越好"
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html.escape(title_text)}</title>
<style>
  :root {{ --text: #1f2733; --muted: #5b6472; --line: #e6eaf1; --bg: #f4f6fa; }}
  body {{ margin: 0; padding: 28px; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif; background: var(--bg); color: var(--text); }}
  .card {{ max-width: 980px; margin: 0 auto; background: #fff; border-radius: 14px; padding: 22px; box-shadow: 0 1px 4px rgba(16,35,72,.08); }}
  h1 {{ font-size: 22px; margin: 0 0 6px; }}
  p {{ color: var(--muted); font-size: 13px; margin: 0 0 16px; }}
  table {{ border-collapse: separate; border-spacing: 4px; width: 100%; table-layout: fixed; }}
  th {{ font-size: 12px; color: var(--muted); font-weight: 600; padding: 6px; }}
  th:first-child {{ width: 88px; }}
  td {{ text-align: center; font-size: 12px; font-weight: 600; padding: 12px 6px; border-radius: 8px; color: #1f2733; }}
  td.empty {{ background: #f3f5f8; color: #a0a8b5; font-weight: 400; }}
  td.best {{ outline: 3px solid #1a56db; outline-offset: 1px; }}
  .legend {{ display: flex; align-items: center; gap: 10px; margin-top: 16px; font-size: 12px; color: var(--muted); }}
  .bar {{ flex: 1; height: 12px; border-radius: 6px; background: linear-gradient(90deg, #d93026, #f0c36d, #0a8a4a); }}
  .note {{ margin-top: 14px; font-size: 12px; color: var(--muted); line-height: 1.7; }}
</style>
</head>
<body>
<div class="card">
  <h1>{html.escape(title_text)}</h1>
  <p>指标：{html.escape(payload['metric_label'])}（{direction}）。行 = stop_loss，列 = gap_scale。单元格为 init_position 维度上的均值。</p>
  <table>
    <thead><tr><th>stop \\ gap</th>{header}</tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
  <div class="legend"><span>{_format_value(payload['low'], metric)}</span><div class="bar"></div><span>{_format_value(payload['high'], metric)}</span></div>
  <div class="note">优先选择颜色连续、相邻格距和止损表现都稳定的高原区域，而不是单点最亮的孤岛。悬停单元格可查看样本数。</div>
</div>
</body>
</html>
"""


def write_heatmap(
    results: list[SweepResult],
    output: str | Path,
    *,
    code: str = "",
    metric: str = "plateau_score",
) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        render_heatmap_html(results, code=code, metric=metric),
        encoding="utf-8",
    )
    return path
