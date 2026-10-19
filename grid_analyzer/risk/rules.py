from __future__ import annotations


def collect_risks(d: dict) -> list[str]:
    risks: list[str] = []
    q = d["quote"]
    t = d["trend"]
    v = d["volatility"]
    liq = d["liquidity"]
    g1, g2 = d["main_grid"], d["aux_grid"]
    axis = d["axis"]
    single = d["params"]["single_grid"]
    stop_loss = d["params"].get("stop_loss_pct", 0)

    if abs(t["trend60_pct"]) >= 12 and abs(t["trend20_pct"]) >= 8 and t["trend20_pct"] * t["trend60_pct"] > 0:
        risks.append(f"近60日趋势 {t['trend60_pct']:+.1f}%，近20日趋势 {t['trend20_pct']:+.1f}%，呈单边行情，网格易单边接飞刀或提前卖飞，建议谨慎")
    elif abs(t["trend20_pct"]) >= 8:
        risks.append(f"近20日短期趋势明显（{t['trend20_pct']:+.1f}%），注意区间可能被击穿")

    if v.get("squeeze"):
        reason = "TTM Squeeze 双通道内嵌" if v.get("ttm_squeeze") else f"带宽处于历史 {v.get('boll_width_percentile', 50):.0f}% 分位"
        risks.append(f"布林带宽 {v.get('boll_width_pct', 0):.2f}%（{reason}），疑似极度挤压。挤压期网格套利空间被摩擦成本吞噬，且随时可能单边突破，属于开网格禁区")

    off = q["price"] / axis["recommended"] - 1
    if abs(off) > 0.2:
        risks.append(f"当前价偏离推荐中轴 {off * 100:+.0f}%，可能已进入超跌/超涨区，区间参考性下降")
    if v["atr_pct"] > 6:
        risks.append(f"ATR 高达 {v['atr_pct']:.1f}%，波动剧烈，网格单格利润可能被滑点侵蚀")
    if v["atr_pct"] < 0.8:
        risks.append(f"ATR 仅 {v['atr_pct']:.2f}%，波动过小，网格触发频率低，资金利用率不高")
    if v.get("vol_of_vol_pct", 0) >= 30:
        risks.append(f"波动率方差 {v['vol_of_vol_pct']:.1f}%（年化），波动率自身离散度高，市场易由震荡切换为单边，建议拉宽格距或降低仓位")
    if liq["grade"] == "差":
        risks.append("流动性评级为「差」，盘口薄、价差大，网格成交滑点风险高")
    if g1.get("capital_constrained"):
        risks.append(f"资金约束：主网格为保证每格至少一手，间距被拉宽至 {g1['gap_pct']:.1f}%，仅 {len(g1['levels']) - 1} 个可买档位，网格套利属性弱化，建议增加资金或选择低价标的")
    if not single and g2.get("capital_constrained"):
        risks.append(f"资金约束：辅助网格间距被拉宽至 {g2['gap_pct']:.1f}%，仅 {len(g2['levels']) - 1} 个可买档位")
    if g1["grid_cost"] > liq["bid_depth_yuan"] * 0.2 and liq["bid_depth_yuan"] > 0:
        risks.append(f"主网格每格金额 {g1['grid_cost'] / 1e4:.1f} 万 超过五档买盘承接的 20%，大单卖出可能砸穿盘口")
    if not single and g2["grid_cost"] > liq["bid_depth_yuan"] * 0.2 and liq["bid_depth_yuan"] > 0:
        risks.append(f"辅助网格每格金额 {g2['grid_cost'] / 1e4:.1f} 万 超过五档买盘承接的 20%，冲击成本较高")
    if not stop_loss:
        risks.append("未启用破网止损：单边下跌时持仓与单笔跌幅双重放大，浮亏近似随价格偏离度平方增长，建议设置 3%~8% 的破网清仓阈值")
    else:
        for label, bt in (("主网格", d.get("backtest", {}).get("main")),
                          ("辅助网格", d.get("backtest", {}).get("aux"))):
            if bt and bt.get("stop_triggered"):
                risks.append(f"{label}在回测期内触发破网止损（{bt.get('stop_date') or '—'}，成交价 {bt.get('stop_fill_price', 0):.2f}），说明区间下沿曾被击穿，实盘需复核区间与止损阈值")
    return risks
