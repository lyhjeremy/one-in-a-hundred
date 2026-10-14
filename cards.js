// Client-side share card (1200 x 630) on a canvas, same composition as
// pipeline/render_cards.py. Used for the where-do-I-land card, which carries
// the visitor's own number and so is never rendered on a server.

function tokens() {
  const cs = getComputedStyle(document.documentElement);
  const t = (n) => cs.getPropertyValue(n).trim();
  return { paper: t("--paper"), panel: t("--panel"), ink: t("--ink"), ink2: t("--ink-2"), rule: t("--rule"), signal: t("--signal"), signal2: t("--signal-2") };
}

function wrap(ctx, text, maxWidth) {
  const words = text.split(" ");
  const lines = [];
  let line = "";
  for (const w of words) {
    const test = line ? `${line} ${w}` : w;
    if (ctx.measureText(test).width > maxWidth && line) { lines.push(line); line = w; } else line = test;
  }
  if (line) lines.push(line);
  return lines;
}

export async function renderCard({ headline, subline, grade, stamp, foot }) {
  await document.fonts.ready;
  const c = document.createElement("canvas");
  c.width = 1200; c.height = 630;
  const ctx = c.getContext("2d");
  const T = tokens();
  ctx.fillStyle = T.paper; ctx.fillRect(0, 0, 1200, 630);
  ctx.fillStyle = T.ink; ctx.fillRect(72, 72, 1056, 2);
  ctx.fillRect(72, 556, 1056, 1);

  ctx.font = '600 22px "IBM Plex Sans", Helvetica, Arial, sans-serif';
  ctx.fillStyle = T.ink2;
  ctx.fillText("ONE IN A HUNDRED", 72, 56);
  if (stamp) {
    ctx.font = '400 22px "IBM Plex Mono", Menlo, monospace';
    ctx.fillStyle = T.signal;
    const w = ctx.measureText(stamp).width;
    ctx.fillText(stamp, 1128 - w, 56);
  }

  let size = 60;
  let lines;
  do {
    ctx.font = `600 ${size}px "Source Serif 4", Palatino, serif`;
    lines = wrap(ctx, headline, 1056);
    size -= 4;
  } while (lines.length > 4 && size > 32);
  ctx.fillStyle = T.ink;
  const lh = (size + 4) * 1.15;
  let y = 140 + (size + 4);
  for (const ln of lines) { ctx.fillText(ln, 72, y); y += lh; }

  ctx.font = '400 26px "IBM Plex Sans", Helvetica, Arial, sans-serif';
  ctx.fillStyle = T.ink2;
  y = Math.max(y + 10, 470);
  for (const ln of wrap(ctx, subline, 1056).slice(0, 2)) { ctx.fillText(ln, 72, y); y += 34; }

  if (grade) {
    ctx.font = '400 22px "IBM Plex Mono", Menlo, monospace';
    const label = `GRADE ${grade}`;
    const w = ctx.measureText(label).width + 24;
    ctx.strokeStyle = T.ink; ctx.lineWidth = 1.5;
    ctx.strokeRect(1128 - w, 574, w, 36);
    ctx.fillStyle = T.ink;
    ctx.fillText(label, 1128 - w + 12, 599);
  }
  ctx.font = '400 20px "IBM Plex Sans", Helvetica, Arial, sans-serif';
  ctx.fillStyle = T.ink2;
  ctx.fillText(foot || "lyhjeremy.github.io/one-in-a-hundred", 72, 599);
  return new Promise((res) => c.toBlob(res, "image/png"));
}
