const SUPPORTED_SCHEMA_VERSION = 2;

async function parseResponse(res, fallbackMessage) {
  const text = await res.text();
  let json;
  try {
    json = JSON.parse(text);
  } catch (error) {
    const contentType = res.headers.get('content-type') || '';
    if (contentType.includes('text/html') || text.trimStart().startsWith('<')) {
      throw new Error(
        `接口返回了 HTML 页面（HTTP ${res.status}）。通常表示后端未重启、/api/plateau 路由不存在，或反向代理返回了错误页。`
        + ' 请先重启 grid.service，并确认反向代理把 /api/ 请求转发到 FastAPI；然后刷新页面重试。'
      );
    }
    throw new Error(`接口返回内容不是合法 JSON（HTTP ${res.status}）：${text.slice(0, 120) || fallbackMessage}`);
  }
  if (!res.ok || !json.ok) {
    let detail = json.detail;
    if (Array.isArray(detail)) detail = detail.map(x => x.msg).join('；');
    if (typeof detail !== 'string') detail = String(detail || fallbackMessage);
    throw new Error(detail);
  }
  if (json.schema_version !== SUPPORTED_SCHEMA_VERSION) {
    throw new Error(`后端 API schema v${json.schema_version} 与前端 v${SUPPORTED_SCHEMA_VERSION} 不兼容`);
  }
  return json.data;
}

export async function analyzeMarket({ code, capital, fee, minfee, ratio, initpos, stoploss }) {
  const params = new URLSearchParams({
    code,
    capital,
    fee,
    min_fee: minfee,
    main_ratio: ratio,
    init_position: initpos,
    stop_loss: stoploss,
  });
  const res = await fetch(`/api/analyze?${params.toString()}`);
  return parseResponse(res, '分析失败，请稍后重试');
}

export async function fetchIntradayHeatmap(payload) {
  const res = await fetch('/api/intraday-heatmap', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return parseResponse(res, '5 分钟参数高原计算失败，请稍后重试');
}

export async function createIntradayHeatmapJob(payload) {
  const res = await fetch('/api/intraday-heatmap/jobs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return parseResponse(res, '创建 5 分钟参数高原任务失败');
}

export async function fetchIntradayHeatmapJob(jobId) {
  const res = await fetch(`/api/intraday-heatmap/jobs/${encodeURIComponent(jobId)}`);
  return parseResponse(res, '查询 5 分钟参数高原任务失败');
}

export async function fetchPlateau(payload) {
  const res = await fetch('/api/plateau', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return parseResponse(res, 'ATR 归一化参数高原计算失败，请稍后重试');
}
