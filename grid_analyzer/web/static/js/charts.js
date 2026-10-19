import { $ } from './dom.js';
import { fmt } from './format.js';

// ---- 价格走势图：主/辅网格图层开关 ----
// 底图（120日走势线 / 中轴 / 坐标轴 / 现价）始终绘制；主网格与辅助网格各自是独立图层，可点击开关显隐
const layerState = { main: true, aux: true };
let _chartData = null;   // 缓存最近一次绘图数据，切换图层时直接重绘，无需重新请求
export function toggleLayer(key){
  layerState[key] = !layerState[key];
  syncLayerUI();
  if(_chartData) drawChart(_chartData);
}
export function syncLayerUI(){
  const bm = document.getElementById('layer-main');
  const ba = document.getElementById('layer-aux');
  if(!bm || !ba) return;
  const single = _chartData ? _chartData.params.single_grid : false;
  bm.classList.toggle('on-main', layerState.main);
  bm.classList.toggle('off', !layerState.main);
  ba.classList.toggle('on-aux', layerState.aux);
  ba.classList.toggle('off', !layerState.aux);
  ba.disabled = !!single;
  ba.style.display = single ? 'none' : '';
}

export function drawEquityChart(d){
  const b = d.backtest, single = d.params.single_grid;
  const series = [];
  if(b.main && b.main.equity_curve && b.main.equity_curve.length){
    series.push({name:'主网格', color:'#1a56db', bt:b.main});
  }
  if(!single && b.aux && b.aux.equity_curve && b.aux.equity_curve.length){
    series.push({name:'辅助网格', color:'#c2700c', bt:b.aux});
  }
  if(!series.length){ $('equity-chart').innerHTML = ''; return; }
  const W=860, H=230, L=58, R=62, T=20, B=28;
  const iw=W-L-R, ih=H-T-B;
  const n = Math.max(...series.map(s=>s.bt.equity_curve.length));
  const capOf = s => d.params.capital * (s.name==='主网格' ? (single ? 1 : d.params.main_ratio) : (1 - d.params.main_ratio));
  const pctOf = (s,i) => {
    const pt = s.bt.equity_curve[Math.min(i, s.bt.equity_curve.length-1)];
    const capital = capOf(s);
    return capital ? (pt.equity/capital - 1)*100 : 0;
  };
  let lo=0, hi=0;
  series.forEach(s=>{
    s.bt.equity_curve.forEach((_,i)=>{ const v=pctOf(s,i); lo=Math.min(lo,v); hi=Math.max(hi,v); });
  });
  const range = Math.max(hi-lo, 0.5); lo-=range*0.12; hi+=range*0.12;
  const X = i => L + iw * (n<=1?0:i/(n-1));
  const Y = v => T + ih * (1 - (v-lo)/(hi-lo));
  const lineFor = s => s.bt.equity_curve.map((_,i)=>`${i?'L':'M'}${X(i).toFixed(1)},${Y(pctOf(s,i)).toFixed(1)}`).join(' ');
  let yTicks='';
  for(let i=0;i<=4;i++){
    const v = lo + (hi-lo)*i/4, y=Y(v);
    yTicks += `<line x1="${L}" x2="${W-R}" y1="${y}" y2="${y}" stroke="#eef1f6"/>
      <text x="${L-7}" y="${y+3.5}" font-size="10" fill="#8b93a1" text-anchor="end">${v>=0?'+':''}${fmt(v,1)}%</text>`;
  }
  const zeroY = Y(0);
  const dates = series[0].bt.equity_curve.map(x=>x.date);
  let xTicks='';
  [0,Math.floor((n-1)/2),n-1].filter((v,i,a)=>a.indexOf(v)===i).forEach(i=>{
    const anchor = i===n-1?'end':i===0?'start':'middle';
    xTicks += `<text x="${X(i)}" y="${H-9}" font-size="10" fill="#8b93a1" text-anchor="${anchor}">${(dates[i]||'').slice(2,7)}</text>`;
  });
  let stopLines='';
  series.forEach(s=>{
    if(s.bt.stop_triggered && s.bt.stop_date){
      const idx = dates.indexOf(s.bt.stop_date);
      if(idx>=0) stopLines += `<line x1="${X(idx)}" x2="${X(idx)}" y1="${T}" y2="${T+ih}" stroke="#d93026" stroke-width="1" stroke-dasharray="4 4" opacity=".55"/>`;
    }
  });
  const paths = series.map(s=>`<path d="${lineFor(s)}" fill="none" stroke="${s.color}" stroke-width="1.8"/>`).join('');
  const ends = series.map(s=>{
    const i=s.bt.equity_curve.length-1, v=pctOf(s,i);
    return `<text x="${W-R+6}" y="${Y(v)+3.5}" font-size="10" fill="${s.color}" font-weight="600">${v>=0?'+':''}${fmt(v,1)}%</text>`;
  }).join('');
  const legend = series.map(s=>`<span><i style="background:${s.color}"></i>${s.name}（${s.bt.return_pct>=0?'+':''}${fmt(s.bt.return_pct)}%）</span>`).join('');
  $('equity-chart').innerHTML = `<div class="equity-box">
    <div class="equity-head"><b style="color:var(--text)">权益曲线（相对初始资金）</b><div class="equity-legend">${legend}</div></div>
    <svg viewBox="0 0 ${W} ${H}" style="min-width:640px">
      ${yTicks}${xTicks}
      <line x1="${L}" x2="${W-R}" y1="${zeroY}" y2="${zeroY}" stroke="#b9c2d1" stroke-width="1"/>
      ${stopLines}${paths}${ends}
    </svg>
  </div>`;
}

export function drawChart(d){
  _chartData = d;
  const data = d.kline_tail, price = d.quote.price;
  const single = d.params.single_grid;
  const W=860, H=380, L=52, R=116, T=18, B=34;
  const iw = W-L-R, ih = H-T-B;
  const g1 = d.main_grid, g2 = d.aux_grid;
  // 图层开关：主网格 / 辅助网格（辅助网格仅主网格模式下无数据）
  const showMain = layerState.main;
  const showAux = !single && layerState.aux;
  // 标签列位置：两层都开时主网格在最右列、辅助网格在中间列；只开一层时该层标签移最右列
  const mainLX = W-R+112, auxLX = (showMain && showAux) ? W-R+56 : W-R+112;
  let lo = Math.min(...data.map(x=>x.close), g1.lower, single ? price : g2.lower, price);
  let hi = Math.max(...data.map(x=>x.close), g1.upper, single ? price : g2.upper, price);
  const pad = (hi-lo)*0.06; lo-=pad; hi+=pad;
  const X = i => L + iw * i/(data.length-1);
  const Y = p => T + ih * (1 - (p-lo)/(hi-lo));
  const line = data.map((x,i)=>`${i?'L':'M'}${X(i).toFixed(1)},${Y(x.close).toFixed(1)}`).join(' ');

  const band = (l, u, color) => {
    const y1=Y(u), y2=Y(l);
    return `<rect x="${L}" y="${y1}" width="${iw}" height="${Math.max(1,y2-y1)}" fill="${color}" stroke="none"/>`;
  };
  // 右侧价格标签：最右列=主网格（蓝），中间列=辅助网格（橙）
  // 碰撞检测：只与同列标签避让（X 已错开 56px，不同列 Y 重叠也不影响视觉）
  // 同列 Y 距离 < 11px 视为相邻重叠，跳过；< 5px 视为完全遮挡，跳过
  const placed = { main: [], aux: [] };
  const tryPlace = (y, col) => {
    for (const y2 of placed[col]) {
      if (Math.abs(y2 - y) < 5) return false; // 完全重叠
      if (Math.abs(y2 - y) < 11) return false; // 同行相邻
    }
    return true;
  };
  let gridLines = '';
  // 只画可买档位（最高档只挂卖不买入，不画虚线/标签，与网格参数卡「档位数量」保持一致；同时色带上边缘不再有线）
  if(showMain) g1.levels.slice(0, -1).forEach(p => {
    const y = Y(p);
    const line = `<line x1="${L}" x2="${W-R}" y1="${y}" y2="${y}" stroke="#7ba0e8" stroke-width="0.7" stroke-dasharray="4 4" opacity="0.8"/>`;
    if (tryPlace(y, 'main')) {
      placed.main.push(y);
      gridLines += line +
        `<text x="${mainLX}" y="${y+3.5}" font-size="9.5" fill="#4a6fb5" text-anchor="end">${fmt(p)}</text>`;
    } else {
      gridLines += line;
    }
  });
  if(showAux) g2.levels.slice(0, -1).forEach(p => {
    const y = Y(p);
    const line = `<line x1="${L}" x2="${W-R}" y1="${y}" y2="${y}" stroke="#d9a441" stroke-width="0.7" stroke-dasharray="2 4" opacity="0.7"/>`;
    if (tryPlace(y, 'aux')) {
      placed.aux.push(y);
      gridLines += line +
        `<text x="${auxLX}" y="${y+3.5}" font-size="9.5" fill="#c2700c" text-anchor="end">${fmt(p)}</text>`;
    } else {
      gridLines += line;
    }
  });
  // 双列列头（跟随图层开关）
  const colHeads =
    (showMain ? `<text x="${mainLX}" y="${T+4}" font-size="9.5" fill="#4a6fb5" text-anchor="end" font-weight="600">主网格</text>` : '') +
    (showAux ? `<text x="${auxLX}" y="${T+4}" font-size="9.5" fill="#c2700c" text-anchor="end" font-weight="600">辅网格</text>` : '');
  const midY = Y(d.axis.recommended);
  let xTicks = '';
  // x轴标签：固定5个位置，最后一个必须是最近交易日（避免右侧空白误以为过期）
  const n = data.length;
  const positions = [0, Math.floor(n/4), Math.floor(n/2), Math.floor(3*n/4), n-1].filter((v,i,a)=>a.indexOf(v)===i);
  positions.forEach(i => {
    const label = (i===n-1) ? data[i].date.slice(2) : data[i].date.slice(2,7);
    const anchor = (i===n-1 ? 'end' : i===0 ? 'start' : 'middle');
    xTicks += `<text x="${X(i)}" y="${H-10}" font-size="10" fill="#8b93a1" text-anchor="${anchor}">${label}</text>`;
  });
  let yTicks = '';
  const step = (hi-lo)/5;
  for(let i=0;i<=5;i++){
    const p = lo + step*i, y = Y(p);
    yTicks += `<line x1="${L-4}" x2="${W-R}" y1="${y}" y2="${y}" stroke="#eef1f6" stroke-width="1"/>
      <text x="${L-7}" y="${y+3.5}" font-size="10" fill="#8b93a1" text-anchor="end">${fmt(p)}</text>`;
  }
  const lastX = X(data.length-1), priceY = Y(price);
  $('chart').innerHTML = `<svg viewBox="0 0 ${W} ${H}">
    ${showMain ? band(g1.lower,g1.upper,'#eaf1fd') : ''}${showAux ? band(g2.lower,g2.upper,'#fdf6e8') : ''}
    ${yTicks}${xTicks}
    ${gridLines}${colHeads}
    <line x1="${L}" x2="${W-R}" y1="${midY}" y2="${midY}" stroke="#d93026" stroke-width="1.4" stroke-dasharray="7 4"/>
    <text x="${L+6}" y="${midY-5}" font-size="11" fill="#d93026" font-weight="600">中轴 ${fmt(d.axis.recommended)}</text>
    <path d="${line}" fill="none" stroke="#1a56db" stroke-width="1.8"/>
    <circle cx="${lastX}" cy="${priceY}" r="4" fill="#d93026" stroke="#fff" stroke-width="1.5"/>
    <text x="${Math.min(lastX-8,W-150)}" y="${priceY-8}" font-size="11" fill="#d93026" font-weight="700" text-anchor="end">现价 ${fmt(price)}（${data[data.length-1].date.slice(5)}）</text>
  </svg>`;
}
