import { $ } from './dom.js';
import { analyzeMarket, fetchIntradayHeatmap } from './api.js';
import { render } from './render.js';
import { toggleLayer } from './charts.js';
import { renderIntradayHeatmap } from './intraday_heatmap.js';

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
  $('heatmap-status').textContent = '正在拉取数据并执行滚动验证，可能需要几十秒…';
  $('heatmap-wrap').innerHTML = '';
  try {
    const data = await fetchIntradayHeatmap({
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
    renderIntradayHeatmap(data, $('heatmap-wrap'));
    $('heatmap-status').textContent = '计算完成';
  } catch (e) {
    $('heatmap-status').textContent = e.message;
  } finally {
    $('heatmap-btn').disabled = false;
  }
}

function initToc() {
  const ids = ['p-stock', 'p-axis', 'p-grid', 'p-chart', 'p-bt', 'p-heatmap', 'p-risk'];
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

restoreInputs();
initToc();
if (!$('code').value) $('code').value = '600000';
window.addEventListener('load', () => analyze());
