// Two small SVG charts, built as strings. No library.
//  curve(): value against cumulative share of the group, one line per group,
//           a mark for the chosen percentile and one for "you".
//  history(): one threshold over the years.
// Colours come from CSS classes, never inline, so both themes work.

const NS = "http://www.w3.org/2000/svg";
const W = 720, H = 320, PAD = { l: 64, r: 20, t: 16, b: 40 };

function scaleLinear(d0, d1, r0, r1) { const k = (r1 - r0) / ((d1 - d0) || 1); return (x) => r0 + (x - d0) * k; }
function scaleLog(d0, d1, r0, r1) { const l0 = Math.log(d0), l1 = Math.log(d1); const k = (r1 - r0) / ((l1 - l0) || 1); return (x) => r0 + (Math.log(x) - l0) * k; }
function niceTicks(d0, d1, n = 5) {
  const span = d1 - d0 || 1; const step0 = span / n; const mag = Math.pow(10, Math.floor(Math.log10(step0)));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => span / s <= n) || mag * 10;
  const out = []; for (let v = Math.ceil(d0 / step) * step; v <= d1 + 1e-9; v += step) out.push(v); return out;
}
function logTicks(d0, d1) {
  const out = []; for (let e = Math.floor(Math.log10(d0)); e <= Math.ceil(Math.log10(d1)); e++) for (const m of [1, 2, 5]) { const v = m * Math.pow(10, e); if (v >= d0 && v <= d1) out.push(v); } return out;
}
function esc(s) { return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;"); }

// series: [{ name, points: [[share0to1, value], ...], cls }]
// marks: [{ share, value, label, cls }]
export function curve(el, { series, marks, fmt, log, xLabel, yLabel }) {
  // On a log scale, points at or below zero cannot be drawn; drop them rather than
  // falling back to a linear scale that flattens everything else.
  if (log) series = series.map((s) => ({ ...s, points: s.points.filter((p) => p[1] > 0) })).filter((s) => s.points.length > 1);
  if (log) marks = marks.filter((m) => m.value == null || m.value > 0);
  const all = series.flatMap((s) => s.points.map((p) => p[1]));
  let y0 = Math.min(...all), y1 = Math.max(...all);
  for (const m of marks) { if (m.value != null) { y0 = Math.min(y0, m.value); y1 = Math.max(y1, m.value); } }
  const useLog = log && y0 > 0;
  if (!useLog) { const padv = (y1 - y0) * 0.06 || 1; y0 -= padv; y1 += padv; } else { y0 /= 1.15; y1 *= 1.15; }
  const x = scaleLinear(0, 1, PAD.l, W - PAD.r);
  const y = useLog ? scaleLog(y0, y1, H - PAD.b, PAD.t) : scaleLinear(y0, y1, H - PAD.b, PAD.t);
  const yt = useLog ? logTicks(y0, y1) : niceTicks(y0, y1, 5);
  const xt = [0, 0.25, 0.5, 0.75, 0.9, 0.99];
  let g = `<svg xmlns="${NS}" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(xLabel)}">`;
  g += `<g class="grid">` + yt.map((v) => `<line x1="${PAD.l}" x2="${W - PAD.r}" y1="${y(v).toFixed(1)}" y2="${y(v).toFixed(1)}"/>`).join("") + `</g>`;
  g += `<line class="baseline" x1="${PAD.l}" x2="${W - PAD.r}" y1="${H - PAD.b}" y2="${H - PAD.b}"/>`;
  g += `<g class="axis">` + yt.map((v) => `<text x="${PAD.l - 8}" y="${(y(v) + 4).toFixed(1)}" text-anchor="end">${esc(fmt(v, true))}</text>`).join("");
  g += xt.map((s) => `<text x="${x(s).toFixed(1)}" y="${H - PAD.b + 16}" text-anchor="${s === 0 ? "start" : s >= 0.99 ? "end" : "middle"}">${s === 0 ? "0%" : Math.round(s * 100) + "%"}</text>`).join("");
  g += `<text x="${W - PAD.r}" y="${H - 6}" text-anchor="end">${esc(xLabel)}</text>`;
  g += `<text x="${PAD.l}" y="${PAD.t - 4}" text-anchor="start">${esc(yLabel)}</text></g>`;
  series.forEach((s, i) => {
    const pts = s.points.slice().sort((a, b) => a[0] - b[0]);
    const d = pts.map((p, j) => `${j ? "L" : "M"}${x(p[0]).toFixed(1)},${y(p[1]).toFixed(1)}`).join(" ");
    g += `<path class="line ${s.cls || ""}" d="${d}"/>`;
  });
  for (const m of marks) {
    if (m.value == null || m.share == null) continue;
    const cx = x(m.share), cy = y(Math.min(Math.max(m.value, useLog ? y0 : -Infinity), y1));
    const anchor = m.share > 0.7 ? "end" : "start", dx = m.share > 0.7 ? -12 : 12;
    g += `<circle class="mark-ring" cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="8"/><circle class="${m.cls}" cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="5.5"/>`;
    g += `<text class="mark-label ${m.cls === "mark-you" ? "you" : ""}" x="${(cx + dx).toFixed(1)}" y="${(cy - 10).toFixed(1)}" text-anchor="${anchor}">${esc(m.label)}</text>`;
  }
  g += `<rect class="hit" x="${PAD.l}" y="${PAD.t}" width="${W - PAD.l - PAD.r}" height="${H - PAD.t - PAD.b}" fill="transparent"/></svg>`;
  el.innerHTML = g;
  attachHover(el, series, fmt, x);
}

function attachHover(el, series, fmt, x) {
  const svg = el.querySelector("svg"), tip = document.getElementById("tip");
  if (!svg || !tip) return;
  const pts = series[0].points.slice().sort((a, b) => a[0] - b[0]);
  const inv = (px) => (px - PAD.l) / (W - PAD.l - PAD.r);
  svg.addEventListener("mousemove", (e) => {
    const r = svg.getBoundingClientRect();
    const share = inv((e.clientX - r.left) * (W / r.width));
    if (share < 0 || share > 1) { tip.hidden = true; return; }
    let best = pts[0];
    for (const p of pts) if (Math.abs(p[0] - share) < Math.abs(best[0] - share)) best = p;
    const others = series.slice(1).map((s) => { const q = s.points.find((p) => p[0] === best[0]); return q ? `<br>${esc(s.name)}: <b>${esc(fmt(q[1]))}</b>` : ""; }).join("");
    tip.innerHTML = `${Math.round(best[0] * 100)}% of ${esc(series[0].name)} are at or below <b>${esc(fmt(best[1]))}</b>${others}`;
    tip.hidden = false;
    tip.style.left = `${Math.min(e.clientX + 14, window.innerWidth - 280)}px`;
    tip.style.top = `${e.clientY + 14}px`;
  });
  svg.addEventListener("mouseleave", () => { tip.hidden = true; });
}

// points: [[year, value]]
export function history(el, { points, fmt, label }) {
  const HH = 160, P = { l: 64, r: 20, t: 14, b: 28 };
  const ys = points.map((p) => p[1]); const xs = points.map((p) => p[0]);
  let y0 = Math.min(...ys), y1 = Math.max(...ys); const padv = (y1 - y0) * 0.1 || 1; y0 -= padv; y1 += padv;
  const x = scaleLinear(Math.min(...xs), Math.max(...xs), P.l, W - P.r);
  const y = scaleLinear(y0, y1, HH - P.b, P.t);
  const yt = niceTicks(y0, y1, 3);
  const xt = niceTicks(Math.min(...xs), Math.max(...xs), 6).map(Math.round);
  let g = `<svg xmlns="${NS}" viewBox="0 0 ${W} ${HH}" role="img" aria-label="${esc(label)}">`;
  g += `<g class="grid">` + yt.map((v) => `<line x1="${P.l}" x2="${W - P.r}" y1="${y(v).toFixed(1)}" y2="${y(v).toFixed(1)}"/>`).join("") + `</g>`;
  g += `<g class="axis">` + yt.map((v) => `<text x="${P.l - 8}" y="${(y(v) + 4).toFixed(1)}" text-anchor="end">${esc(fmt(v, true))}</text>`).join("");
  g += xt.map((v) => `<text x="${x(v).toFixed(1)}" y="${HH - 8}" text-anchor="middle">${v}</text>`).join("") + `</g>`;
  g += `<path class="line" d="${points.map((p, j) => `${j ? "L" : "M"}${x(p[0]).toFixed(1)},${y(p[1]).toFixed(1)}`).join(" ")}"/>`;
  const last = points[points.length - 1];
  g += `<circle class="mark-pct" cx="${x(last[0]).toFixed(1)}" cy="${y(last[1]).toFixed(1)}" r="4.5"/></svg>`;
  el.innerHTML = g;
}
