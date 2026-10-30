document.addEventListener('DOMContentLoaded', () => {
  const dataNode = document.getElementById('attendance-chart-data');
  if (!dataNode) return;
  const data = JSON.parse(dataNode.textContent || '{}');
  const teal = '#53d6ca';
  const slate = '#496881';
  const grid = 'rgba(157,188,218,.10)';
  const muted = '#7f9ab0';
  const trend = document.getElementById('trend-chart');
  const trendEmpty = document.querySelector('[data-empty="trend"]');
  const drawTrend = () => {
    if (!trend || !data.labels?.length) {
      if (trendEmpty) trendEmpty.style.display = 'block';
      return;
    }
    const ctx = trend.getContext('2d');
    const width = trend.clientWidth || 560;
    const height = 220;
    const dpr = window.devicePixelRatio || 1;
    trend.width = width * dpr; trend.height = height * dpr; ctx.scale(dpr, dpr);
    const left = 34, right = width - 10, top = 15, bottom = height - 28;
    const values = [...(data.present || []), ...(data.absent || [])];
    const max = Math.max(...values, 1);
    const plotX = (index) => left + ((right - left) * (data.labels.length === 1 ? .5 : index / (data.labels.length - 1)));
    const plotY = (value) => bottom - ((bottom - top) * value / max);
    ctx.font = '10px system-ui';
    ctx.strokeStyle = grid; ctx.lineWidth = 1;
    for (let step = 0; step <= 3; step += 1) {
      const y = top + ((bottom - top) * step / 3);
      ctx.beginPath(); ctx.moveTo(left, y); ctx.lineTo(right, y); ctx.stroke();
      ctx.fillStyle = muted; ctx.textAlign = 'right'; ctx.fillText(String(Math.round(max - (max * step / 3))), left - 7, y + 3);
    }
    const drawLine = (series, color) => {
      ctx.beginPath();
      series.forEach((value, index) => { const x = plotX(index), y = plotY(value); index ? ctx.lineTo(x, y) : ctx.moveTo(x, y); });
      ctx.strokeStyle = color; ctx.lineWidth = 2; ctx.stroke();
      series.forEach((value, index) => { ctx.beginPath(); ctx.fillStyle = color; ctx.arc(plotX(index), plotY(value), 3, 0, Math.PI * 2); ctx.fill(); });
    };
    drawLine(data.present || [], teal); drawLine(data.absent || [], slate);
    ctx.fillStyle = muted; ctx.textAlign = 'center';
    data.labels.forEach((label, index) => ctx.fillText(label, plotX(index), height - 7));
  };
  drawTrend();
  window.addEventListener('resize', drawTrend);

  const distribution = document.getElementById('distribution-chart');
  if (distribution) {
    const ctx = distribution.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    distribution.width = 190 * dpr; distribution.height = 190 * dpr; ctx.scale(dpr, dpr);
    const present = Number(data.today_present || 0), absent = Number(data.today_absent || 0), total = present + absent;
    const center = 95, radius = 71;
    ctx.lineWidth = 16; ctx.lineCap = 'round'; ctx.beginPath(); ctx.strokeStyle = 'rgba(157,188,218,.10)'; ctx.arc(center, center, radius, 0, Math.PI * 2); ctx.stroke();
    if (total) { const angle = Math.PI * 2 * present / total; ctx.beginPath(); ctx.strokeStyle = teal; ctx.arc(center, center, radius, -Math.PI / 2, -Math.PI / 2 + angle); ctx.stroke(); }
  }
});
