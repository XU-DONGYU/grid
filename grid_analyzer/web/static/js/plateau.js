import { fmt } from './format.js';

const NET_COLOR = '#1a56db';
const LOOP_COLOR = '#c2700c';
const PRIOR_COLOR = '#2f6fe0';
const PLATEAU_COLOR = '#0a8a4a';
const ISLAND_COLOR = '#d93026';
const STAR_COLOR = '#d4a017';

const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
}[ch]));

const pct = (value, digits = 2) => Number.isFinite(Number(value)) ? `${fmt(value, digits)}%` : '—';
const num = (value, digits = 2) => Number.isFinite(Number(value)) ? fmt(value, digits) : '—';

function ticks(low, high, count = 5) {
  if (!Number.isFinite(low) || !Number.isFinite(high)) return [];
  if (low === high) return [low];
  return Array.from({ length: count }, (_, index) => low + (high - low) * index / (count - 1));
}

function starPoints(cx, cy, outer = 9, inner = 4) {
  const points = [];
  for (let index = 0; index < 10; index += 1) {
    const radius = index % 2 === 0 ? outer : inner;
    const angle = -Math.PI / 2 + index * Math.PI / 5;
    points.push(`${(cx + radius * Math.cos(angle)).toFixed(1)},${(cy + radius * Math.sin(angle)).toFixed(1)}`);
  }
  return points.join(' ');
}

function chart(data) {
  const curve = data.curve || [];
  if (!curve.length) return '<div class="note">没有可绘制的 k 曲线。</div>';
  const ks = curve.map(point => Number(point.k));
  const netValues = curve.map(point => Number(point.net_return_pct));
  const loops = curve.map(point => Number(point.loops));
  const kMin = Math.min(...ks);
  const kMax = Math.max(...ks);
  let netLow = Math.min(0, ...netValues);
  let netHigh = Math.max(0, ...netValues);
  if (netLow === netHigh) {
    netLow -= 1;
    netHigh += 1;
  }
  const netPad = (netHigh - netLow) * 0.12;
  netLow -= netPad;
  netHigh += netPad;
  const loopHigh = Math.max(1, ...loops) * 1.12;

  const W = 960, H = 440, L = 72, R = 70, T = 32, B = 54;
  const iw = W - L - R;
  const ih = H - T - B;
  const x = k => L + (k - kMin) / (kMax - kMin || 1) * iw;
  const yNet = value => T + ih * (1 - (value - netLow) / (netHigh - netLow || 1));
  const yLoop = value => T + ih * (1 - value / (loopHigh || 1));

  const netPath = curve.map((point, index) =>
    `${index === 0 ? 'M' : 'L'}${x(Number(point.k)).toFixed(1)},${yNet(Number(point.net_return_pct)).toFixed(1)}`
  ).join(' ');
  const loopPath = curve.map((point, index) =>
    `${index === 0 ? 'M' : 'L'}${x(Number(point.k)).toFixed(1)},${yLoop(Number(point.loops)).toFixed(1)}`
  ).join(' ');

  const netTicks = ticks(netLow, netHigh, 5).map(value =>
    `<line x1="${L}" x2="${W - R}" y1="${yNet(value)}" y2="${yNet(value)}" stroke="#eef1f6"/>`
    + `<text x="${L - 8}" y="${yNet(value) + 3.5}" font-size="10" fill="#8b93a1" text-anchor="end">${fmt(value, 1)}%</text>`
  ).join('');
  const loopTicks = ticks(0, loopHigh, 5).map(value =>
    `<text x="${W - R + 8}" y="${yLoop(value) + 3.5}" font-size="10" fill="#8b93a1" text-anchor="start">${fmt(value, 0)}</text>`
  ).join('');

  const tickStep = (kMax - kMin) > 1.6 ? 0.2 : 0.1;
  const xTicks = [];
  for (let k = Math.ceil(kMin / tickStep) * tickStep; k <= kMax + 1e-9; k += tickStep) {
    const value = Number(k.toFixed(2));
    xTicks.push(
      `<line x1="${x(value)}" x2="${x(value)}" y1="${T + ih}" y2="${T + ih + 4}" stroke="#c3ccda"/>`
      + `<text x="${x(value)}" y="${H - 14}" font-size="10" fill="#8b93a1" text-anchor="middle">${fmt(value, 2)}</text>`
    );
  }

  const safeK = Number(data.summary?.k_min_safe);
  const forbiddenWidth = Number.isFinite(safeK) ? Math.max(0, Math.min(kMax, safeK) - kMin) : 0;
  const forbidden = forbiddenWidth > 0
    ? `<rect x="${x(kMin)}" y="${T}" width="${(x(kMin + forbiddenWidth) - x(kMin)).toFixed(1)}" height="${ih}" fill="${ISLAND_COLOR}" opacity=".08"/>`
      + `<text x="${(x(kMin) + x(kMin + forbiddenWidth)) / 2}" y="${T + 16}" font-size="10" fill="${ISLAND_COLOR}" text-anchor="middle">手续费磨损禁区</text>`
    : '';

  const priorLeft = Number(data.prior_validation?.prior_left ?? 0.65);
  const priorRight = Number(data.prior_validation?.prior_right ?? 0.80);
  const priorAnchor = Number(data.prior_validation?.prior_anchor ?? 0.70);
  const priorDrawLeft = Math.max(kMin, priorLeft);
  const priorDrawRight = Math.min(kMax, priorRight);
  const priorBand = priorDrawRight > priorDrawLeft
    ? `<rect x="${x(priorDrawLeft)}" y="${T}" width="${Math.max(0, x(priorDrawRight) - x(priorDrawLeft))}" height="${ih}" fill="${PRIOR_COLOR}" opacity=".10"/>`
    : '';
  const priorLine = priorAnchor >= kMin && priorAnchor <= kMax
    ? `<line x1="${x(priorAnchor)}" x2="${x(priorAnchor)}" y1="${T}" y2="${T + ih}" stroke="${PRIOR_COLOR}" stroke-width="1.4" stroke-dasharray="6 4"/>`
      + `<text x="${x(priorAnchor) + 4}" y="${T + 16}" font-size="10" fill="${PRIOR_COLOR}">0.7×ATR 理论锚定线</text>`
    : '';
  const prior = priorBand + priorLine;

  const plateau = data.plateau;
  const plateauColor = plateau && plateau.profitable ? PLATEAU_COLOR : '#6b7280';
  const plateauBand = plateau
    ? `<rect x="${x(plateau.k_left)}" y="${T}" width="${Math.max(0, x(plateau.k_right) - x(plateau.k_left))}" height="${ih}" fill="${plateauColor}" opacity=".14"/>`
      + `<text x="${(x(plateau.k_left) + x(plateau.k_right)) / 2}" y="${T + ih - 8}" font-size="10" fill="${plateauColor}" text-anchor="middle">${plateau.profitable ? '实测参数高原' : '候选高原（未通过收益/浮亏筛选）'} ${fmt(plateau.k_left, 2)}–${fmt(plateau.k_right, 2)}</text>`
    : '';

  const islandMarks = (data.islands || []).map(island => {
    const cx = x(Number(island.k));
    const cy = yNet(Number(island.net_return_pct));
    return `<rect x="${cx - 9}" y="${cy - 13}" width="18" height="26" fill="none" stroke="${ISLAND_COLOR}" stroke-width="1.2" stroke-dasharray="3 3"/>`
      + `<text x="${cx}" y="${cy - 17}" font-size="9" fill="${ISLAND_COLOR}" text-anchor="middle">孤岛</text>`;
  }).join('');

  const points = curve.map(point => {
    const cx = x(Number(point.k));
    const cy = yNet(Number(point.net_return_pct));
    const color = point.is_island ? ISLAND_COLOR : point.is_optimal ? STAR_COLOR : NET_COLOR;
    return `<circle cx="${cx}" cy="${cy}" r="${point.is_optimal ? 4 : 2.6}" fill="${color}">`
      + `<title>k=${fmt(point.k, 2)}，净收益 ${pct(point.net_return_pct)}，闭环 ${fmt(point.loops, 0)} 次，期末浮盈亏 ${pct(point.open_position_pnl_pct)}</title>`
      + '</circle>';
  }).join('');

  const optimal = plateau
    ? (() => {
        const point = curve.find(item => Number(item.k) === Number(plateau.k_star));
        if (!point) return '';
        const cx = x(Number(plateau.k_star));
        const cy = yNet(Number(point.net_return_pct));
        const starColor = plateau.profitable ? STAR_COLOR : '#6b7280';
        return `<polygon points="${starPoints(cx, cy)}" fill="${starColor}" stroke="#4b5563" stroke-width="1"/>`
          + `<text x="${cx}" y="${cy - 15}" font-size="10" fill="${starColor}" text-anchor="middle" font-weight="700">k* ${fmt(plateau.k_star, 2)}</text>`;
      })()
    : '';

  return `<div class="plateau-chart">
    <div class="plateau-legend">
      <span><i style="background:${NET_COLOR}"></i>单格累计净收益（左轴）</span>
      <span><i style="background:${LOOP_COLOR}"></i>有效闭环次数 n(k)（右轴）</span>
      <span><i style="background:${PLATEAU_COLOR}"></i>实测高原</span>
      <span><i style="background:${PRIOR_COLOR}"></i>理论先验带</span>
      <span><i style="background:${ISLAND_COLOR}"></i>孤岛/禁区</span>
    </div>
    <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="ATR 归一化参数高原倒 U 型图">
      <text x="${L}" y="${T - 10}" font-size="11" fill="${NET_COLOR}">单格累计净收益 %</text>
      <text x="${W - R}" y="${T - 10}" font-size="11" fill="${LOOP_COLOR}" text-anchor="end">闭环次数</text>
      ${netTicks}${loopTicks}${xTicks.join('')}
      ${forbidden}${prior}${plateauBand}${islandMarks}
      <line x1="${L}" x2="${W - R}" y1="${yNet(0)}" y2="${yNet(0)}" stroke="#9aa4b2" stroke-width="1"/>
      <line x1="${L}" x2="${W - R}" y1="${T + ih}" y2="${T + ih}" stroke="#c3ccda"/>
      <path d="${loopPath}" fill="none" stroke="${LOOP_COLOR}" stroke-width="1.6" stroke-dasharray="5 3" opacity=".9"/>
      <path d="${netPath}" fill="none" stroke="${NET_COLOR}" stroke-width="2.4"/>
      ${points}${optimal}
      <text x="${L + iw / 2}" y="${H - 2}" font-size="10" fill="#8b93a1" text-anchor="middle">ATR 倍数 k（0.05 步进）</text>
    </svg>
  </div>`;
}

const ANCHOR_TEXT = {
  daily_roll: '每日重锚',
  fixed_band: '区间边界重锚',
  fixed: '固定锚点',
  periodic: '周期重锚',
};

function contextCard(data) {
  const context = data.context || {};
  const mode = context.mode === 'static_mean' ? '静态均值' : '动态自适应';
  const anchor = ANCHOR_TEXT[context.anchor_policy] || context.anchor_policy;
  return `<div class="plateau-context">
    <div><span>股票</span><b>${esc(context.name || '')} ${esc(context.code || '')}</b></div>
    <div><span>步长 / 锚定</span><b>${mode} · ${esc(anchor)}</b></div>
    <div><span>固定区间</span><b>${fmt(context.band_lower, 3)} – ${fmt(context.band_upper, 3)} · ${esc({auto: '自动', manual: '手动', fallback: '兜底'}[context.band_source] || context.band_source)}</b></div>
    <div><span>最新 ATR(14)</span><b>${pct(context.latest_atr_pct)}</b></div>
    <div><span>区间日均 ATR%</span><b>${pct(context.mean_atr_pct)}</b></div>
    <div><span>单边佣金 / 最低佣金</span><b>${pct(context.fee, 3)} / ${fmt(context.min_fee, 0)} 元</b></div>
    <div><span>双边摩擦 C%</span><b>${pct(context.friction_pct)}</b></div>
    <div><span>安全底线 k<sub>min</sub></span><b>${num(context.k_min_safe, 3)}</b></div>
    <div><span>最大持仓 / 总资金</span><b>${fmt(context.max_positions, 0)} 格 / ${fmt(context.capital, 0)} 元</b></div>
    <div><span>每格股数 / 滑点 / 涨跌停</span><b>${fmt(context.shares_per_grid, 0)} 股 / ${pct(context.slippage_pct)} / ${pct(context.price_limit_pct)}</b></div>
    <div><span>破网止损 / 重启冷却</span><b>${pct(context.stop_loss_pct)} / ${fmt(context.restart_cooldown_days, 0)} 天</b></div>
    <div><span>最小闭环 / 浮亏惩罚</span><b>${fmt(data.summary?.min_loops, 0)} / ${fmt(data.summary?.open_loss_penalty, 2)}</b></div>
    <div><span>5 分钟数据</span><b>${esc(context.data_start)} ~ ${esc(context.data_end)}（${fmt(context.bar_count, 0)} 根）</b></div>
  </div>`;
}

function summaryCard(data) {
  const summary = data.summary || {};
  const plateau = data.plateau;
  const prior = data.prior_validation || {};
  const plateauText = plateau
    ? `${fmt(plateau.k_left, 2)} – ${fmt(plateau.k_right, 2)}（${plateau.window_points} 点）`
    : '未识别';
  return `<div class="plateau-summary">
    <div><span>参数高原</span><b>${plateauText}</b></div>
    <div><span>最优系数 k*</span><b>${plateau ? fmt(plateau.k_star, 3) : '—'}</b></div>
    <div><span>高原平均单格收益</span><b>${plateau ? pct(plateau.mean_net_return_pct) : '—'}</b></div>
    <div><span>k* 单格 / 总资金收益</span><b>${plateau ? `${pct(plateau.k_star_net_return_pct)} / ${pct(plateau.k_star_capital_return_pct)}` : '—'}</b></div>
    <div><span>k* 闭环 / 最大持仓</span><b>${plateau ? `${fmt(plateau.k_star_loops, 0)} / ${fmt(plateau.k_star_max_positions_used, 0)}` : '—'}</b></div>
    <div><span>剔除孤岛</span><b>${fmt(summary.island_count, 0)} 个</b></div>
    <div><span>先验重合</span><b>${prior.matches ? '是' : '否'}</b></div>
  </div>`;
}

function holdoutCard(data) {
  const holdout = data.holdout || {};
  if (!holdout.enabled) {
    return `<div class="plateau-prior-card">
      <div class="blind-title">留出验证</div>
      <div class="note">${esc(holdout.reason || '未启用留出验证。')}</div>
    </div>`;
  }
  const tag = holdout.positive
    ? '<span class="bt-tag ok">留出段正收益</span>'
    : '<span class="bt-tag stop">留出段未盈利</span>';
  return `<div class="plateau-prior-card">
    <div class="blind-title">留出验证 ${tag}</div>
    <div class="plateau-prior-grid">
      <div><span>样本内区间</span><b>${esc(holdout.in_sample_start)} ~ ${esc(holdout.in_sample_end)}</b></div>
      <div><span>留出区间</span><b>${esc(holdout.oos_start)} ~ ${esc(holdout.oos_end)}</b></div>
      <div><span>锁定 k*</span><b>${fmt(holdout.k_star, 3)}</b></div>
      <div><span>留出净收益</span><b>${pct(holdout.net_return_pct)}</b></div>
      <div><span>占总资金</span><b>${pct(holdout.capital_return_pct)}</b></div>
      <div><span>闭环 / 最大持仓</span><b>${fmt(holdout.loops, 0)} / ${fmt(holdout.max_positions_used, 0)}</b></div>
      <div><span>区间外天数（上/下）</span><b>${fmt(holdout.upper_breakout_days, 0)} / ${fmt(holdout.lower_breakout_days, 0)}</b></div>
    </div>
    <div class="note">留出段只评估样本内选出的 k*，不参与高原选择。</div>
  </div>`;
}

function boundaryWarning(data) {
  const summary = data.summary || {};
  const messages = [];
  if (summary.best_inside_forbidden) {
    messages.push(`原始最优 k=${fmt(summary.raw_best_k, 2)} 落在手续费磨损禁区，说明该标的的历史频率优势不足以覆盖 10 倍成本安全线。`);
  }
  if (summary.plateau_found && !summary.positive_plateau) {
    messages.push('合规高原扣除期末浮亏后没有正选参值，因此不输出实盘步长。');
  }
  if (summary.plateau_at_safe_boundary) {
    messages.push('合规高原贴近安全底线左边缘，实盘应优先观察右移后的高原中心，而不是继续压缩步长。');
  }
  if (summary.plateau_at_right_edge) {
    messages.push('合规高原顶到 k 扫描右边界，真实最优可能更大；请扩大 k 终点后重新扫描。');
  }
  const prior = data.prior_validation || {};
  if (Number.isFinite(Number(summary.k_min_safe)) && Number(prior.prior_right) <= Number(summary.k_min_safe)) {
    messages.push('0.65–0.80 × ATR% 理论先验带整体落在手续费磨损禁区，说明该标的当前波动率相对摩擦成本偏低。');
  }
  if (Number(summary.missing_5m_days) > 0 || Number(summary.incomplete_days) > 0) {
    messages.push(`存在缺失或不完整的 5 分钟交易日（缺失 ${fmt(summary.missing_5m_days, 0)} 天，低 bar 数 ${fmt(summary.incomplete_days, 0)} 天），这些交易日已跳过撮合。`);
  }
  if ((data.curve || []).some(point => Number(point.capital_constrained_buys) > 0)) {
    messages.push('部分档位因现金不足无法买入 100 股而被跳过，请提高总资金。');
  }
  if ((data.curve || []).some(point => Number(point.limit_locked_days) > 0)) {
    messages.push('检测到涨跌停封死日，这些交易日不撮合；阈值可在高级参数中调整。');
  }
  if (!messages.length) return '';
  return `<div class="risk-item">${messages.map(esc).join('<br>')}</div>`;
}

function liveCard(data) {
  const live = data.live;
  if (!live) {
    return `<div class="plateau-live-card warn">
      <b>实盘步长还原</b>
      <div class="note">${esc(data.summary?.live_unavailable_reason || '未生成实盘步长。')}</div>
    </div>`;
  }
  const frontRun = live.front_run || {};
  const adjusted = frontRun.adjusted
    ? `<span class="bt-tag stop">已向下微调 ${pct(frontRun.offset_pct)}</span>`
    : '<span class="bt-tag idle">未触发整数关口修正</span>';
  return `<div class="plateau-live-card">
    <div class="plateau-live-title">从无量纲 k* 还原今日实盘步长 ${adjusted}</div>
    <div class="plateau-conversion">
      <div><span>最优系数 k*</span><b>${fmt(live.k_star, 3)}</b></div>
      <div class="plateau-op">×</div>
      <div><span>当前 ATR%</span><b>${pct(live.latest_atr_pct)}</b></div>
      <div class="plateau-op">=</div>
      <div><span>理论步长 d<sub>raw</sub></span><b>${pct(live.d_raw_pct)}</b></div>
      <div class="plateau-op">→</div>
      <div><span>抢跑修正后 d<sub>exec</sub></span><b class="plateau-em">${pct(live.d_exec_pct)}</b></div>
    </div>
    <div class="plateau-live-meta">
      <span>实际执行系数 k<sub>exec</sub> <b>${fmt(live.k_exec, 3)}</b></span>
      <span>绝对格距 <b>${fmt(live.d_exec_abs, 3)} 元</b></span>
      <span>有效往返成本 <b>${pct(live.effective_friction_pct)}</b></span>
      <span>净边际 <b>${pct(live.net_edge_pct)}</b></span>
      <span>安全底线步长 <b>${pct(live.safe_floor_pct)}</b></span>
    </div>
    ${frontRun.reason ? `<div class="note">${esc(frontRun.reason)}</div>` : ''}
    ${(live.warnings || []).map(item => `<div class="risk-item">${esc(item)}</div>`).join('')}
  </div>`;
}

function breakoutCard(data) {
  const live = data.live;
  if (!live) return '';
  const breakout = live.breakout || {};
  return `<div class="plateau-breakout-card">
    <div class="blind-title">拐点触发（执行建议，不参与回测）</div>
    <div class="plateau-breakout-grid">
      <div><span>灵敏区基础步长</span><b>${pct(breakout.base_step_pct)}</b></div>
      <div><span>反弹买入触发</span><b>${pct(breakout.rebound_buy_pct)}</b></div>
      <div><span>回落卖出触发</span><b>${pct(breakout.pullback_sell_pct)}</b></div>
      <div><span>趋势段拉伸步长</span><b>${pct(breakout.stretch_step_pct)}</b></div>
      <div><span>参考买入价</span><b>${fmt(breakout.buy_trigger_price, 3)} 元</b></div>
      <div><span>参考卖出价</span><b>${fmt(breakout.sell_trigger_price, 3)} 元</b></div>
    </div>
    <div class="note">仅为实盘条件单建议，不参与历史回测；回测只使用基础步长。窄幅震荡用基础步长保留成交频次，单边拉升或下杀时，回落/反弹条件单把有效步长拉伸到 ${pct(breakout.stretch_step_pct)}。</div>
  </div>`;
}

const RELATION_TEXT = {
  inside_prior: '先验区间内',
  below_prior: '低于先验区间',
  above_prior: '高于先验区间',
  no_plateau: '无参数高原',
};

function priorCard(data) {
  const prior = data.prior_validation || {};
  const overlap = prior.overlap_left === null || prior.overlap_left === undefined
    ? '无重合'
    : `${fmt(prior.overlap_left, 2)} – ${fmt(prior.overlap_right, 2)}`;
  return `<div class="plateau-prior-card">
    <div class="blind-title">理论先验交叉验证</div>
    <div class="plateau-prior-grid">
      <div><span>先验区间</span><b>${fmt(prior.prior_left, 2)} – ${fmt(prior.prior_right, 2)} × ATR%</b></div>
      <div><span>核心锚点</span><b>${fmt(prior.prior_anchor, 2)} × ATR%</b></div>
      <div><span>与实测高原重合</span><b>${overlap}</b></div>
      <div><span>k* 相对先验</span><b>${esc(RELATION_TEXT[prior.k_star_relation] || prior.k_star_relation)}</b></div>
    </div>
    ${prior.warning ? `<div class="risk-item">${esc(prior.warning)}</div>` : '<div class="note">实测高原与 0.65–0.80 × ATR% 先验区间重合，参数解释性较好。</div>'}
  </div>`;
}

const POLICY_TEXT = {
  daily_roll: '每日重锚',
  fixed_band: '区间边界重锚',
  fixed: '固定锚点',
  periodic: '周期重锚',
};

function policyRowsMarkup(rows, currentPolicy) {
  const body = rows.map(row => {
    if (row.status === 'error') {
      return `<tr>
        <td>${esc(POLICY_TEXT[row.anchor_policy] || row.anchor_policy)}</td>
        <td colspan="7" class="down">${esc(row.error || '计算失败')}</td>
      </tr>`;
    }
    const plateauText = row.k_left === null || row.k_left === undefined
      ? '未识别'
      : `${fmt(row.k_left, 2)} – ${fmt(row.k_right, 2)}`;
    const status = row.note
      ? `<span class="bt-tag stop">${esc(row.note)}</span>`
      : row.holdout_positive === false
        ? '<span class="bt-tag stop">留出未盈利</span>'
        : '<span class="bt-tag ok">可用</span>';
    return `<tr class="${row.anchor_policy === currentPolicy ? 'now' : ''}">
      <td>${esc(POLICY_TEXT[row.anchor_policy] || row.anchor_policy)}</td>
      <td>${plateauText}</td>
      <td class="num">${row.k_star === null || row.k_star === undefined ? '—' : fmt(row.k_star, 3)}</td>
      <td class="num">${pct(row.in_sample_net_return_pct)}</td>
      <td class="num">${pct(row.holdout_net_return_pct)}</td>
      <td class="num">${pct(row.live_d_exec_pct)}</td>
      <td class="num">${row.stop_count === null || row.stop_count === undefined ? '—' : `${fmt(row.stop_count, 0)} / ${fmt(row.restart_count, 0)}`}</td>
      <td>${status}</td>
    </tr>`;
  }).join('');
  return `<div class="table-scroll">
    <table class="intraday-table" style="min-width:820px">
      <thead><tr><th>策略</th><th>高原</th><th>k*</th><th>样本内收益</th><th>留出收益</th><th>实盘步长</th><th>止损 / 重启</th><th>状态</th></tr></thead>
      <tbody>${body}</tbody>
    </table>
  </div>`;
}

function policyTable(data) {
  const rows = data.policy_comparison || [];
  return `<div class="plateau-prior-card" style="margin-top:12px">
    <div class="blind-title">四种锚定策略自动对照</div>
    <div id="plateau-policy-table">${policyRowsMarkup(rows, data.context?.anchor_policy)}</div>
    <div class="note">fixed 使用完整固定区间阶梯；其余策略为锚点梯子对照。高原在不同策略下越接近，参数越稳健；差异很大时，不应只采用单一策略的 k*。</div>
  </div>`;
}

const POLICY_ORDER = ['fixed', 'fixed_band', 'periodic', 'daily_roll'];

export function updatePolicyComparison(rows, currentPolicy, container) {
  const target = container.querySelector('#plateau-policy-table');
  if (!target) return;
  const sorted = [...rows].sort(
    (left, right) => POLICY_ORDER.indexOf(left.anchor_policy) - POLICY_ORDER.indexOf(right.anchor_policy)
  );
  target.innerHTML = policyRowsMarkup(sorted, currentPolicy);
}

function curveTable(data) {
  const rows = data.curve.map(point => `<tr class="${point.is_optimal ? 'now' : ''}">
    <td class="num">${fmt(point.k, 2)}</td>
    <td class="num">${pct(point.net_return_pct)}</td>
    <td class="num">${pct(point.capital_return_pct)}</td>
    <td class="num">${pct(point.selection_value)}</td>
    <td class="num">${fmt(point.loops, 0)}</td>
    <td class="num">${fmt(point.winning_loops, 0)}</td>
    <td class="num">${pct(point.avg_loop_return_pct)}</td>
    <td class="num">${pct(point.open_position_pnl_pct)}</td>
    <td class="num">${fmt(point.max_positions_used, 0)} / ${fmt(point.max_positions, 0)}</td>
    <td class="num">${fmt(point.stop_count, 0)} / ${fmt(point.restart_count, 0)}</td>
    <td>${point.below_safe ? '手续费禁区' : point.is_island ? '孤岛' : point.is_optimal ? 'k*' : point.in_plateau ? '高原' : ''}</td>
  </tr>`).join('');
  return `<details class="intraday-details">
    <summary>完整 k 扫描明细</summary>
    <div class="table-scroll">
      <table class="intraday-table">
        <thead><tr><th>k</th><th>单格收益</th><th>总资金收益</th><th>选参值</th><th>闭环 n</th><th>盈利闭环</th><th>单次均值</th><th>期末浮盈亏</th><th>最大持仓</th><th>止损/重启</th><th>标记</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  </details>`;
}

export function renderPlateau(data, container) {
  if (!data || !data.curve || !data.curve.length) {
    container.innerHTML = '<div class="note">暂无 ATR 归一化参数高原结果。</div>';
    return;
  }
  container.innerHTML = `
    ${contextCard(data)}
    ${summaryCard(data)}
    ${boundaryWarning(data)}
    ${chart(data)}
    <div class="plateau-cards">
      ${liveCard(data)}
      ${holdoutCard(data)}
      ${breakoutCard(data)}
      ${priorCard(data)}
    </div>
    ${policyTable(data)}
    ${curveTable(data)}
    <div class="note">实验模块：以 k × ATR(14)% 为唯一横轴，使用 0/1 阶跃触线撮合。按所选锚定策略布置阶梯，每格固定 100 股，最多持有 N 个槽位，按格线成交，卖出受 T+1 约束；已处理固定 100 股、总资金上限、滑点、涨跌停锁定和停牌/缺失日。默认前 70% 样本内选参、后 30% 留出验证，选参时对期末浮亏按惩罚系数扣减。结果不构成投资建议，也不替代滚动样本外验证和最终盲测。</div>
  `;
}
