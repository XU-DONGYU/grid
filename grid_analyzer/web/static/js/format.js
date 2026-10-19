export const fmt = (n, d=2) => {
  const x = Number(n);
  if (!Number.isFinite(x)) return '—';
  return x.toLocaleString('zh-CN', {minimumFractionDigits:d, maximumFractionDigits:d});
};
export const pctOrDash = (n, d=1) => Number.isFinite(Number(n)) ? fmt(n, d)+'%' : '—';
export const fmtWan = n => {
  const sign = n < 0 ? '-' : '';
  const a = Math.abs(n);
  return a >= 1e8 ? sign+(a/1e8).toFixed(2)+' 亿' : a >= 1e4 ? sign+(a/1e4).toFixed(2)+' 万' : sign+fmt(a,0);
};
export const pctCls = v => v > 0 ? 'up' : v < 0 ? 'down' : '';
