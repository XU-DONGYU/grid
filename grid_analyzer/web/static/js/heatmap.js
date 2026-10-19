import { fmt } from './format.js';

function metricValue(value, metric) {
  return metric === 'plateau_score' ? fmt(value, 2) : fmt(value, 2) + '%';
}

export function renderHeatmap(data, container) {
  if (!data || !data.cells || !data.cells.length) {
    container.innerHTML = '<div class="note">暂无热力图数据，请先完成一次分析或调整参数。</div>';
    return;
  }

  const cellMap = new Map();
  data.cells.forEach(cell => {
    cellMap.set(`${cell.gap_scale}|${cell.stop_loss}`, cell);
  });

  const header = ['<th>止损 \\ 格距</th>']
    .concat(data.gap_scales.map(gap => `<th>${fmt(gap, 2)}</th>`))
    .join('');

  const rows = data.stop_losses.map(stop => {
    const cells = data.gap_scales.map(gap => {
      const cell = cellMap.get(`${gap}|${stop}`);
      if (!cell) return '<td class="hm-empty">—</td>';
      const css = cell.is_best ? 'hm-best' : '';
      const title = `gap_scale=${fmt(gap, 2)}, stop_loss=${fmt(stop, 1)}%, ` +
        `${data.metric_label}=${metricValue(cell.value, data.metric)}，样本数=${cell.count}`;
      return `<td class="${css}" style="background:${cell.color}" title="${title}">` +
        `${metricValue(cell.value, data.metric)}</td>`;
    }).join('');
    return `<tr><th>${fmt(stop, 1)}%</th>${cells}</tr>`;
  }).join('');

  const direction = data.direction === 'lower' ? '越低越好' : '越高越好';
  const best = data.best
    ? `<div class="hint" style="margin-top:10px">最佳参数：格距缩放 ${fmt(data.best.gap_scale, 2)}，止损 ${fmt(data.best.stop_loss, 1)}%，` +
      `${data.metric_label} ${metricValue(data.best.value, data.metric)}（样本 ${data.best.count}）</div>`
    : '';
  const legend = `<div class="hm-legend"><span>${metricValue(data.low, data.metric)}</span>` +
    '<div class="hm-legend-bar"></div>' +
    `<span>${metricValue(data.high, data.metric)}</span></div>`;

  const initText = (data.init_positions || []).map(item => fmt(item * 100, 0) + '%').join(' / ');
  const initPart = initText ? ` · 初始底仓 ${initText}（格内均值）` : '';
  container.innerHTML =
    `<div class="hm-head">${data.name || ''} ${data.code || ''} · ${data.metric_label} · ${direction}${initPart} · ${data.sample_count} 组参数</div>` +
    `<table class="hm-table"><thead><tr>${header}</tr></thead><tbody>${rows}</tbody></table>` +
    legend + best;
}
