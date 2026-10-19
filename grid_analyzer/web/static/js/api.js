const SUPPORTED_SCHEMA_VERSION = 2;

async function requestJson(url, fallbackMessage) {
  const res = await fetch(url);
  const json = await res.json();
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
  return requestJson(`/api/analyze?${params.toString()}`, '分析失败，请稍后重试');
}

export async function fetchHeatmap({
  code,
  capital,
  fee,
  minfee,
  metric,
  gapScales,
  stopLosses,
  initPositions,
}) {
  const params = new URLSearchParams({
    code,
    capital,
    fee,
    min_fee: minfee,
    metric,
    gap_scales: gapScales,
    stop_losses: stopLosses,
    init_positions: initPositions,
  });
  return requestJson(`/api/heatmap?${params.toString()}`, '热力图计算失败，请稍后重试');
}
