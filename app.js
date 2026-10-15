// One in a Hundred v0.3: five modes, one answer. State lives in the URL; data is static.
import { punchline, groupName, formatCount, formatValue, gridKeyFor, COUNTRY_SHORT, ageBandPhrase, sig2 } from "./format.js";
import { parseRules } from "./parser-rules.js";
import { curve, history as historyChart } from "./chart.js";

const $ = (s) => document.querySelector(s);
const PCT_KEYS = ["p50", "p90", "p99"];
const WORKER = null; // Worker origin once deployed (parse + research + queue); null = browser only
const REPO = "https://github.com/lyhjeremy/one-in-a-hundred";
const LS_KEY = "oih.profile";
const DIMS = ["country", "sex", "age_band", "source_category"];
const MODES = ["explore", "ask", "me", "compare", "surprise"];

let M, INDEX, FACTS = {};
const state = { mode: "explore", metric: null, pop: blankPop(), pct: "p99", b: null, v: null };

function blankPop() { return { country: null, sex: "all", age_band: null, activity: null, source_category: null }; }

// ---------- data ----------
async function loadData() {
  const [m, idx, extra] = await Promise.all([
    fetch("data/metrics.json").then((r) => r.json()),
    fetch("data/index.json").then((r) => r.json()),
    fetch("data/metrics_extra.json").then((r) => (r.ok ? r.json() : { metrics: {}, activities: {} })).catch(() => ({ metrics: {}, activities: {} })),
  ]);
  M = m; INDEX = idx;
  M.families.more = M.families.more || { label: "More measures (researched)", order: 9 };
  for (const [id, def] of Object.entries(extra.metrics || {})) M.metrics[id] = { family: "more", ...def };
  Object.assign(M.activities, extra.activities || {});
  const fams = Object.keys(M.families);
  const files = await Promise.all(fams.map((f) => fetch(`data/facts/${f}.json`).then((r) => (r.ok ? r.json() : [])).catch(() => [])));
  for (const list of files) for (const f of list) FACTS[f.id] = f;
  $("#built").textContent = INDEX.built || "";
}
function slicesFor(metric) { return (INDEX.metrics[metric] || { slices: [] }).slices; }
function norm(dim, v) { return v || (dim === "sex" ? "all" : null); }
function popMatches(slice, pop, ignore = null) {
  for (const k of ["country", "sex", "age_band", "activity", "source_category"]) {
    if (k === ignore) continue;
    if (norm(k, slice[k]) !== norm(k, pop[k])) return false;
  }
  return true;
}
function findFact(metric, pop) { const s = slicesFor(metric).find((x) => popMatches(x, pop)); return s ? FACTS[s.id] : null; }
function optionsFor(metric, pop, dim) {
  const vals = new Set();
  for (const s of slicesFor(metric)) if (popMatches(s, pop, dim)) vals.add(norm(dim, s[dim]));
  return [...vals];
}
function metricsWithData() { return Object.keys(M.metrics).filter((m) => slicesFor(m).length); }
function reconcile(metric, pop, keep = null) {
  const p = { ...pop, activity: M.metrics[metric].activity || null };
  if (findFact(metric, p)) return p;
  for (const d of DIMS.filter((d) => d !== keep).reverse()) {
    if (d === "sex" ? p.sex === "all" : !p[d]) continue;
    p[d] = d === "sex" ? "all" : null;
    if (findFact(metric, p)) return p;
  }
  if (keep) { const q = { ...blankPop(), activity: p.activity, [keep]: p[keep] }; if (findFact(metric, q)) return q; }
  const base = { ...blankPop(), activity: p.activity };
  if (findFact(metric, base)) return base;
  // Some metrics exist only per sex: fall back to the first slice.
  const s = slicesFor(metric)[0];
  return s ? { country: s.country || null, sex: s.sex || "all", age_band: s.age_band || null, activity: s.activity || null, source_category: s.source_category || null } : base;
}

// ---------- URL ----------
function readURL() {
  const u = new URLSearchParams(location.search);
  state.mode = MODES.includes(u.get("mode")) ? u.get("mode") : "explore";
  if (u.get("f") && FACTS[u.get("f")]) {
    const f = FACTS[u.get("f")]; state.metric = f.metric; state.pop = { ...blankPop(), ...f.population }; delete state.pop.base;
  } else {
    state.metric = u.get("m") && M.metrics[u.get("m")] && slicesFor(u.get("m")).length ? u.get("m") : null;
    state.pop = { country: u.get("c") || null, sex: u.get("s") || "all", age_band: u.get("a") || null, activity: null, source_category: u.get("g") || null };
  }
  if (u.get("q") && PCT_KEYS.includes(`p${u.get("q")}`)) state.pct = `p${u.get("q")}`;
  if (!state.metric) { const avail = metricsWithData(); state.metric = avail.includes("income_pretax_adult_ppp") ? "income_pretax_adult_ppp" : avail[0]; }
  state.pop = reconcile(state.metric, state.pop);
  if (u.get("b") === "1") state.b = reconcile(state.metric, { country: u.get("bc") || null, sex: u.get("bs") || "all", age_band: u.get("ba") || null, activity: null, source_category: u.get("bg") || null });
  if (u.get("v")) state.v = parseFloat(u.get("v"));
}
function writeURL(push = false) {
  const u = new URLSearchParams();
  if (state.mode !== "explore") u.set("mode", state.mode);
  u.set("m", state.metric);
  const p = state.pop;
  if (p.country) u.set("c", p.country); if (p.sex !== "all") u.set("s", p.sex); if (p.age_band) u.set("a", p.age_band); if (p.source_category) u.set("g", p.source_category);
  u.set("q", state.pct.slice(1));
  if (state.b) { u.set("b", "1"); if (state.b.country) u.set("bc", state.b.country); if (state.b.sex !== "all") u.set("bs", state.b.sex); if (state.b.age_band) u.set("ba", state.b.age_band); if (state.b.source_category) u.set("bg", state.b.source_category); }
  const url = `${location.pathname}?${u.toString()}`;
  if (push) window.history.pushState(null, "", url); else window.history.replaceState(null, "", url);
}

// ---------- modes ----------
function setMode(mode, push = true) {
  state.mode = mode;
  for (const b of document.querySelectorAll("#modes button")) b.setAttribute("aria-pressed", b.dataset.mode === mode ? "true" : "false");
  for (const p of document.querySelectorAll(".pane")) p.hidden = p.dataset.pane !== mode;
  if (mode !== "compare" && state.b) { state.b = null; renderAnswer(findFact(state.metric, state.pop)); }
  if (mode === "compare" && !state.b) { state.b = reconcile(state.metric, { ...blankPop(), sex: state.pop.sex }); renderAnswer(findFact(state.metric, state.pop)); }
  if (mode === "surprise") surprise();
  renderPanes();
  writeURL(push);
}

// ---------- controls ----------
function option(value, label, selected) { const o = document.createElement("option"); o.value = value; o.textContent = label; o.selected = selected; return o; }
function dimLabel(dim, v) {
  if (dim === "country") return v ? (COUNTRY_SHORT[v] || v) : "Worldwide";
  if (dim === "sex") return v === "m" ? "Men" : v === "f" ? "Women" : "Everyone";
  if (dim === "age_band") return v ? ageBandPhrase(v).replace(/^aged /, "Aged ") : "All ages";
  return v || "All categories";
}
function renderMetricSelect() {
  const sel = $("#sel-metric"); sel.replaceChildren();
  const avail = metricsWithData();
  for (const [fid, f] of Object.entries(M.families).sort((a, b) => a[1].order - b[1].order)) {
    const ids = avail.filter((m) => M.metrics[m].family === fid);
    if (!ids.length) continue;
    const og = document.createElement("optgroup"); og.label = f.label;
    for (const mid of ids) og.appendChild(option(mid, M.metrics[mid].label, mid === state.metric));
    sel.appendChild(og);
  }
}
function renderGroupSelects(prefix, pop) {
  const map = { country: `#${prefix}-country`, sex: `#${prefix}-sex`, age_band: `#${prefix}-age`, source_category: `#${prefix}-cat` };
  for (const dim of DIMS) {
    const sel = $(map[dim]);
    const opts = optionsFor(state.metric, pop, dim);
    const cur = norm(dim, pop[dim]);
    if (!opts.includes(cur)) opts.push(cur);
    opts.sort((a, b) => {
      if (a === null || a === "all") return -1; if (b === null || b === "all") return 1;
      if (dim === "age_band") return parseInt(a, 10) - parseInt(b, 10);
      return dimLabel(dim, a).localeCompare(dimLabel(dim, b));
    });
    sel.replaceChildren();
    for (const o of opts) sel.appendChild(option(o === null ? "" : o, dimLabel(dim, o), o === cur));
    sel.hidden = opts.length < 2;
  }
}
function renderPct(fact) {
  const seg = $("#pct-seg"); seg.replaceChildren();
  for (const pk of PCT_KEYS) {
    const b = document.createElement("button"); b.type = "button"; b.textContent = M.percentiles[pk.slice(1)].label;
    b.setAttribute("aria-pressed", pk === state.pct ? "true" : "false");
    b.disabled = fact ? !(gridKeyFor(fact.direction, pk) in fact.grid) : false;
    b.addEventListener("click", () => { state.pct = pk; update(true); });
    seg.appendChild(b);
  }
}
function renderPanes() {
  renderMetricSelect();
  renderGroupSelects("sel", state.pop);
  const fact = findFact(state.metric, state.pop);
  renderPct(fact);
  if (fact) renderLandPane(fact);
  renderProfile();
  if (state.b) { renderGroupSelects("selb", state.b); renderCompareLine(fact); }
}

// ---------- chain ----------
function renderChain(fact) {
  const ol = $("#chain"); ol.replaceChildren();
  const m = M.metrics[state.metric];
  const root = document.createElement("li");
  const rootBtn = document.createElement("button"); rootBtn.type = "button";
  // "All people who finished a marathon", not "All finishers who finished a marathon".
  rootBtn.textContent = state.metric === "age_years" ? "Everyone alive" : state.pop.activity ? `All people ${(M.activities[state.pop.activity] || { label: "" }).label}` : `All ${m.base_noun || "people"}`;
  rootBtn.title = "Back to the whole group";
  rootBtn.addEventListener("click", () => { state.pop = reconcile(state.metric, { ...blankPop(), activity: state.pop.activity }); state.v = null; update(true); });
  root.appendChild(rootBtn); ol.appendChild(root);
  for (const dim of DIMS) {
    const v = state.pop[dim]; if (!v || (dim === "sex" && v === "all")) continue;
    const li = document.createElement("li"); const b = document.createElement("button"); b.type = "button";
    b.textContent = dimLabel(dim, v); b.title = `Remove ${dimLabel(dim, v)}`;
    b.addEventListener("click", () => { state.pop = reconcile(state.metric, { ...state.pop, [dim]: dim === "sex" ? "all" : null }); state.v = null; update(true); });
    li.appendChild(b); ol.appendChild(li);
  }
  const more = DIMS.filter((d) => (d === "sex" ? state.pop.sex === "all" : !state.pop[d]) && optionsFor(state.metric, state.pop, d).length > 1);
  if (more.length) {
    const li = document.createElement("li"); li.className = "hint";
    li.textContent = `narrow by ${more.map((d) => ({ country: "country", sex: "sex", age_band: "age", source_category: "category" })[d]).join(", ")}`;
    ol.appendChild(li);
  }
  if (fact && fact.n) {
    const li = document.createElement("li"); li.className = "root"; li.textContent = `${formatCount(fact.n)} people`; ol.appendChild(li);
  }
}

// ---------- answer ----------
function gradeWord(g) { return { A: "two sources agree", B: "one official source", C: "sources disagree", D: "unreviewed" }[g] || ""; }
function axisFmt(metric) {
  const fmt = M.metrics[metric].format;
  if (fmt === "money") return (v, short) => { const a = Math.abs(v); const s = a >= 1e6 ? `$${+(v / 1e6).toPrecision(3)}M` : a >= 1e3 ? `$${Math.round(v / 1e3)}k` : `$${Math.round(v)}`; return short ? s : formatValue(M, metric, v); };
  // Axis ticks drop the parenthetical conversion ("202 cm", not "202 cm (6 ft 7 in)").
  return (v, short) => { const t = formatValue(M, metric, v); return short ? t.replace(/\s*\(.*\)$/, "") : t; };
}
function cumulative(pk) { return parseFloat(pk.slice(1)) / 100; }
function gridPoints(fact) { return Object.entries(fact.grid).map(([k, v]) => [cumulative(k), v]).sort((a, b) => a[0] - b[0]); }

function renderAnswer(fact) {
  const pl = $("#punchline"), sub = $("#subline"), empty = $("#empty");
  pl.classList.remove("skeleton", "skeleton--title");
  renderChain(fact);
  if (!fact) {
    pl.classList.add("empty"); pl.textContent = "No data for this group yet."; sub.textContent = "";
    $("#curve").innerHTML = ""; $("#curve-cap").textContent = ""; $("#history").hidden = true;
    renderEvidence(null); renderEmpty(null);
    return;
  }
  empty.hidden = true;
  pl.classList.remove("empty");
  const { text, value } = punchline(M, fact, state.pct);
  const i = text.lastIndexOf(value);
  pl.replaceChildren(text.slice(0, i)); const b = document.createElement("b"); b.textContent = value; pl.appendChild(b); pl.append(text.slice(i + value.length));
  sub.replaceChildren();
  const g = document.createElement("span"); g.className = `grade${fact.grade === "D" ? " d" : ""}`; g.textContent = `Grade ${fact.grade}`; sub.appendChild(g);
  const bits = [gradeWord(fact.grade)];
  if (fact.n) { const top = { p50: 0.5, p90: 0.1, p99: 0.01 }[state.pct]; bits.push(state.pct === "p50" ? `${formatCount(fact.n)} in the group` : `that's ${formatCount(fact.n * top)} people`); }
  bits.push(`reference year ${fact.year}`);
  sub.append(bits.join(" · "));
  renderCurve(fact);
  renderHistory(fact);
  renderEvidence(fact);
  $("#btn-card").href = `cards/${fact.id}.png`; $("#btn-card").download = `${fact.id}.png`;
}

function renderCurve(fact) {
  const fmt = axisFmt(fact.metric);
  const name = groupName(M, fact.population, fact.metric, fact.year);
  const series = [{ name, points: gridPoints(fact), cls: "" }];
  const factB = state.b ? findFact(state.metric, state.b) : null;
  if (factB && factB.id !== fact.id) series.push({ name: groupName(M, factB.population, factB.metric, factB.year), points: gridPoints(factB), cls: "b" });
  const gk = gridKeyFor(fact.direction, state.pct);
  const marks = [{ share: cumulative(gk), value: fact.grid[gk], label: `${M.percentiles[state.pct.slice(1)].label}: ${formatValue(M, fact.metric, fact.grid[gk])}`, cls: "mark-pct" }];
  if (state.v != null) {
    const r = placeValue(fact, state.v);
    if (r.kind === "between") marks.push({ share: fact.direction === "high" ? 1 - r.top : r.top, value: state.v, label: `You: ${formatValue(M, fact.metric, state.v)}`, cls: "mark-you" });
  }
  const log = M.metrics[fact.metric].format === "money" && series[0].points.filter((p) => p[1] > 0).length > 2;
  curve($("#curve"), { series, marks, fmt, log, xLabel: fact.direction === "low" ? "share of the group at or below this time (fastest on the left)" : "share of the group at or below this value", yLabel: M.metrics[fact.metric].label + (log ? " (log scale)" : "") });
  const legend = [`<span>${esc(name)}</span>`];
  if (series[1]) legend.push(`<span class="b">${esc(series[1].name)}</span>`);
  legend.push(`<span class="pct">chosen percentile</span>`);
  if (marks[1]) legend.push(`<span class="you">you</span>`);
  $("#curve-cap").innerHTML = `<div class="legend">${legend.join("")}</div>The whole distribution the sentence comes from: ${Object.keys(fact.grid).length} published points, joined by straight lines. Hover for any point.`;
}
function esc(s) { return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;"); }

function renderHistory(fact) {
  const h = $("#history");
  const gk = gridKeyFor(fact.direction, state.pct);
  const years = fact.series ? Object.keys(fact.series).filter((y) => fact.series[y][gk] != null) : [];
  if (years.length < 3) { h.hidden = true; return; }
  h.hidden = false;
  const points = years.map((y) => [parseInt(y, 10), fact.series[y][gk]]).concat([[fact.year, fact.grid[gk]]]).sort((a, b) => a[0] - b[0]);
  const fmt = axisFmt(fact.metric);
  historyChart($("#history-svg"), { points, fmt, label: `${M.percentiles[state.pct.slice(1)].label} threshold over time` });
  const first = points[0], last = points[points.length - 1];
  const change = first[1] ? ((last[1] - first[1]) / Math.abs(first[1])) * 100 : null;
  $("#history-cap").textContent = `${M.percentiles[state.pct.slice(1)].label} threshold for ${groupName(M, fact.population, fact.metric, fact.year)}, ${first[0]} to ${last[0]}: ${formatValue(M, fact.metric, first[1])} to ${formatValue(M, fact.metric, last[1])}` + (change != null ? ` (${change >= 0 ? "+" : ""}${Math.round(change)}%). ` : ". ") + (M.metrics[fact.metric].format === "money" ? "Constant purchasing-power dollars, so the change is real, not inflation." : "");
}

function renderEvidence(fact) {
  const el = $("#evidence-body"); el.replaceChildren();
  if (!fact) { el.innerHTML = `<h2>Evidence</h2><p>Nothing to show until there is a fact.</p>`; return; }
  const gk = gridKeyFor(fact.direction, state.pct);
  const parts = [];
  parts.push(`<h2>Confidence</h2><div class="ev-grade"><span class="letter${fact.grade === "D" ? " d" : ""}">${fact.grade}</span><span class="word">${esc(gradeWord(fact.grade))}</span></div>`);
  if (fact.status === "queued") parts.push(`<p class="unrev">Unreviewed: researched automatically, not yet checked by a person.</p>`);
  parts.push(`<p>${esc(fact.reason || "")}</p>`);
  const rng = fact.range && fact.range[gk];
  const dl = [];
  if (rng && rng.length === 2 && rng[0] !== rng[1]) dl.push(["Range across sources", `${formatValue(M, fact.metric, rng[0])} to ${formatValue(M, fact.metric, rng[1])}`, true]);
  else if (fact.sources.length === 1) dl.push(["Range", "one source, no spread to show", false]);
  if (fact.n) dl.push(["Group size", `${formatCount(fact.n)}${fact.n_source_name ? ` (${fact.n_source_name})` : ""}`, false]);
  dl.push(["Reference year", String(fact.year), true]);
  dl.push(["Definition", fact.definition || "", false]);
  if (fact.caveat) dl.push(["Caveat", fact.caveat, false]);
  parts.push(`<dl>${dl.map(([k, v, num]) => `<dt>${esc(k)}</dt><dd class="${num ? "num" : ""}">${esc(v)}</dd>`).join("")}</dl>`);
  parts.push(`<h2>Sources</h2><ul class="src">${fact.sources.map((s) => { const v = s.values && s.values[gk]; return `<li><a href="${esc(s.url)}" rel="noopener">${esc(s.name)}</a><span class="what">${esc(s.measures || "")}</span>${v != null ? `<span class="val">${esc(formatValue(M, fact.metric, v))} at this percentile · accessed ${esc(s.accessed || "")}</span>` : ""}</li>`; }).join("")}</ul>`);
  el.innerHTML = parts.join("");
}

function renderEmpty(parsed) {
  const e = $("#empty"); e.hidden = false;
  const unmatched = parsed && parsed.unmatched && parsed.unmatched.metric;
  const known = parsed && parsed.metric && M.metrics[parsed.metric] && !slicesFor(parsed.metric).length;
  let text, title = "No data for that yet";
  if (unmatched) text = `"${unmatched}" is not a measure on the site yet.`;
  else if (known) text = `${M.metrics[parsed.metric].label} is a measure we plan to cover, but the data is not in yet.`;
  else text = "This exact group has no fact. Nearest groups with data are listed below.";
  $("#empty-h").textContent = title; $("#empty-text").textContent = text;
  const near = !unmatched && !known ? slicesFor(state.metric).filter((s) => popMatches(s, state.pop, "age_band") || popMatches(s, state.pop, "country") || popMatches(s, state.pop, "sex")).slice(0, 4) : [];
  $("#empty-near").textContent = near.length ? near.map((s) => groupName(M, s, state.metric, s.year)).join("; ") + "." : "";
  const q = parsed && parsed.q ? parsed.q : `${M.metrics[state.metric].label}: ${groupName(M, state.pop, state.metric, new Date().getFullYear())}`;
  $("#btn-request").href = `${REPO}/issues/new?labels=fact-request&title=${encodeURIComponent("Fact request: " + q.slice(0, 80))}&body=${encodeURIComponent(`Question: ${q}\n\nParsed as: ${JSON.stringify(parsed && parsed.metric ? { metric: parsed.metric, population: parsed.population, percentile: parsed.percentile } : null)}\n\n(Filed from the site. The research loop picks these up.)`)}`;
  const rb = $("#btn-research"); rb.hidden = !WORKER; rb.onclick = () => researchLive(q);
}

// ---------- where do I land ----------
function placeValue(fact, v) {
  const pts = gridPoints(fact);
  const log = M.metrics[fact.metric].format === "money" && v > 0 && pts.every((p) => p[1] > 0);
  const tr = (x) => (log ? Math.log(x) : x);
  const asc = fact.direction === "high";
  const inside = pts.map((p) => [p[0], tr(p[1])]);
  const tv = tr(v);
  let lo = null, hi = null;
  for (let i = 0; i < inside.length - 1; i++) { const [c0, v0] = inside[i], [c1, v1] = inside[i + 1]; if (tv >= Math.min(v0, v1) && tv <= Math.max(v0, v1)) { lo = [c0, v0]; hi = [c1, v1]; break; } }
  const topShare = (c) => (asc ? 1 - c : c);
  if (!lo) {
    const first = inside[0], last = inside[inside.length - 1];
    const beyondTop = asc ? tv > last[1] : tv < first[1];
    if (beyondTop) return { kind: "beyond", top: topShare(asc ? last[0] : first[0]) };
    return { kind: "below", bottom: asc ? first[0] : last[0] };
  }
  const f = hi[1] === lo[1] ? 0 : (tv - lo[1]) / (hi[1] - lo[1]);
  const c = lo[0] + f * (hi[0] - lo[0]);
  return { kind: "between", top: topShare(c), bandTop: [topShare(lo[0]), topShare(hi[0])].sort((a, b) => a - b) };
}
function pctText(x) { return x < 0.01 ? `${(x * 100).toFixed(1)}%` : `${Math.round(x * 100)}%`; }
function placementText(fact, v) {
  const r = placeValue(fact, v); const fv = formatValue(M, fact.metric, v); const group = groupName(M, fact.population, fact.metric, fact.year);
  if (r.kind === "beyond") return { lead: `${fv}: `, strong: `top ${pctText(r.top)} or better`, tail: ` of ${group}; the data stops there.`, top: r.top };
  if (r.kind === "below") return { lead: `${fv}: `, strong: `below the ${pctText(r.bottom)} mark`, tail: ` for ${group}; the data stops there.`, top: null };
  return { lead: `${fv}: `, strong: `roughly top ${pctText(r.top)}`, tail: ` of ${group} (between the top ${pctText(r.bandTop[0])} and top ${pctText(r.bandTop[1])} marks).`, top: r.top };
}
function renderLandPane(fact) {
  const m = M.metrics[fact.metric];
  $("#v-label").textContent = m.format === "money" ? "Your amount (USD)" : m.format.startsWith("time") ? "Your time (h:mm or mm:ss)" : m.format === "height" ? "Your height (cm or ft'in)" : m.format === "weight" ? "Your weight (kg or lb)" : `Your ${m.label.toLowerCase()}`;
  const prof = loadProfile();
  if (state.v == null && prof[fact.metric] && prof[fact.metric].factId === fact.id) state.v = prof[fact.metric].v;
  $("#v").value = state.v == null ? "" : rawToInput(fact, state.v);
  const out = $("#land-out"); out.replaceChildren();
  if (state.v != null) { const t = placementText(fact, state.v); const b = document.createElement("b"); b.textContent = t.strong; out.append(t.lead, b, t.tail); }
}
function rawToInput(fact, v) {
  const fmt = M.metrics[fact.metric].format;
  if (fmt.startsWith("time")) { const h = Math.floor(v / 3600), mm = Math.floor((v % 3600) / 60), ss = Math.round(v % 60); return fmt === "time_hm" ? `${h}:${String(mm).padStart(2, "0")}` : `${h * 60 + mm}:${String(ss).padStart(2, "0")}`; }
  return String(Math.round(v * 10) / 10);
}
function inputToRaw(fact, s) {
  const fmt = M.metrics[fact.metric].format;
  s = s.trim().toLowerCase().replace(/,/g, "").replace(/\$/g, "");
  let m;
  if (fmt.startsWith("time") && (m = s.match(/^(\d{1,2}):(\d{2})(?::(\d{2}))?$/))) { if (m[3]) return (+m[1]) * 3600 + (+m[2]) * 60 + (+m[3]); return fmt === "time_hm" ? (+m[1]) * 3600 + (+m[2]) * 60 : (+m[1]) * 60 + (+m[2]); }
  if ((m = s.match(/^(\d+)\s*(?:ft|')\s*(\d{1,2})?/))) return ((+m[1]) * 12 + (m[2] ? +m[2] : 0)) * 2.54;
  if ((m = s.match(/^([\d.]+)\s*(lb|lbs)$/))) return (+m[1]) / 2.20462;
  if ((m = s.match(/^([\d.]+)\s*k$/))) return (+m[1]) * 1000;
  if ((m = s.match(/^([\d.]+)\s*(m|million)$/))) return (+m[1]) * 1e6;
  const n = parseFloat(s); return Number.isFinite(n) ? n : null;
}
function loadProfile() { try { return JSON.parse(localStorage.getItem(LS_KEY) || "{}"); } catch { return {}; } }
function saveProfile(metric, entry) { try { const o = loadProfile(); if (entry == null) delete o[metric]; else o[metric] = entry; localStorage.setItem(LS_KEY, JSON.stringify(o)); } catch { /* storage unavailable */ } }
function renderProfile() {
  const prof = loadProfile(); const wrap = $("#profile"), ul = $("#profile-list"); ul.replaceChildren();
  const entries = Object.entries(prof).filter(([mid, e]) => M.metrics[mid] && FACTS[e.factId]);
  wrap.hidden = !entries.length;
  for (const [mid, e] of entries) {
    const f = FACTS[e.factId]; const t = placementText(f, e.v);
    const li = document.createElement("li");
    const a = document.createElement("button"); a.type = "button"; a.textContent = `${M.metrics[mid].label}: ${formatValue(M, mid, e.v)}`; a.style.textDecoration = "underline"; a.style.color = "var(--ink)"; a.style.fontSize = ".9rem";
    a.addEventListener("click", () => { state.metric = f.metric; state.pop = { ...blankPop(), ...f.population }; delete state.pop.base; state.v = e.v; update(true); });
    const b = document.createElement("b"); b.textContent = t.strong;
    const x = document.createElement("button"); x.type = "button"; x.textContent = "erase"; x.addEventListener("click", () => { saveProfile(mid, null); if (state.metric === mid) state.v = null; update(false); });
    li.append(a, b, x); ul.appendChild(li);
  }
}

// ---------- compare ----------
function renderCompareLine(factA) {
  const el = $("#compare-line"); el.replaceChildren();
  const factB = state.b ? findFact(state.metric, state.b) : null;
  if (!factA || !factB) { el.textContent = factB ? "" : "No data for that second group."; return; }
  const gk = gridKeyFor(factA.direction, state.pct);
  const a = factA.grid[gk], b = factB.grid[gk];
  if (a == null || b == null) { el.textContent = ""; return; }
  const label = M.percentiles[state.pct.slice(1)].label.toLowerCase();
  const nameA = groupName(M, factA.population, factA.metric, factA.year), nameB = groupName(M, factB.population, factB.metric, factB.year);
  const better = factA.direction === "high" ? b > a : b < a;
  const ratio = a && b ? Math.max(a, b) / Math.min(a, b) : null;
  const cmp = ratio && Math.abs(ratio - 1) > 0.02 ? ` For ${nameB} the bar is ${ratio.toFixed(ratio < 10 ? 1 : 0)}x ${better ? "higher" : "lower"}.` : " Nearly the same bar.";
  el.textContent = `${label.charAt(0).toUpperCase() + label.slice(1)}: ${formatValue(M, factA.metric, a)} for ${nameA}; ${formatValue(M, factB.metric, b)} for ${nameB}.${cmp}`;
}

// ---------- surprise ----------
function surprise() {
  const pool = Object.values(FACTS).filter((f) => f.grade === "A" || f.grade === "B");
  const recent = JSON.parse(sessionStorage.getItem("oih.recent") || "[]");
  const clean = pool.filter((f) => !f.population.age_band && !f.population.source_category && !recent.includes(f.id));
  const cand = clean.length ? clean : pool;
  const f = cand[Math.floor(Math.random() * cand.length)];
  sessionStorage.setItem("oih.recent", JSON.stringify([f.id, ...recent].slice(0, 8)));
  state.metric = f.metric; state.pop = { ...blankPop(), ...f.population }; delete state.pop.base;
  state.pct = ["p99", "p90", "p50"].find((k) => gridKeyFor(f.direction, k) in f.grid) || "p50"; state.v = null; state.b = null;
  update(true);
}

// ---------- ask ----------
async function ask(q) {
  const note = $("#ask-note"); note.textContent = "Reading your question…";
  let parsed = null;
  if (WORKER) {
    try {
      const ctl = new AbortController(); const t = setTimeout(() => ctl.abort(), 2500);
      const r = await fetch(`${WORKER}/parse`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ q }), signal: ctl.signal });
      clearTimeout(t); const j = await r.json();
      if (j.ok) parsed = { ...j.triple, confidence: j.confidence, parser: "llm", unmatched: j.unmatched || {} };
    } catch { parsed = null; }
  }
  if (!parsed) parsed = parseRules(q, M);
  parsed.q = q;
  if (parsed.metric && slicesFor(parsed.metric).length) {
    state.metric = parsed.metric;
    let pop = { ...blankPop(), ...parsed.population }; delete pop.base;
    pop = snapAge(parsed.metric, pop);
    state.pop = reconcile(parsed.metric, pop);
    state.pct = PCT_KEYS.includes(`p${parsed.percentile}`) ? `p${parsed.percentile}` : "p99";
    state.v = parsed.value; state.b = null;
    update(true);
    note.textContent = `Understood as ${describeParsed(parsed)}.${parsed.confidence === "low" ? " If that is wrong, adjust it in Explore." : ""}`;
  } else {
    renderAnswer(null); renderEmpty(parsed);
    note.textContent = parsed.metric && M.metrics[parsed.metric] ? `Understood as ${M.metrics[parsed.metric].label.toLowerCase()}, but there is no data for it yet.` : "That is not a measure on the site yet.";
  }
}
function describeParsed(p) {
  const bits = [M.metrics[p.metric].label.toLowerCase()];
  if (p.population.country) bits.push(COUNTRY_SHORT[p.population.country]);
  if (p.population.sex !== "all") bits.push(p.population.sex === "m" ? "men" : "women");
  if (p.population.age_band) bits.push(ageBandPhrase(p.population.age_band));
  bits.push((M.percentiles[String(p.percentile)] || M.percentiles["99"]).label.toLowerCase());
  return bits.join(", ");
}
function inBand(b, age) { if (b.endsWith("+")) return age >= parseInt(b, 10); const [lo, hi] = b.split("-").map(Number); return age >= lo && age <= hi; }
function snapAge(metric, pop) {
  if (!pop.age_band) return pop;
  const bands = optionsFor(metric, { ...pop, age_band: null }, "age_band").filter(Boolean);
  if (bands.includes(pop.age_band)) return pop;
  const lo = parseInt(pop.age_band, 10);
  return { ...pop, age_band: bands.find((b) => inBand(b, lo)) || null };
}

// Live research through the Worker: the answer arrives as a D-grade fact and is shown at once.
async function researchLive(q) {
  const rb = $("#btn-research"); rb.disabled = true; rb.textContent = "Researching…";
  try {
    const r = await fetch(`${WORKER}/research`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ q }) });
    const j = await r.json();
    if (!j.ok || !j.found) { $("#empty-text").textContent = j.why || "Nothing credible was found just now. The request has been queued."; return; }
    M.metrics[j.metric_def.id] = { family: "more", ...j.metric_def };
    FACTS[j.fact.id] = j.fact;
    INDEX.metrics[j.metric_def.id] = { slices: [{ id: j.fact.id, ...j.fact.population, year: j.fact.year, grade: "D", keys: Object.keys(j.fact.grid), status: "queued" }] };
    state.metric = j.metric_def.id; state.pop = { ...blankPop(), ...j.fact.population }; delete state.pop.base;
    state.pct = ["p99", "p90", "p50"].find((k) => gridKeyFor(j.fact.direction, k) in j.fact.grid) || "p50";
    update(false);
  } catch { $("#empty-text").textContent = "The research service did not answer. The request has been queued."; }
  finally { rb.disabled = false; rb.textContent = "Research it now"; }
}

// ---------- share ----------
async function shareLink() {
  const fact = findFact(state.metric, state.pop);
  const url = fact ? `${location.origin}${location.pathname.replace(/[^/]*$/, "")}f/${fact.id}/` : location.href;
  try { await navigator.clipboard.writeText(url); $("#btn-link").textContent = "Link copied"; setTimeout(() => ($("#btn-link").textContent = "Copy link"), 1500); } catch { prompt("Copy this link", url); }
}

// ---------- orchestration ----------
function update(push = false) {
  const fact = findFact(state.metric, state.pop);
  if (fact && !(gridKeyFor(fact.direction, state.pct) in fact.grid)) state.pct = PCT_KEYS.find((k) => gridKeyFor(fact.direction, k) in fact.grid) || "p50";
  if (state.b) state.b = reconcile(state.metric, state.b);
  renderPanes();
  renderAnswer(fact);
  writeURL(push);
}

async function init() {
  await loadData();
  readURL();
  setMode(state.mode, false);
  update(false);
  $("#modes").addEventListener("click", (e) => { const b = e.target.closest("button[data-mode]"); if (b) setMode(b.dataset.mode); });
  $("#sel-metric").addEventListener("change", (e) => { state.metric = e.target.value; state.v = null; state.pop = reconcile(state.metric, state.pop); update(true); });
  const dimOf = { country: "country", sex: "sex", age: "age_band", cat: "source_category" };
  for (const [suffix, dim] of Object.entries(dimOf)) {
    document.getElementById(`sel-${suffix}`).addEventListener("change", (e) => { state.pop = reconcile(state.metric, { ...state.pop, [dim]: e.target.value || (dim === "sex" ? "all" : null) }, dim); state.v = null; update(true); });
    document.getElementById(`selb-${suffix}`).addEventListener("change", (e) => { state.b = reconcile(state.metric, { ...state.b, [dim]: e.target.value || (dim === "sex" ? "all" : null) }, dim); update(true); });
  }
  $("#ask-form").addEventListener("submit", (e) => { e.preventDefault(); const q = $("#q").value.trim(); if (q) ask(q); });
  // Enter asks; Shift+Enter makes a new line.
  $("#q").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); const q = $("#q").value.trim(); if (q) ask(q); } });
  $("#examples").addEventListener("click", (e) => { const b = e.target.closest("button"); if (b) { $("#q").value = b.textContent; ask(b.textContent); } });
  $("#land-form").addEventListener("submit", (e) => {
    e.preventDefault(); const fact = findFact(state.metric, state.pop); if (!fact) return;
    const v = inputToRaw(fact, $("#v").value);
    if (v == null) { $("#land-out").textContent = "Couldn't read that value. Try a plain number, h:mm for a time, or 6'2 for a height."; return; }
    state.v = v; saveProfile(fact.metric, { v, factId: fact.id }); update(false);
  });
  $("#v-clear").addEventListener("click", () => { const fact = findFact(state.metric, state.pop); state.v = null; if (fact) saveProfile(fact.metric, null); $("#v").value = ""; update(false); });
  $("#btn-surprise").addEventListener("click", surprise);
  $("#btn-link").addEventListener("click", shareLink);
  window.addEventListener("popstate", () => { readURL(); setMode(state.mode, false); update(false); });
}
init().catch((e) => { $("#punchline").classList.remove("skeleton"); $("#punchline").textContent = "The data failed to load. Reload the page."; console.error(e); });
