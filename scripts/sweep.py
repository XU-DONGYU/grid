#!/usr/bin/env python3
"""Parameter sweep with rolling walk-forward validation."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from grid_analyzer.data.tencent import TencentMarketDataProvider  # noqa: E402
from grid_analyzer.services.heatmap import write_heatmap  # noqa: E402
from grid_analyzer.services.research import run_parameter_sweep  # noqa: E402


def floats(value: str) -> list[float]:
    return [float(item.strip()) for item in value.split(",") if item.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--code", required=True, help="股票代码，如 002541")
    parser.add_argument("--capital", type=float, default=100_000)
    parser.add_argument("--fee", type=float, default=0.025, help="单边佣金 %%")
    parser.add_argument("--min-fee", type=float, default=5.0, help="单笔最低佣金")
    parser.add_argument("--spread-pct", type=float, default=0.05, help="历史价差代理 %%")
    parser.add_argument("--history-days", type=int, default=750)
    parser.add_argument("--gap-scales", default="0.8,0.9,1.0,1.1,1.2")
    parser.add_argument("--stop-losses", default="0,3,5,8")
    parser.add_argument("--init-positions", default="0,0.2")
    parser.add_argument("--calib-days", type=int, default=250)
    parser.add_argument("--test-days", type=int, default=60)
    parser.add_argument("--step", type=int, default=60)
    parser.add_argument("--output", help="CSV 输出路径，默认 reports/sweep_<code>.csv")
    parser.add_argument("--heatmap", help="HTML 热力图路径，默认与 CSV 同名 .html")
    parser.add_argument("--heatmap-metric", default="plateau_score", help="热力图指标")
    args = parser.parse_args()

    provider = TencentMarketDataProvider()
    quote = provider.get_quote(args.code)
    klines = provider.get_klines(args.code, args.history_days)
    if len(klines) < args.calib_days + args.test_days:
        print(
            f"历史数据不足：需要 {args.calib_days + args.test_days} 条，实际 {len(klines)} 条",
            file=sys.stderr,
        )
        return 2

    results = run_parameter_sweep(
        klines,
        gap_scales=floats(args.gap_scales),
        stop_losses=floats(args.stop_losses),
        init_positions=floats(args.init_positions),
        capital=args.capital,
        fee=args.fee,
        min_fee=args.min_fee,
        main_ratio=1.0,
        spread_pct=args.spread_pct,
        calib_days=args.calib_days,
        test_days=args.test_days,
        step=args.step,
        single=True,
    )
    if not results:
        print("没有可用的 walk-forward 窗口，请增加历史数据或减小窗口", file=sys.stderr)
        return 2

    output = Path(args.output) if args.output else Path("reports") / f"sweep_{args.code}.csv"
    output.parent.mkdir(parents=True, exist_ok=True)
    records = [result.to_record() for result in results]
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(records[0].keys()))
        writer.writeheader()
        writer.writerows(records)
    json_output = output.with_suffix(".json")
    json_output.write_text(
        json.dumps([asdict(result) for result in results], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    heatmap_output = Path(args.heatmap) if args.heatmap else output.with_suffix(".html")
    write_heatmap(
        results,
        heatmap_output,
        code=args.code,
        metric=args.heatmap_metric,
    )

    print(f"{quote['name']} {quote['code']} 当前价 {quote['price']:.2f}")
    print(f"数据 {len(klines)} 条，窗口 {args.calib_days}/{args.test_days}，步长 {args.step}")
    print(
        f"{'gap_scale':>9} {'stop':>5} {'init':>5} {'mean%':>8} {'worst%':>8} "
        f"{'compound%':>10} {'maxDD%':>8} {'plateau':>8}"
    )
    for result in results[:10]:
        p = result.params
        print(
            f"{p.gap_scale:9.2f} {p.stop_loss:5.1f} {p.init_position:5.2f} "
            f"{result.mean_return_pct:8.2f} {result.worst_return_pct:8.2f} "
            f"{result.compounded_return_pct:10.2f} {result.max_drawdown_pct:8.2f} "
            f"{result.plateau_score:8.2f}"
        )
    print(f"CSV: {output}")
    print(f"JSON: {json_output}")
    print(f"HTML: {heatmap_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
