from __future__ import annotations

from pathlib import Path

from grid_analyzer.services.heatmap import (
    build_heatmap_payload,
    render_heatmap_html,
    write_heatmap,
)
from grid_analyzer.services.research import SweepParams, SweepResult


def make_result(gap: float, stop: float, score: float, init: float = 0.0) -> SweepResult:
    return SweepResult(
        params=SweepParams(gap_scale=gap, stop_loss=stop, init_position=init),
        plateau_score=score,
        mean_return_pct=score,
        compounded_return_pct=score,
        worst_return_pct=score,
        max_drawdown_pct=abs(score) / 2,
    )


def test_render_heatmap_contains_axes_and_values() -> None:
    results = [
        make_result(0.9, 0.0, 1.0),
        make_result(1.0, 0.0, 2.0),
        make_result(0.9, 5.0, 3.0),
        make_result(1.0, 5.0, 4.0),
    ]
    html = render_heatmap_html(results, code="TEST")
    assert "<!DOCTYPE html>" in html
    assert "TEST" in html
    assert "gap_scale" in html
    assert "stop_loss" in html
    assert "1.00" in html
    assert "4.00" in html


def test_render_heatmap_aggregates_init_positions() -> None:
    results = [
        make_result(1.0, 5.0, 1.0, init=0.0),
        make_result(1.0, 5.0, 3.0, init=0.2),
    ]
    html = render_heatmap_html(results, code="TEST")
    assert "2.00" in html
    assert 'data-count="2"' in html


def test_render_heatmap_empty() -> None:
    html = render_heatmap_html([], code="EMPTY")
    assert "暂无扫描结果" in html


def test_render_heatmap_drawdown_is_lower_better() -> None:
    results = [
        make_result(1.0, 0.0, 1.0),
        make_result(1.0, 5.0, 2.0),
    ]
    html = render_heatmap_html(results, code="TEST", metric="max_drawdown_pct")
    assert "最大单窗口回撤" in html
    assert "越低越好" in html


def test_write_heatmap(tmp_path: Path) -> None:
    output = tmp_path / "heatmap.html"
    path = write_heatmap([make_result(1.0, 5.0, 1.0)], output, code="TEST")
    assert path == output
    assert output.exists()
    assert "TEST" in output.read_text(encoding="utf-8")


def test_build_heatmap_payload() -> None:
    results = [
        make_result(0.9, 0.0, 1.0),
        make_result(1.0, 0.0, 2.0),
        make_result(0.9, 5.0, 3.0),
        make_result(1.0, 5.0, 4.0),
    ]
    payload = build_heatmap_payload(results, code="TEST")
    assert payload["code"] == "TEST"
    assert payload["gap_scales"] == [0.9, 1.0]
    assert payload["stop_losses"] == [0.0, 5.0]
    assert payload["init_positions"] == [0.0]
    assert len(payload["cells"]) == 4
    assert payload["best"] == {
        "gap_scale": 1.0,
        "stop_loss": 5.0,
        "value": 4.0,
        "count": 1,
    }
