#!/usr/bin/env python3
"""Run one grid parameter set across rolling walk-forward windows."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from grid_analyzer.data.tencent import TencentMarketDataProvider  # noqa: E402
from grid_analyzer.services.research import SweepParams, run_walk_forward  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--code", required=True)
    parser.add_argument("--gap-scale", type=float, default=1.0)
    parser.add_argument("--stop-loss", type=float, default=5.0)
    parser.add_argument("--init-position", type=float, default=0.0)
    parser.add_argument("--capital", type=float, default=100_000)
    parser.add_argument("--fee", type=float, default=0.025)
    parser.add_argument("--min-fee", type=float, default=5.0)
    parser.add_argument("--spread-pct", type=float, default=0.05)
    parser.add_argument("--history-days", type=int, default=750)
    parser.add_argument("--calib-days", type=int, default=250)
    parser.add_argument("--test-days", type=int, default=60)
    parser.add_argument("--step", type=int, default=60)
    parser.add_argument("--output", help="JSON 输出路径")
    args = parser.parse_args()

    provider = TencentMarketDataProvider()
    quote = provider.get_quote(args.code)
    klines = provider.get_klines(args.code, args.history_days)
    result = run_walk_forward(
        klines,
        SweepParams(
            gap_scale=args.gap_scale,
            stop_loss=args.stop_loss,
            init_position=args.init_position,
        ),
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
    if not result.folds:
        print("没有可用的 walk-forward 窗口", file=sys.stderr)
        return 2

    output = Path(args.output) if args.output else Path("reports") / f"walk_forward_{args.code}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(asdict(result), ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"{quote['name']} {quote['code']} 当前价 {quote['price']:.2f}")
    print(f"{'训始':>10} {'训末':>10} {'测始':>10} {'测末':>10} {'收益%':>8} {'回撤%':>8} {'回合':>5} {'止损':>4}")
    for fold in result.folds:
        print(
            f"{fold.calib_start:>10} {fold.calib_end:>10} {fold.test_start:>10} "
            f"{fold.test_end:>10} {fold.return_pct:8.2f} {fold.max_drawdown_pct:8.2f} "
            f"{fold.rounds:5d} {'Y' if fold.stop_triggered else 'N':>4}"
        )
    print(
        f"均值 {result.mean_return_pct:.2f}% | 最差 {result.worst_return_pct:.2f}% | "
        f"复利 {result.compounded_return_pct:.2f}% | 最大回撤 {result.max_drawdown_pct:.2f}% | "
        f"plateau {result.plateau_score:.2f}"
    )
    print(f"JSON: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
