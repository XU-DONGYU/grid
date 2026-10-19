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
  const json = await res.json();
  if (!res.ok || !json.ok) {
    let detail = json.detail;
    if (Array.isArray(detail)) detail = detail.map(x => x.msg).join('；');
    if (typeof detail !== 'string') detail = String(detail || '分析失败，请稍后重试');
    throw new Error(detail);
  }
  return json.data;
}
