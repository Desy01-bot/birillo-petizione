(function () {
  const canvas = document.getElementById('signaturesChart');
  const dataEl = document.getElementById('dailyStats');
  if (!canvas || !dataEl) return;

  const stats = JSON.parse(dataEl.textContent);
  const ctx = canvas.getContext('2d');
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  canvas.width = rect.width * dpr;
  canvas.height = rect.height * dpr;
  ctx.scale(dpr, dpr);

  const css = getComputedStyle(document.documentElement);
  const accent = css.getPropertyValue('--accent').trim() || '#e66b2e';
  const accentDark = css.getPropertyValue('--accent-dark').trim() || '#b94616';
  const border = css.getPropertyValue('--border').trim() || '#f1c9ad';
  const muted = css.getPropertyValue('--muted').trim() || '#76655d';

  const width = rect.width;
  const height = rect.height;
  const padding = 28;
  const values = stats.values || [];
  const labels = stats.labels || [];
  const max = Math.max(1, ...values);
  const chartW = width - padding * 2;
  const chartH = height - padding * 2;

  ctx.clearRect(0, 0, width, height);
  ctx.lineWidth = 1;
  ctx.strokeStyle = border;
  ctx.beginPath();
  ctx.moveTo(padding, padding);
  ctx.lineTo(padding, height - padding);
  ctx.lineTo(width - padding, height - padding);
  ctx.stroke();

  if (values.length === 0) return;

  const step = values.length > 1 ? chartW / (values.length - 1) : chartW;
  ctx.lineWidth = 3;
  ctx.strokeStyle = accent;
  ctx.beginPath();
  values.forEach((value, index) => {
    const x = padding + index * step;
    const y = height - padding - (value / max) * chartH;
    if (index === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();

  ctx.fillStyle = accentDark;
  values.forEach((value, index) => {
    const x = padding + index * step;
    const y = height - padding - (value / max) * chartH;
    ctx.beginPath();
    ctx.arc(x, y, 3.5, 0, Math.PI * 2);
    ctx.fill();
  });

  ctx.fillStyle = muted;
  ctx.font = '12px system-ui, sans-serif';
  ctx.fillText('0', 6, height - padding + 4);
  ctx.fillText(String(max), 6, padding + 4);
  if (labels.length) {
    ctx.fillText(labels[0].slice(5), padding, height - 6);
    ctx.fillText(labels[labels.length - 1].slice(5), width - padding - 34, height - 6);
  }
})();
