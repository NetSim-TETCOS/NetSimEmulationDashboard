export function drawLineChart(canvas, series, markers = [], options = {}) {
  const dpr = window.devicePixelRatio || 1;
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  if (!width || !height) return;
  canvas.width = width * dpr;
  canvas.height = height * dpr;
  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);
  const pad = { left: 44, right: 14, top: 15, bottom: 28 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  const points = series.flatMap(item => item.points || []);
  const now = Date.now();
  const since = options.since || (now - 60000);
  const visible = points.filter(p => p.x >= since);
  const values = visible.map(p => Number(p.y)).filter(Number.isFinite);
  const dataMin = values.length ? Math.min(...values) : 0;
  const dataMax = values.length ? Math.max(...values) : (options.minMaxY || 10);
  const dataSpan = Math.max(0.5, dataMax - dataMin);
  const padding = Math.max(0.5, dataSpan * 0.18);
  const minY = Math.max(0, dataMin - padding);
  const maxY = Math.max(minY + 1, dataMax + padding);
  ctx.clearRect(0, 0, width, height);
  ctx.font = '11px system-ui';
  ctx.fillStyle = '#91a7bd';
  ctx.strokeStyle = '#243b55';
  ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const y = pad.top + plotH * i / 4;
    ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(width - pad.right, y); ctx.stroke();
    const value = minY + (maxY - minY) * (1 - i / 4);
    ctx.fillText(`${Math.round(value)} ms`, 2, y + 4);
  }
  if (options.baseline != null) {
    const y = pad.top + plotH * (1 - (options.baseline - minY) / (maxY - minY));
    ctx.strokeStyle = '#ffbf5b'; ctx.setLineDash([5, 4]);
    ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(width - pad.right, y); ctx.stroke();
    ctx.setLineDash([]);
  }
  const range = Math.max(1, now - since);
  markers.filter(m => Date.parse(m.timestamp) >= since).forEach(marker => {
    const x = pad.left + ((Date.parse(marker.timestamp) - since) / range) * plotW;
    ctx.strokeStyle = '#ffbf5b'; ctx.globalAlpha = .65;
    ctx.beginPath(); ctx.moveTo(x, pad.top); ctx.lineTo(x, pad.top + plotH); ctx.stroke(); ctx.globalAlpha = 1;
  });
  series.forEach((item, index) => {
    const line = (item.points || []).filter(p => p.x >= since);
    if (!line.length) return;
    ctx.strokeStyle = item.color || ['#37d6c0', '#62a8ff', '#ff6b7a'][index % 3];
    ctx.lineWidth = 2; ctx.beginPath();
    line.forEach((point, i) => {
      const x = pad.left + ((point.x - since) / range) * plotW;
      const y = pad.top + plotH * (1 - (point.y - minY) / (maxY - minY));
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    });
    ctx.stroke();
  });
  const legend = series.filter(item => item.points?.length);
  let legendX = pad.left;
  legend.forEach((item, index) => {
    const label = item.label || (index === 0 ? 'Median RTT' : `Series ${index + 1}`);
    ctx.fillStyle = item.color || '#37d6c0'; ctx.fillRect(legendX, 3, 18, 3);
    ctx.fillStyle = '#bac8d6'; ctx.fillText(label, legendX + 23, 8);
    legendX += Math.min(220, ctx.measureText(label).width + 42);
  });
  ctx.fillStyle = '#91a7bd';
  ctx.fillText(new Date(since).toLocaleTimeString(), pad.left, height - 7);
  const end = new Date(now).toLocaleTimeString();
  ctx.fillText(end, width - pad.right - ctx.measureText(end).width, height - 7);
}
