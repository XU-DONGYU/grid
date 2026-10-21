import { $ } from './dom.js';
import {
  analyzeMarket,
  createIntradayHeatmapJob,
  fetchIntradayHeatmapJob,
  fetchPlateau,
} from './api.js';
import { render } from './render.js';
import { toggleLayer } from './charts.js';
import { renderIntradayHeatmap } from './intraday_heatmap.js';
import { renderPlateau, updatePolicyComparison } from './plateau.js';

const LS_KEY = 'grid_analyzer_input';

function saveInputs() {
  try {
    localStorage.setItem(LS_KEY, JSON.stringify({
      code: $('code').value,
      capital: $('capital').value,
      fee: $('fee').value,
      minfee: $('minfee').value,
      ratio: $('ratio').value,
      single: $('single').checked,
      initpos: $('initpos').value,
      stoploss: $('stoploss').value,
      hmKStart: $('heatmap-k-start').value,
      hmKEnd: $('heatmap-k-end').value,
      hmKStep: $('heatmap-k-step').value,
      hmStop: $('heatmap-stop-losses').value,
      hmMetric: $('heatmap-metric').value,
      hmWindow: $('heatmap-window-days').value,
      hmRatio: $('heatmap-in-sample-ratio').value,
      hmBlind: $('heatmap-final-blind-days').value,
      hmMinOos: $('heatmap-min-oos-days').value,
      hmHistory: $('heatmap-history-days').value,
      plMode: $('plateau-mode').value,
      plAnchorPolicy: $('plateau-anchor-policy').value,
      plBandLower: $('plateau-band-lower').value,
      plBandUpper: $('plateau-band-upper').value,
      plKStart: $('plateau-k-start').value,
      plKEnd: $('plateau-k-end').value,
      plKStep: $('plateau-k-step').value,
      plGridAmount: $('plateau-grid-amount').value,
      plMaxPositions: $('plateau-max-positions').value,
      plWindow: $('plateau-window').value,
      plSpread: $('plateau-spread').value,
      plSlippage: $('plateau-slippage').value,
      plLotSize: $('plateau-lot-size').value,
      plPriceLimit: $('plateau-price-limit').value,
      plStopLoss: $('plateau-stop-loss').value,
      plRestartCooldown: $('plateau-restart-cooldown').value,
      plCompare: $('plateau-compare').checked,
      plMinLoops: $('plateau-min-loops').value,
      plOpenLossPenalty: $('plateau-open-loss-penalty').value,
      plHoldoutRatio: $('plateau-holdout-ratio').value,
      plIslandRatio: $('plateau-island-ratio').value,
      plFrontRunOffset: $('plateau-front-run-offset').value,
      plHistory: $('plateau-history-days').value,
    }));
  } catch (e) {
    // localStorage may be unavailable in private mode.
  }
}

function syncSingleUI() {
  $('ratio').disabled = $('single').checked;
}

function restoreInputs() {
  try {
    const saved = JSON.parse(localStorage.getItem(LS_KEY) || 'null');
    if (!saved) return;
    if (saved.code) $('code').value = saved.code;
    if (saved.capital) $('capital').value = saved.capital;
    if (saved.fee !== undefined && saved.fee !== '') $('fee').value = saved.fee;
    if (saved.minfee !== undefined && saved.minfee !== '') $('minfee').value = saved.minfee;
    if (saved.ratio) $('ratio').value = saved.ratio;
    if (saved.single) $('single').checked = saved.single;
    if (saved.initpos !== undefined && saved.initpos !== '') $('initpos').value = saved.initpos;
    if (saved.stoploss !== undefined && saved.stoploss !== '') $('stoploss').value = saved.stoploss;
    if (saved.hmKStart !== undefined && saved.hmKStart !== '') $('heatmap-k-start').value = saved.hmKStart;
    if (saved.hmKEnd !== undefined && saved.hmKEnd !== '') $('heatmap-k-end').value = saved.hmKEnd;
    if (saved.hmKStep !== undefined && saved.hmKStep !== '') $('heatmap-k-step').value = saved.hmKStep;
    if (saved.hmStop !== undefined && saved.hmStop !== '') $('heatmap-stop-losses').value = saved.hmStop;
    if (saved.hmMetric) {
      const metricOptions = Array.from($('heatmap-metric').options).map(option => option.value);
      if (metricOptions.includes(saved.hmMetric)) $('heatmap-metric').value = saved.hmMetric;
    }
    if (saved.hmWindow !== undefined && saved.hmWindow !== '') $('heatmap-window-days').value = saved.hmWindow;
    if (saved.hmRatio !== undefined && saved.hmRatio !== '') $('heatmap-in-sample-ratio').value = saved.hmRatio;
    if (saved.hmBlind !== undefined && saved.hmBlind !== '') $('heatmap-final-blind-days').value = saved.hmBlind;
    if (saved.hmMinOos !== undefined && saved.hmMinOos !== '') $('heatmap-min-oos-days').value = saved.hmMinOos;
    if (saved.hmHistory !== undefined && saved.hmHistory !== '') $('heatmap-history-days').value = saved.hmHistory;
    if (saved.plMode) {
      const modeOptions = Array.from($('plateau-mode').options).map(option => option.value);
      if (modeOptions.includes(saved.plMode)) $('plateau-mode').value = saved.plMode;
    }
    if (saved.plAnchorPolicy) {
      const anchorOptions = Array.from($('plateau-anchor-policy').options).map(option => option.value);
      if (anchorOptions.includes(saved.plAnchorPolicy)) $('plateau-anchor-policy').value = saved.plAnchorPolicy;
    }
    if (saved.plBandLower !== undefined) $('plateau-band-lower').value = saved.plBandLower;
    if (saved.plBandUpper !== undefined) $('plateau-band-upper').value = saved.plBandUpper;
    if (saved.plKStart !== undefined && saved.plKStart !== '') $('plateau-k-start').value = saved.plKStart;
    if (saved.plKEnd !== undefined && saved.plKEnd !== '') $('plateau-k-end').value = saved.plKEnd;
    if (saved.plKStep !== undefined && saved.plKStep !== '') $('plateau-k-step').value = saved.plKStep;
    if (saved.plGridAmount !== undefined && saved.plGridAmount !== '') $('plateau-grid-amount').value = saved.plGridAmount;
    if (saved.plMaxPositions !== undefined && saved.plMaxPositions !== '') $('plateau-max-positions').value = saved.plMaxPositions;
    if (saved.plWindow !== undefined && saved.plWindow !== '') $('plateau-window').value = saved.plWindow;
    if (saved.plSpread !== undefined && saved.plSpread !== '') $('plateau-spread').value = saved.plSpread;
    if (saved.plSlippage !== undefined && saved.plSlippage !== '') $('plateau-slippage').value = saved.plSlippage;
    if (saved.plLotSize !== undefined && saved.plLotSize !== '') $('plateau-lot-size').value = saved.plLotSize;
    if (saved.plPriceLimit !== undefined && saved.plPriceLimit !== '') $('plateau-price-limit').value = saved.plPriceLimit;
    if (saved.plStopLoss !== undefined && saved.plStopLoss !== '') $('plateau-stop-loss').value = saved.plStopLoss;
    if (saved.plRestartCooldown !== undefined && saved.plRestartCooldown !== '') $('plateau-restart-cooldown').value = saved.plRestartCooldown;
    if (saved.plCompare !== undefined) $('plateau-compare').checked = Boolean(saved.plCompare);
    if (saved.plMinLoops !== undefined && saved.plMinLoops !== '') $('plateau-min-loops').value = saved.plMinLoops;
    if (saved.plOpenLossPenalty !== undefined && saved.plOpenLossPenalty !== '') $('plateau-open-loss-penalty').value = saved.plOpenLossPenalty;
    if (saved.plHoldoutRatio !== undefined && saved.plHoldoutRatio !== '') $('plateau-holdout-ratio').value = saved.plHoldoutRatio;
    if (saved.plIslandRatio !== undefined && saved.plIslandRatio !== '') $('plateau-island-ratio').value = saved.plIslandRatio;
    if (saved.plFrontRunOffset !== undefined && saved.plFrontRunOffset !== '') $('plateau-front-run-offset').value = saved.plFrontRunOffset;
    if (saved.plHistory !== undefined && saved.plHistory !== '') $('plateau-history-days').value = saved.plHistory;
    syncSingleUI();
  } catch (e) {
    // Ignore malformed or unavailable local storage.
  }
}

function showError(msg) {
  $('err').textContent = msg;
  $('err').style.display = 'block';
  $('loading').style.display = 'none';
}

async function analyze() {
  const code = $('code').value.trim();
  if (!code) {
    showError('请输入股票代码');
    return;
  }
  const capital = parseFloat($('capital').value) || 100000;
  const fee = parseFloat($('fee').value);
  const minfee = Math.max(0, parseFloat($('minfee').value) || 0);
  const single = $('single').checked;
  const ratio = single ? 1.0 : (parseFloat($('ratio').value) || 0.7);
  const initpos = Math.min(100, Math.max(0, parseFloat($('initpos').value) || 0)) / 100;
  const stoploss = Math.min(50, Math.max(0, parseFloat($('stoploss').value) || 0));

  saveInputs();
  $('heatmap-wrap').innerHTML = '';
  $('heatmap-status').textContent = '';
  $('err').style.display = 'none';
  $('result').style.display = 'none';
  $('loading').style.display = 'block';
  $('btn').disabled = true;
  try {
    const data = await analyzeMarket({ code, capital, fee, minfee, ratio, initpos, stoploss });
    render(data);
    $('result').style.display = 'block';
  } catch (e) {
    showError(e.message);
  } finally {
    $('loading').style.display = 'none';
    $('btn').disabled = false;
  }
}

function parseNumberList(value, name) {
  const items = value.split(',').map(item => item.trim()).filter(Boolean).map(Number);
  if (!items.length || items.some(item => !Number.isFinite(item))) {
    throw new Error(`${name} 需要逗号分隔的数字`);
  }
  return items;
}

async function generateHeatmap() {
  const code = $('code').value.trim();
  if (!code) {
    $('heatmap-status').textContent = '请先输入股票代码';
    return;
  }
  const capital = parseFloat($('capital').value) || 100000;
  const fee = parseFloat($('fee').value) || 0;
  const minfee = Math.max(0, parseFloat($('minfee').value) || 0);
  const metric = $('heatmap-metric').value;
  const initPosition = Math.min(100, Math.max(0, parseFloat($('initpos').value) || 0)) / 100;

  let stopLosses;
  let kStart;
  let kEnd;
  let kStep;
  try {
    stopLosses = parseNumberList($('heatmap-stop-losses').value, '破网止损');
    kStart = parseFloat($('heatmap-k-start').value);
    kEnd = parseFloat($('heatmap-k-end').value);
    kStep = parseFloat($('heatmap-k-step').value);
    if ([kStart, kEnd, kStep].some(value => !Number.isFinite(value))) throw new Error('K 范围需要有效数字');
    if (kStart <= 0 || kEnd <= kStart || kStep <= 0) throw new Error('K 范围必须满足 0 < 起点 < 终点，步长 > 0');
    if (stopLosses.some(item => item < 0)) throw new Error('破网止损不能为负');
  } catch (e) {
    $('heatmap-status').textContent = e.message;
    return;
  }

  const ratioPercent = Math.min(90, Math.max(10, parseFloat($('heatmap-in-sample-ratio').value) || 70));
  const windowDays = Math.max(10, parseInt($('heatmap-window-days').value, 10) || 126);
  const finalBlindDays = Math.max(0, parseInt($('heatmap-final-blind-days').value, 10) || 0);
  const minOosDays = Math.max(0, parseInt($('heatmap-min-oos-days').value, 10) || 0);
  const historyDays = Math.max(60, parseInt($('heatmap-history-days').value, 10) || 500);

  saveInputs();
  $('heatmap-btn').disabled = true;
  $('heatmap-status').textContent = '任务已提交，正在拉取数据…';
  $('heatmap-wrap').innerHTML = '';
  try {
    const job = await createIntradayHeatmapJob({
      code,
      capital,
      fee,
      min_fee: minfee,
      init_position: initPosition,
      stop_losses: stopLosses,
      k_start: kStart,
      k_end: kEnd,
      k_step: kStep,
      window_days: windowDays,
      in_sample_ratio: ratioPercent / 100,
      final_blind_days: finalBlindDays,
      min_oos_days: minOosDays,
      primary_metric: metric,
      history_days: historyDays,
    });
    const started = Date.now();
    while (true) {
      await sleep(2000);
      const status = await fetchIntradayHeatmapJob(job.job_id);
      const elapsed = Math.round((Date.now() - started) / 1000);
      if (status.status === 'completed') {
        renderIntradayHeatmap(status.result, $('heatmap-wrap'));
        $('heatmap-status').textContent = `计算完成（${elapsed}s）`;
        break;
      }
      if (status.status === 'failed') {
        throw new Error(status.error || '计算失败');
      }
      $('heatmap-status').textContent = `计算中… 已等待 ${elapsed}s`;
      if (elapsed > 300) throw new Error('计算超时，请稍后重试或缩小参数范围');
    }
  } catch (e) {
    $('heatmap-status').textContent = e.message;
  } finally {
    $('heatmap-btn').disabled = false;
  }
}

const ANCHOR_POLICIES = ['fixed', 'fixed_band', 'periodic', 'daily_roll'];

function plateauRowFromResult(policy, data) {
  const plateau = data.plateau;
  const holdout = data.holdout || {};
  const summary = data.summary || {};
  let note = null;
  if (!plateau) note = '未识别到合规高原';
  else if (!plateau.profitable) note = '合规高原没有正选参值';
  else if (summary.plateau_at_right_edge) note = '高原顶到 k 右边界';
  return {
    anchor_policy: policy,
    status: 'ok',
    error: null,
    k_left: plateau?.k_left ?? null,
    k_right: plateau?.k_right ?? null,
    k_star: plateau?.k_star ?? null,
    profitable: plateau?.profitable ?? null,
    in_sample_net_return_pct: plateau?.k_star_net_return_pct ?? null,
    in_sample_capital_return_pct: plateau?.k_star_capital_return_pct ?? null,
    holdout_net_return_pct: holdout.net_return_pct ?? null,
    holdout_positive: holdout.positive ?? null,
    live_d_exec_pct: data.live?.d_exec_pct ?? null,
    stop_count: plateau?.k_star_stop_count ?? null,
    restart_count: plateau?.k_star_restart_count ?? null,
    plateau_at_right_edge: summary.plateau_at_right_edge ?? null,
    plateau_at_safe_boundary: summary.plateau_at_safe_boundary ?? null,
    note,
  };
}

function failedPolicyRow(policy, error) {
  return {
    anchor_policy: policy,
    status: 'error',
    error: error?.message || String(error),
    k_left: null,
    k_right: null,
    k_star: null,
    profitable: null,
    in_sample_net_return_pct: null,
    in_sample_capital_return_pct: null,
    holdout_net_return_pct: null,
    holdout_positive: null,
    live_d_exec_pct: null,
    stop_count: null,
    restart_count: null,
    plateau_at_right_edge: null,
    plateau_at_safe_boundary: null,
    note: '该策略计算失败',
  };
}

async function loadPolicyComparison(payload, mainData, container) {
  const rows = [plateauRowFromResult(payload.anchor_policy, mainData)];
  updatePolicyComparison(rows, payload.anchor_policy, container);
  let done = 1;
  for (const policy of ANCHOR_POLICIES) {
    if (policy === payload.anchor_policy) continue;
    $('plateau-status').textContent = `图表已生成，正在对照锚定策略 ${done + 1}/4…`;
    try {
      const compared = await fetchPlateau({
        ...payload,
        anchor_policy: policy,
        compare_anchor_policies: false,
      });
      rows.push(plateauRowFromResult(policy, compared));
    } catch (error) {
      rows.push(failedPolicyRow(policy, error));
    }
    done += 1;
    updatePolicyComparison(rows, payload.anchor_policy, container);
  }
  $('plateau-status').textContent = '计算完成：已生成四种锚定策略对照表';
}

async function generatePlateau() {
  const code = $('code').value.trim();
  if (!code) {
    $('plateau-status').textContent = '请先输入股票代码';
    return;
  }
  const fee = parseFloat($('fee').value) || 0;
  const minfee = Math.max(0, parseFloat($('minfee').value) || 0);
  const gridAmount = Math.max(100, parseFloat($('plateau-grid-amount').value) || 10000);
  const maxPositions = Math.min(50, Math.max(1, parseInt($('plateau-max-positions').value, 10) || 8));
  const spread = Math.max(0, parseFloat($('plateau-spread').value) || 0);
  const slippage = Math.max(0, parseFloat($('plateau-slippage').value) || 0);
  const lotSize = Math.max(0, parseInt($('plateau-lot-size').value, 10) || 0);
  const priceLimit = Math.max(0, parseFloat($('plateau-price-limit').value) || 0);
  const stopLoss = Math.max(0, parseFloat($('plateau-stop-loss').value) || 0);
  const restartCooldown = Math.max(0, parseInt($('plateau-restart-cooldown').value, 10) || 0);
  const comparePolicies = $('plateau-compare').checked;
  const minLoops = Math.max(0, parseInt($('plateau-min-loops').value, 10) || 0);
  const openLossPenalty = Math.max(0, parseFloat($('plateau-open-loss-penalty').value) || 0.5);
  const holdoutValue = parseFloat($('plateau-holdout-ratio').value);
  const holdoutRatio = (Number.isFinite(holdoutValue) ? Math.min(80, Math.max(0, holdoutValue)) : 30) / 100;
  const islandRatio = Math.max(0, parseFloat($('plateau-island-ratio').value) || 0.25);
  const frontRunOffset = Math.max(0, parseFloat($('plateau-front-run-offset').value) || 0.2);
  const historyDays = Math.max(60, parseInt($('plateau-history-days').value, 10) || 500);
  const kStart = parseFloat($('plateau-k-start').value);
  const kEnd = parseFloat($('plateau-k-end').value);
  const kStep = parseFloat($('plateau-k-step').value);
  const windowPoints = Math.max(2, parseInt($('plateau-window').value, 10) || 5);
  if ([kStart, kEnd, kStep].some(value => !Number.isFinite(value))) {
    $('plateau-status').textContent = 'k 范围需要有效数字';
    return;
  }
  if (kStart <= 0 || kEnd <= kStart || kStep <= 0) {
    $('plateau-status').textContent = 'k 范围必须满足 0 < 起点 < 终点，步长 > 0';
    return;
  }
  const bandLowerText = $('plateau-band-lower').value.trim();
  const bandUpperText = $('plateau-band-upper').value.trim();
  const bandLower = bandLowerText ? Number(bandLowerText) : null;
  const bandUpper = bandUpperText ? Number(bandUpperText) : null;
  if ((bandLower === null) !== (bandUpper === null)) {
    $('plateau-status').textContent = '区间下限和上限必须同时填写，或同时留空使用自动区间';
    return;
  }
  if (bandLower !== null && (!Number.isFinite(bandLower) || !Number.isFinite(bandUpper) || bandLower <= 0 || bandUpper <= bandLower)) {
    $('plateau-status').textContent = '手动区间必须满足 0 < 下限 < 上限';
    return;
  }

  saveInputs();
  $('plateau-btn').disabled = true;
  $('plateau-status').textContent = comparePolicies
    ? '正在计算主策略图表，完成后再自动对照其余策略…'
    : '正在拉取 5 分钟数据并扫描 k 曲线…';
  $('plateau-wrap').innerHTML = '';
  const payload = {
    code,
    grid_amount: gridAmount,
    max_positions: maxPositions,
    lot_size: lotSize,
    fee,
    min_fee: minfee,
    spread_pct: spread,
    slippage_pct: slippage,
    price_limit_pct: priceLimit,
    stop_loss_pct: stopLoss,
    restart_cooldown_days: restartCooldown,
    compare_anchor_policies: false,
    min_loops: minLoops,
    open_loss_penalty: openLossPenalty,
    holdout_ratio: holdoutRatio,
    k_start: kStart,
    k_end: kEnd,
    k_step: kStep,
    mode: $('plateau-mode').value,
    anchor_policy: $('plateau-anchor-policy').value,
    band_lower: bandLower,
    band_upper: bandUpper,
    plateau_window: windowPoints,
    island_drop_ratio: islandRatio,
    front_run_offset_pct: frontRunOffset,
    history_days: historyDays,
  };
  try {
    const data = await fetchPlateau(payload);
    renderPlateau(data, $('plateau-wrap'));
    $('plateau-status').textContent = `主策略完成：${data.k_values.length} 个 k 值`;
    if (comparePolicies) {
      await loadPolicyComparison(payload, data, $('plateau-wrap'));
    }
  } catch (e) {
    $('plateau-status').textContent = e.message;
  } finally {
    $('plateau-btn').disabled = false;
  }
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function initParamTips() {
  const tip = document.createElement('div');
  tip.id = 'param-tip';
  document.body.appendChild(tip);
  let current = null;

  const hide = () => {
    tip.classList.remove('show', 'above');
    current = null;
  };

  const show = (element) => {
    const text = element.dataset.tip;
    if (!text) return;
    tip.textContent = text;
    tip.classList.add('show');
    const rect = element.getBoundingClientRect();
    const width = Math.min(340, window.innerWidth - 24);
    tip.style.maxWidth = `${width}px`;
    const left = Math.min(Math.max(12, rect.left), window.innerWidth - width - 12);
    tip.style.left = `${left}px`;
    tip.style.top = `${rect.bottom + 8}px`;
    const tipRect = tip.getBoundingClientRect();
    if (rect.bottom + 8 + tipRect.height > window.innerHeight - 12) {
      tip.classList.add('above');
      tip.style.top = `${Math.max(8, rect.top - tipRect.height - 8)}px`;
    } else {
      tip.classList.remove('above');
    }
    current = element;
  };

  document.addEventListener('click', event => {
    const target = event.target.closest?.('.param-label');
    if (target) {
      event.preventDefault();
      event.stopPropagation();
      if (current === target) {
        hide();
      } else {
        show(target);
      }
      return;
    }
    if (!event.target.closest?.('#param-tip')) hide();
  });
  document.addEventListener('keydown', event => { if (event.key === 'Escape') hide(); });
  window.addEventListener('scroll', hide, { passive: true });
  window.addEventListener('resize', hide);
}

function initToc() {
  const ids = ['p-stock', 'p-axis', 'p-grid', 'p-chart', 'p-bt', 'p-heatmap', 'p-plateau', 'p-risk'];
  const links = Array.from(document.querySelectorAll('#toc a'));
  const secs = ids.map(id => document.getElementById(id)).filter(Boolean);
  if (!('IntersectionObserver' in window)) return;
  const obs = new IntersectionObserver(entries => {
    entries.forEach(e => {
      if (e.isIntersecting) {
        links.forEach(a => a.classList.toggle('active', a.getAttribute('href') === '#' + e.target.id));
      }
    });
  }, { rootMargin: '-12% 0px -72% 0px' });
  secs.forEach(s => obs.observe(s));
}

$('btn').onclick = analyze;
$('code').addEventListener('keydown', e => { if (e.key === 'Enter') analyze(); });
$('single').addEventListener('change', syncSingleUI);
$('layer-main').addEventListener('click', () => toggleLayer('main'));
$('layer-aux').addEventListener('click', () => toggleLayer('aux'));
$('heatmap-btn').addEventListener('click', generateHeatmap);
$('plateau-btn').addEventListener('click', generatePlateau);

restoreInputs();
initParamTips();
initToc();
if (!$('code').value) $('code').value = '600000';
window.addEventListener('load', () => analyze());
