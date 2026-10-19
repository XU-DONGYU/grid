#!/usr/bin/env python3
"""Run the 5-minute parameter plateau research from the command line."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from grid_analyzer.api.schemas import IntradayHeatmapRequest  # noqa: E402
from grid_analyzer.data.intraday import IntradayRepository  # noqa: E402
from grid_analyzer.data.tencent import TencentMarketDataProvider  # noqa: E402
from grid_analyzer.services.intraday_heatmap import IntradayHeatmapService  # noqa: E402


def floats(value: str) -> list[float]:
    return [float(item.strip()) for item in value.split(",") if item.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--code", required=True)
    parser.add_argument("--capital", type=float, default=100_000)
    parser.add_argument("--fee", type=float, default=0.025, help="单边佣金 %%")
    parser.add_argument("--min-fee", type=float, default=5.0)
    parser.add_argument("--init-position", type=float, default=0.0)
    parser.add_argument("--stop-losses", default="0,3,5,8")
    parser.add_argument("--k-start", type=float, default=0.5)
    parser.add_argument("--k-end", type=float, default=1.5)
    parser.add_argument("--k-step", type=float, default=0.05)
    parser.add_argument("--window-days", type=int, default=126)
    parser.add_argument("--in-sample-ratio", type=float, default=0.70)
    parser.add_argument("--final-blind-days", type=int, default=63)
    parser.add_argument("--min-oos-days", type=int, default=252)
    parser.add_argument(
        "--primary-metric",
        default="realized_annual_pct",
        choices=[
            "realized_annual_pct",
            "total_annual_pct",
            "calmar",
            "sharpe",
            "sortino",
            "max_drawdown_pct",
        ],
    )
    parser.add_argument("--history-days", type=int, default=500)
    parser.add_argument("--output-dir", default="reports")
    args = parser.parse_args()

    request = IntradayHeatmapRequest(
        code=args.code,
        capital=args.capital,
        fee=args.fee,
        min_fee=args.min_fee,
        init_position=args.init_position,
        stop_losses=floats(args.stop_losses),
        k_start=args.k_start,
        k_end=args.k_end,
        k_step=args.k_step,
        window_days=args.window_days,
        in_sample_ratio=args.in_sample_ratio,
        final_blind_days=args.final_blind_days,
        min_oos_days=args.min_oos_days,
        primary_metric=args.primary_metric,
        history_days=args.history_days,
    )
    service = IntradayHeatmapService(
        IntradayRepository(),
        TencentMarketDataProvider(),
    )
    try:
        data = service.run(request)
    except Exception as exc:
        print(f"计算失败：{exc}", file=sys.stderr)
        return 2

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"intraday_{args.code}.json"
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    folds_path = output_dir / f"intraday_{args.code}_folds.csv"
    with folds_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "in_sample_start",
                "in_sample_end",
                "oos_start",
                "oos_end",
                "selected_k",
                "selected_stop_loss",
                "atr_pct",
                "gap_pct",
                "capital_constrained",
                "in_sample_metrics",
                "oos_metrics",
            ],
        )
        writer.writeheader()
        for fold in data["folds"]:
            row = dict(fold)
            row["in_sample_metrics"] = json.dumps(fold["in_sample_metrics"], ensure_ascii=False)
            row["oos_metrics"] = json.dumps(fold["oos_metrics"], ensure_ascii=False)
            writer.writerow(row)

    cells_path = output_dir / f"intraday_{args.code}_cells.csv"
    with cells_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "k",
                "stop_loss",
                "fold_count",
                "plateau_score",
                "realized_annual_pct",
                "total_annual_pct",
                "calmar",
                "sharpe",
                "sortino",
                "max_drawdown_pct",
                "win_rate_pct",
                "profit_factor",
                "stop_count",
                "exposure_pct",
            ],
        )
        writer.writeheader()
        for cell in data["cells"]:
            row = {
                "k": cell["k"],
                "stop_loss": cell["stop_loss"],
                "fold_count": cell["fold_count"],
                "plateau_score": cell["plateau_score"],
            }
            for key, value in cell["metrics"].items():
                row[key] = value.get("mean")
            writer.writerow(row)

    summary = data["summary"]
    locked = data["locked"]
    print(f"{data['context']['name']} {args.code}")
    print(
        f"K {args.k_start:.2f}~{args.k_end:.2f} step {args.k_step:.2f} | "
        f"OOS {summary['oos_coverage_months']:.1f} months | folds {summary['fold_count']}"
    )
    print(
        f"locked K={locked['k']:.2f} stop={locked['stop_loss']:.1f}% | "
        f"OOS mean {summary['oos_primary_mean']:.2f} worst {summary['oos_primary_worst']:.2f}"
    )
    if locked.get("blind"):
        blind = locked["blind"]["metrics"]
        print(
            f"blind {locked['blind']['start']}~{locked['blind']['end']} | "
            f"realized {blind.get('realized_annual_pct', 0):.2f}% "
            f"calmar {blind.get('calmar', 0):.2f} sharpe {blind.get('sharpe', 0):.2f}"
        )
    print(f"JSON: {json_path}")
    print(f"Folds CSV: {folds_path}")
    print(f"Cells CSV: {cells_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
