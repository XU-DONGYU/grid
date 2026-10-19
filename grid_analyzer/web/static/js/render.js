import { $ } from './dom.js';
import { fmt, fmtWan, pctCls, pctOrDash } from './format.js';
import { drawChart, drawEquityChart, syncLayerUI } from './charts.js';

function kv(k, v, cls='', tip=''){ return `<div class="kv"><div class="k"${tip?` title="${tip}"`:''}>${k}</div><div class="v ${cls}">${v}</div></div>`; }

export function render(d){
  const q = d.quote;
  const single = d.params.single_grid;   // 仅主网格模式
  $('ver').textContent = d.version ? '· 后端 v'+d.version : '· 后端版本未返回（可能仍是旧进程，请重启 uvicorn）';
  // ---- 股票概览 ----
  $('s-name').textContent = q.name;
  $('s-code').textContent = q.market_code.toUpperCase() + ' · ' + q.code + (q.pe_ttm ? ' · PE ' + fmt(q.pe_ttm,1) : '');
  $('s-price').textContent = fmt(q.price);
  $('s-price').className = 'price ' + (q.change>=0?'up':'down');
  $('s-change').innerHTML = `<span class="${pctCls(q.change)}">${q.change>=0?'+':''}${fmt(q.change)}（${q.change>=0?'+':''}${fmt(q.change_pct)}%）</span>`;
  const lg = d.liquidity.grade;
  $('s-liq').innerHTML = `流动性 <span class="badge ${lg==='好'?'good':lg==='中'?'mid':'bad'}">${lg}</span>`;
  $('s-kv').innerHTML =
    kv('成交额', fmtWan(q.amount_wan*1e4)) +
    kv('换手率', fmt(q.turnover_pct)+'%') +
    kv('今日振幅', fmt(q.amplitude_pct)+'%') +
    kv('今日最高/最低', fmt(q.high)+' / '+fmt(q.low)) +
    kv('52周最高/最低', fmt(q.high_52w)+' / '+fmt(q.low_52w)) +
    kv('总市值', (Number(q.total_mv) > 0) ? fmt(q.total_mv,0)+' 亿' : '—') +
    kv('买卖价差', fmt(d.liquidity.spread_pct,3)+'%') +
    kv('五档买盘承接', fmtWan(d.liquidity.bid_depth_yuan));

  // ---- 图表 ----
  drawChart(d);
  syncLayerUI();
  const kd = d.kline_tail;
  $('chart-note').innerHTML =
    `<b>数据区间：${kd[0].date} ~ ${kd[kd.length-1].date}</b>（近 ${kd.length} 个交易日，已更新至最新收盘）。` +
    `蓝色带 = 主网格区间${single ? '' : '，橙色带 = 辅助网格区间（含于主区间内）'}；` +
    `蓝色横虚线 + 右侧<b style="color:#4a6fb5">蓝色价格</b> = 主网格档位挂单价，` +
    `${single ? '' : '橙色横虚线 + 右侧<b style="color:#c2700c">橙色价格</b> = 辅助网格档位挂单价，'}红色横虚线 = 推荐中轴（60日收盘中位数），● = 当前价`;

  // ---- 网格参数 ----
  const g1 = d.main_grid, g2 = d.aux_grid, capital_total = d.params.capital;
  $('grid-main').innerHTML =
    kv('网格区间', `${fmt(g1.lower)} ~ ${fmt(g1.upper)} 元`) +
    kv('区间宽度', fmt((g1.upper/g1.lower-1)*100,1)+'%') +
    kv('网格间距', fmt(g1.gap_pct)+'%') +
    kv('ATR锚定', fmt(g1.atr_gap_pct)+'%', '', '0.70 × ATR14%，掐去头尾极值，锚定最常出现的波幅躯干') +
    kv('档位数量', (g1.levels.length-1)+' 档（可买）') +
    kv('分配资金', fmtWan(g1.capital)) +
    kv('每格股数', fmt(g1.shares_per_grid,0)+' 股') +
    kv('每格金额', fmtWan(g1.grid_cost)) +
    kv('最低间距门槛', fmt(g1.min_gap_pct)+'%', '');
  $('grid-aux').innerHTML = single
    ? `<div class="note" style="background:var(--orange-light);border-radius:9px;padding:10px 12px;margin:0">
         未启用 —— 仅主网格模式：全部资金 <b>${fmtWan(capital_total)}</b> 已分配给主网格，不再设置辅助网格。</div>`
    : (g2.shares_per_grid > 0 ?
    kv('网格区间', `${fmt(g2.lower)} ~ ${fmt(g2.upper)} 元`) +
    kv('区间宽度', fmt((g2.upper/g2.lower-1)*100,1)+'%') +
    kv('网格间距', fmt(g2.gap_pct)+'%') +
    kv('ATR锚定', fmt(g2.atr_gap_pct)+'%', '', '0.55 × ATR14%，辅助网格更关注碎波段的换手') +
    kv('档位数量', (g2.levels.length-1)+' 档（可买）') +
    kv('分配资金', fmtWan(g2.capital)) +
    kv('每格股数', fmt(g2.shares_per_grid,0)+' 股') +
    kv('每格金额', fmtWan(g2.grid_cost))
    : `<div class="risk-item">辅助网格每格资金不足一手（100股），建议只跑主网格或增加资金</div>`);
  const constrainedNote = (g1.capital_constrained || (!single && g2.capital_constrained))
    ? ' <b style="color:var(--mid)">资金约束：</b>为保证每格至少成交一手，系统已自动拉宽间距。'
    : '';
  $('grid-note').innerHTML = (single
    ? `费用规则：佣金双边各收 ${fmt(d.params.fee_pct)}%（单笔最低 ${fmt(d.params.min_fee,0)} 元），卖出另收印花税 0.05%。主网格每格金额 ${fmtWan(g1.grid_cost)}，最低间距门槛 <b>${fmt(g1.min_gap_pct)}%</b>（价差 ${fmt(d.liquidity.spread_pct,3)}% + 往返成本 + 0.15% 缓冲）。主网格间距 = max(1.2×门槛, 0.70×ATR%, 1.0×日σ)，采用等比档位。每格股数按100股取整，最高档不买入（防踏空保护）。`
    : `费用规则：佣金双边各收 ${fmt(d.params.fee_pct)}%（单笔最低 ${fmt(d.params.min_fee,0)} 元），卖出另收印花税 0.05%。主网格最低间距门槛 <b>${fmt(g1.min_gap_pct)}%</b>，辅助网格最低间距门槛 <b>${fmt(g2.min_gap_pct)}%</b>。主网格间距 = max(1.2×门槛, 0.70×ATR%, 1.0×日σ)；辅助网格间距 = max(1×门槛, 0.55×ATR%, 0.7×日σ)，均为等比档位。每格股数按100股取整，最高档不买入（防踏空保护）。`
  ) + constrainedNote;

  // ---- 中轴 ----
  const a = d.axis;
  $('axis-rows').innerHTML =
    `<div class="axis-row reco"><span title="近60个交易日收盘价排序取中间值，不受单日暴涨暴跌影响，最稳健。网格以它为中心上下对称展开">60日收盘中位数（推荐）</span><b>${fmt(a.median60)}</b></div>` +
    `<div class="axis-row"><span title="近60个交易日收盘价的算术平均，受极端涨跌影响比中位数大，可作中轴备选">60日收盘均值</span><b>${fmt(a.mean60)}</b></div>` +
    `<div class="axis-row"><span title="20日均线（近20日收盘均值），短中期价格重心，与布林带中轨重合">MA20（布林中轨）</span><b>${fmt(a.ma20)}</b></div>` +
    `<div class="axis-row"><span title="60日均线（近60日收盘均值），中期趋势分水岭，价格在其上方偏多、下方偏空">MA60</span><b>${fmt(a.ma60)}</b></div>` +
    `<div class="axis-row"><span title="现价 ÷ 60日中位数 − 1。正值说明现价高于网格中枢（当前偏上沿），负值偏低">当前价相对推荐中轴</span><b class="${q.price>a.median60?'up':'down'}">${q.price>a.median60?'偏高':'偏低'} ${fmt(Math.abs(q.price/a.median60-1)*100,1)}%</b></div>`;

  // ---- 波动率 ----
  const v = d.volatility, t = d.trend;
  const squeezeTag = v.squeeze ? '<span class="badge bad">挤压禁区</span>' : '<span class="badge good">未挤压</span>';
  $('vol-kv').innerHTML =
    kv('日波动率 σ', fmt(v.sigma_daily_pct)+'%', '', '近120个交易日每日涨跌幅的标准差，衡量单日波动幅度。σ 越大，网格间距建议越大') +
    kv('年化波动率', fmt(v.sigma_annual_pct,1)+'%', '', '日波动率 × √243（年化交易日数）折算到一年，反映整体风险水平，与同类标的可比') +
    kv('波动率方差', pctOrDash(v.vol_of_vol_pct,1), '', '滚动20日日波动率的标准差（年化），衡量波动率自身的离散程度。过高说明市场状态易突变') +
    kv('ATR(14)', fmt(v.atr)+'（'+fmt(v.atr_pct)+'%）', '', '14日平均真实波幅，含跳空缺口，比标准差更贴近实际盘面跳动。ATR 越大，每格价差应越大') +
    kv('布林带宽(20日)', fmt(v.boll_width_pct,2)+'%', '', '(上轨−下轨) ÷ 中轨 = 4×变异系数，衡量近20日价格波动收窄还是放大') +
    kv('带宽历史分位', pctOrDash(v.boll_width_percentile,0), '', '当前布林带宽在可用历史带宽中的分位。≤10% 视为极度挤压，是网格禁区') +
    kv('挤压判定', squeezeTag + (v.ttm_squeeze ? ' TTM' : ''), '', 'TTM Squeeze：布林带上下轨完全收缩进肯特纳通道内部，常预示变盘突破') +
    kv('20日趋势', (t.trend20_pct>0?'+':'')+fmt(t.trend20_pct,1)+'%', pctCls(t.trend20_pct), '近20日收盘累计涨跌幅。正值=短期上行，负值=短期下行') +
    kv('60日趋势', (t.trend60_pct>0?'+':'')+fmt(t.trend60_pct,1)+'%', pctCls(t.trend60_pct), '近60日收盘累计涨跌幅。正值=中期上行，负值=中期下行') +
    kv('布林%B位置', fmt(t.pct_b*100,0)+'%', '', '(现价−下轨) ÷ (上轨−下轨)。0≈贴下轨，1≈贴上轨；>1 超涨，<0 超跌') +
    kv('行情形态', t.regime, '', '由趋势、波动率与挤压状态综合判定：单边趋势、波动挤压均不适合开网格');
  const fit = t.fit_score;
  const fitColor = fit>=75?'var(--good)':fit>=50?'var(--mid)':'var(--bad)';
  const fitText = fit>=75?'适合网格':fit>=50?'尚可，注意仓位':'不适合，建议观望';
  $('fit-bar').style.width = fit+'%'; $('fit-bar').style.background = fitColor;
  $('fit-num').textContent = fit; $('fit-num').style.color = fitColor;
  $('fit-label').textContent = fitText;

  // ---- 回测 ----
  const b = d.backtest, bm = d.backtest_meta || {};
  const validBt = bt => !!(bt && bt.equity_curve && bt.equity_curve.length);
  const row = (name, bt) => validBt(bt) ? `<tr>
      <td>${name}</td>
      <td class="num">${bt.rounds}</td>
      <td class="num">${bt.buy_count} / ${bt.sell_count}</td>
      <td class="num ${bt.net_profit>=0?'up':'down'}">${bt.net_profit>=0?'+':''}${fmtWan(bt.net_profit)}</td>
      <td class="num ${bt.return_pct>=0?'up':'down'}">${bt.return_pct>=0?'+':''}${fmt(bt.return_pct)}%</td>
      <td class="num ${bt.annual_pct>=0?'up':'down'}">${bt.annual_pct>=0?'+':''}${fmt(bt.annual_pct,1)}%</td>
      <td class="num">${fmt(bt.max_drawdown_pct)}%</td>
      <td class="num">${bt.max_holding_cnt}</td>
      <td class="num">${fmtWan(bt.max_position_cost)}</td>
      <td class="num">${fmtWan(bt.end_holding_value)}</td>
      <td class="num ${bt.min_float_pnl>=0?'':'down'}">${fmtWan(bt.min_float_pnl)}</td>
      <td>${bt.stop_triggered
        ? `<span class="bt-tag stop" title="止损价 ${fmt(bt.stop_price)}，成交价 ${fmt(bt.stop_fill_price)}">${bt.stop_date || '已止损'}</span>`
        : '<span class="bt-tag idle">未触发</span>'}</td></tr>`
    : `<tr><td>${name}</td><td colspan="11" style="color:var(--text3)">历史校准参数下资金不足或未产生有效回测</td></tr>`;
  $('bt-wrap').innerHTML = `<table class="bt-table">
    <tr><th>网格</th><th class="num">完整回合</th><th class="num">买入/卖出</th><th class="num">净利(含费)</th><th class="num">收益率</th><th class="num">年化预估</th><th class="num">最大回撤</th><th class="num">最大持仓格</th><th class="num">最大持仓成本</th><th class="num">期末持仓市值</th><th class="num">最深持仓浮亏</th><th>破网止损</th></tr>
    ${row('主网格（历史校准）', b.main)}${single ? '<tr><td>辅助网格</td><td colspan="11" style="color:var(--text3)">未启用（仅主网格模式）</td></tr>' : row('辅助网格（历史校准）', b.aux)}</table>`;
  const meta = bt => validBt(bt) ? `总费用 <b>${fmtWan(bt.total_fees)}</b> · 已实现 <b class="${bt.realized_pnl>=0?'up':'down'}">${fmtWan(bt.realized_pnl)}</b> · 未实现 <b class="${bt.unrealized_pnl>=0?'up':'down'}">${fmtWan(bt.unrealized_pnl)}</b> · 换手 <b>${fmtWan(bt.turnover)}</b> · 跳过买单 <b>${bt.skipped_buys}</b>` : '未产生有效回测';
  const calibNote = bm.used_calibration
    ? `回测参数：以 ${bm.start_date} 前 <b>${bm.calibration_days}</b> 日数据校准（无未来函数），主网格区间 <b>${fmt(bm.main_lower)} ~ ${fmt(bm.main_upper)}</b>，间距 <b>${fmt(bm.main_gap_pct)}%</b>，每格 <b>${fmt(bm.main_shares_per_grid,0)}</b> 股。当前推荐参数基于最新数据，与回测参数可能不同。`
    : `回测参数：历史校准数据不足，暂用当前参数回测（存在未来函数风险）。`;
  $('bt-note').innerHTML = calibNote + `<br>主网格：${meta(b.main)}` + (single ? '' : `<br>辅助网格：${meta(b.aux)}`);
  drawEquityChart(d);

  // ---- 风险 ----
  $('risks').innerHTML = d.risks.length
    ? d.risks.map(r => `<div class="risk-item">⚠️ ${r}</div>`).join('')
    : '<div class="risk-none">✅ 未检测到明显风险信号（基于近120日数据）</div>';
}
