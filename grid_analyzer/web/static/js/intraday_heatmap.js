import { fmt } from './format.js';

const METRICS = [
  ['realized_annual_pct', '已实现网格年化', '%'],
  ['total_annual_pct', '总权益年化', '%'],
  ['calmar', 'Calmar', ''],
  ['sharpe', 'Sharpe', ''],
  ['sortino', 'Sortino', ''],
  ['max_drawdown_pct', '最大回撤（越低越好）', '%'],
];

const COLORS = ['#1a56db', '#c2700c', '#0a8a4a', '#8b5cf6', '#d93026', '#0891b2', '#6b7280'];

function metricText(value, unit, digits = 2) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return '—';
  return fmt(value, digits) + unit;
}

function cellMap(cells) {
  const map = new Map();
  cells.forEach(cell => map.set(`${cell.k}|${cell.stop_loss}`, cell));
  return map;
}

function lineChart(metric, label, unit, data, lockedK) {
  const kValues = data.k_values;
  const stops = data.stop_losses;
  const map = cellMap(data.cells);
  const series = stops.map(stop => ({
    stop,
    values: kValues.map(k => {
      const cell = map.get(`${k}|${stop}`);
      return cell && cell.fold_count > 0 ? Number(cell.metrics[metric]?.mean ?? 0) : null;
    }),
  })).filter(series => series.values.some(value => value !== null));
  if (!series.length) {
    return `<div class="intraday-chart"><div class="intraday-chart-title">${label}</div><div class="note">无有效样本</div></div>`;
  }

  const W = 360, H = 220, L = 52, R = 16, T = 18, B = 34;
  const iw = W - L - R, ih = H - T - B;
  const all = series.flatMap(item => item.values).filter(value => value !== null);
  let low = Math.min(...all), high = Math.max(...all);
  if (low === high) {
    low -= 1;
    high += 1;
  }
  const pad = (high - low) * 0.12;
  low -= pad;
  high += pad;
  const x = i => L + iw * (kValues.length <= 1 ? 0 : i / (kValues.length - 1));
  const y = value => T + ih * (1 - (value - low) / (high - low));

  const yTicks = [];
  for (let i = 0; i <= 4; i++) {
    const value = low + (high - low) * i / 4;
    yTicks.push(`<line x1="${L}" x2="${W - R}" y1="${y(value)}" y2="${y(value)}" stroke="#eef1f6"/>`);
    yTicks.push(`<text x="${L - 7}" y="${y(value) + 3.5}" font-size="9" fill="#8b93a1" text-anchor="end">${fmt(value, 1)}</text>`);
  }
  const xTicks = kValues.map((k, i) => {
    if (kValues.length > 7 && i !== 0 && i !== kValues.length - 1 && i % 5 !== 0) return '';
    return `<text x="${x(i)}" y="${H - 10}" font-size="9" fill="#8b93a1" text-anchor="middle">${fmt(k, 2)}</text>`;
  }).join('');

  const lines = series.map((item, index) => {
    const color = COLORS[index % COLORS.length];
    let path = '';
    let started = false;
    item.values.forEach((value, i) => {
      if (value === null) return;
      path += `${started ? 'L' : 'M'}${x(i).toFixed(1)},${y(value).toFixed(1)} `;
      started = true;
    });
    return `<path d="${path}" fill="none" stroke="${color}" stroke-width="1.8"/>`;
  }).join('');

  const lockedIndex = Math.max(0, kValues.indexOf(lockedK));
  const lockedX = x(lockedIndex);
  const legend = series.map((item, index) => {
    const color = COLORS[index % COLORS.length];
    return `<span><i style="background:${color}"></i>止损 ${fmt(item.stop, 1)}%</span>`;
  }).join('');

  return `<div class="intraday-chart">
    <div class="intraday-chart-title">${label}${unit ? '（' + unit + '）' : ''}</div>
    <div class="intraday-legend">${legend}</div>
    <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${label}">
      ${yTicks.join('')}${xTicks}
      <line x1="${L}" x2="${W - R}" y1="${T + ih}" y2="${T + ih}" stroke="#c3ccda"/>
      <line x1="${lockedX}" x2="${lockedX}" y1="${T}" y2="${T + ih}" stroke="#d93026" stroke-width="1" stroke-dasharray="4 4" opacity=".55"/>
      ${lines}
    </svg>
  </div>`;
}

const PERCENT_METRICS = new Set(['realized_annual_pct', 'total_annual_pct', 'max_drawdown_pct']);

function foldRows(data, primaryMetric) {
  const primaryUnit = PERCENT_METRICS.has(primaryMetric) ? '%' : '';
  return data.folds.map((fold, index) => {
    const inValue = fold.in_sample_metrics?.[primaryMetric];
    const oosValue = fold.oos_metrics?.[primaryMetric];
    return `<tr>
      <td>${index + 1}</td>
      <td>${fold.in_sample_start} ~ ${fold.in_sample_end}</td>
      <td>${fold.oos_start} ~ ${fold.oos_end}</td>
      <td class="num">${fmt(fold.selected_k, 2)}</td>
      <td class="num">${fmt(fold.selected_stop_loss, 1)}%</td>
      <td class="num">${metricText(inValue, primaryUnit)}</td>
      <td class="num">${metricText(oosValue, primaryUnit)}</td>
      <td class="num">${metricText(fold.oos_metrics?.calmar, '')}</td>
      <td class="num">${metricText(fold.oos_metrics?.sharpe, '')}</td>
      <td class="num">${metricText(fold.oos_metrics?.max_drawdown_pct, '%')}</td>
    </tr>`;
  }).join('');
}

function blindCard(data) {
  const blind = data.locked?.blind;
  if (!blind) {
    return '<div class="blind-card"><b>最终锁定盲测</b><div class="note">数据不足，未生成最终盲测。</div></div>';
  }
  const metrics = blind.metrics || {};
  return `<div class="blind-card">
    <div class="blind-title">最终锁定盲测 <span class="bt-tag stop">未参与选参</span></div>
    <div class="blind-meta">${blind.start} ~ ${blind.end} · K=${fmt(blind.k, 2)} · 止损=${fmt(blind.stop_loss, 1)}% · 实际间距=${fmt(blind.gap_pct, 2)}%</div>
    <div class="blind-metrics">
      <div><span>已实现年化</span><b>${metricText(metrics.realized_annual_pct, '%')}</b></div>
      <div><span>总权益年化</span><b>${metricText(metrics.total_annual_pct, '%')}</b></div>
      <div><span>Calmar</span><b>${metricText(metrics.calmar, '')}</b></div>
      <div><span>Sharpe</span><b>${metricText(metrics.sharpe, '')}</b></div>
      <div><span>Sortino</span><b>${metricText(metrics.sortino, '')}</b></div>
      <div><span>最大回撤</span><b>${metricText(metrics.max_drawdown_pct, '%')}</b></div>
    </div>
  </div>`;
}

export function renderIntradayHeatmap(data, container) {
  if (!data || !data.cells || !data.cells.length) {
    container.innerHTML = '<div class="note">暂无 5 分钟参数高原结果。</div>';
    return;
  }
  const context = data.context;
  const summary = data.summary;
  const primaryMetric = data.config?.primary_metric || 'realized_annual_pct';
  const primaryUnit = PERCENT_METRICS.has(primaryMetric) ? '%' : '';
  const lockedK = data.locked?.k ?? data.k_values[0];
  const charts = METRICS.map(([key, label, unit]) => lineChart(key, label, unit, data, lockedK)).join('');
  const stability = data.parameter_stability;
  const stabilityText = stability.k_values.map((k, index) =>
    `<span class="stability-chip">K ${fmt(k, 2)} / 止损 ${fmt(stability.stop_losses[index], 1)}%</span>`
  ).join('');

  container.innerHTML = `
    <div class="intraday-context">
      <div><span>股票</span><b>${context.name || ''} ${context.code}</b></div>
      <div><span>日线 ATR(14)</span><b>${fmt(context.atr_pct, 2)}%</b></div>
      <div><span>参考区间</span><b>${fmt(context.range_lower, 2)} ~ ${fmt(context.range_upper, 2)}</b></div>
      <div><span>5 分钟数据</span><b>${context.data_start} ~ ${context.data_end}（${context.bar_count} 根）</b></div>
    </div>
    <div class="intraday-summary">
      累计样本外 <b>${fmt(summary.oos_coverage_months, 1)} 个月</b> ·
      ${summary.fold_count} 个窗口 ·
      正收益窗口 <b>${fmt(summary.positive_oos_ratio * 100, 0)}%</b> ·
      主指标均值 <b>${metricText(summary.oos_primary_mean, primaryUnit)}</b> ·
      最差 <b>${metricText(summary.oos_primary_worst, primaryUnit)}</b>
    </div>
    <div class="intraday-grid">${charts}</div>
    <details class="intraday-details" open>
      <summary>滚动样本外验证</summary>
      <div class="table-scroll">
        <table class="intraday-table">
          <thead><tr><th>#</th><th>样本内</th><th>样本外</th><th>K</th><th>止损</th><th>样本内主指标</th><th>OOS 主指标</th><th>OOS Calmar</th><th>OOS Sharpe</th><th>OOS 最大回撤</th></tr></thead>
          <tbody>${foldRows(data, primaryMetric)}</tbody>
        </table>
      </div>
    </details>
    <details class="intraday-details">
      <summary>参数稳定性（选中 K / 止损，变化 ${stability.change_count} 次）</summary>
      <div class="stability-list">${stabilityText}</div>
    </details>
    ${blindCard(data)}
    <div class="note">每个指标一张 K 曲线，止损用不同颜色线；红色虚线为锁定 K。盲测段未参与任何选参。</div>
  `;
}
