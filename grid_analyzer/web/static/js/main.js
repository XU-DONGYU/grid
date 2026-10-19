import { $ } from './dom.js';
import { analyzeMarket, fetchHeatmap } from './api.js';
import { render } from './render.js';
import { toggleLayer } from './charts.js';
import { renderHeatmap } from './heatmap.js';

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
      hmGap: $('heatmap-gap-scales').value,
      hmStop: $('heatmap-stop-losses').value,
      hmInit: $('heatmap-init-positions').value,
      hmMetric: $('heatmap-metric').value,
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
    if (saved.hmGap !== undefined && saved.hmGap !== '') $('heatmap-gap-scales').value = saved.hmGap;
    if (saved.hmStop !== undefined && saved.hmStop !== '') $('heatmap-stop-losses').value = saved.hmStop;
    if (saved.hmInit !== undefined && saved.hmInit !== '') $('heatmap-init-positions').value = saved.hmInit;
    if (saved.hmMetric) $('heatmap-metric').value = saved.hmMetric;
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

  let gapScales;
  let stopLosses;
  let initPositions;
  try {
    gapScales = parseNumberList($('heatmap-gap-scales').value, '格距缩放');
    stopLosses = parseNumberList($('heatmap-stop-losses').value, '破网止损');
    const initPct = parseNumberList($('heatmap-init-positions').value, '初始底仓');
    if (gapScales.some(item => item <= 0)) throw new Error('格距缩放必须大于 0');
    if (stopLosses.some(item => item < 0)) throw new Error('破网止损不能为负');
    if (initPct.some(item => item < 0 || item > 100)) throw new Error('初始底仓需在 0~100 之间');
    initPositions = initPct.map(item => item / 100);
  } catch (e) {
    $('heatmap-status').textContent = e.message;
    return;
  }

  saveInputs();
  $('heatmap-btn').disabled = true;
  $('heatmap-status').textContent = '正在计算参数热力图，请稍候…';
  try {
    const data = await fetchHeatmap({
      code,
      capital,
      fee,
      minfee,
      metric,
      gapScales: gapScales.join(','),
      stopLosses: stopLosses.join(','),
      initPositions: initPositions.join(','),
    });
    renderHeatmap(data, $('heatmap-wrap'));
    $('heatmap-status').textContent = '计算完成';
  } catch (e) {
    $('heatmap-status').textContent = e.message;
    $('heatmap-wrap').innerHTML = '';
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
