// One in a Hundred: the core screen. State lives in the URL; data is static.
import { punchline, groupName, formatCount, formatValue, gridKeyFor, COUNTRY_SHORT, ageBandPhrase } from "./format.js";
import { parseRules } from "./parser-rules.js";

const $ = (s) => document.querySelector(s);
const PCT_KEYS = ["p50", "p90", "p99"];
const WORKER = null; // set to the Worker origin when the parse service is deployed; null = rules parser only
const LS_KEY = "oih.values";
const DIMS = ["country", "sex", "age_band", "source_category"];

let M, INDEX, FACTS = {};
const state = { metric: null, pop: blankPop(), pct: "p99", v: null };

function blankPop() { return { country: null, sex: "all", age_band: null, activity: null, source_category: null }; }

// ---------- data ----------
async function loadData() {
  const [m, idx] = await Promise.all([fetch("data/metrics.json").then((r) => r.json()), fetch("data/index.json").then((r) => r.json())]);
  M = m; INDEX = idx;
  const files = await Promise.all(Object.keys(M.families).map((f) => fetch(`data/facts/${f}.json`).then((r) => (r.ok ? r.json() : []))));
  for (const list of files) for (const f of list) FACTS[f.id] = f;
  $("#built").textContent = INDEX.built || "";
}
function slicesFor(metric) { return (INDEX.metrics[metric] || { slices: [] }).slices; }
function popMatches(slice, pop, ignore = null) {
  for (const k of ["country", "sex", "age_band", "activity", "source_category"]) {
    if (k === ignore) continue;
    const a = slice[k] || (k === "sex" ? "all" : null), b = pop[k] || (k === "sex" ? "all" : null);
    if (a !== b) return false;
  }
  return true;
}
function findFact(metric, pop) {
  const s = slicesFor(metric).find((x) => popMatches(x, pop));
  return s ? FACTS[s.id] : null;
}
function optionsFor(metric, pop, dim) {
  const vals = new Set();
  for (const s of slicesFor(metric)) if (popMatches(s, pop, dim)) vals.add(s[dim] || (dim === "sex" ? "all" : null));
  return [...vals];
}
function metricsWithData() { return Object.keys(M.metrics).filter((m) => slicesFor(m).length); }

// Make the population valid for the metric: keep the dimension that was just
// changed, drop the others one at a time until a fact exists.
function reconcile(metric, pop, keep = null) {
  const p = { ...pop, activity: M.metrics[metric].activity || null };
  if (findFact(metric, p)) return p;
  const order = DIMS.filter((d) => d !== keep).reverse(); // drop category, then age, then sex, then country
  for (const d of order) {
    if (d === "sex" ? p.sex === "all" : !p[d]) continue;
    p[d] = d === "sex" ? "all" : null;
    if (findFact(metric, p)) return p;
  }
  if (keep && findFact(metric, { ...blankPop(), activity: p.activity, [keep]: p[keep] })) return { ...blankPop(), activity: p.activity, [keep]: p[keep] };
  return { ...blankPop(), activity: p.activity };
}

// ---------- URL ----------
function readURL() {
  const u = new URLSearchParams(location.search);
  if (u.get("f") && FACTS[u.get("f")]) {
    const f = FACTS[u.get("f")];
    state.metric = f.metric; state.pop = { ...blankPop(), ...f.population }; delete state.pop.base;
  } else {
    state.metric = u.get("m") && M.metrics[u.get("m")] && slicesFor(u.get("m")).length ? u.get("m") : null;
    state.pop = { country: u.get("c") || null, sex: u.get("s") || "all", age_band: u.get("a") || null, activity: null, source_category: u.get("g") || null };
  }
  if (u.get("q") && PCT_KEYS.includes(`p${u.get("q")}`)) state.pct = `p${u.get("q")}`;
  if (!state.metric) {
    const avail = metricsWithData();
    state.metric = avail.includes("income_pretax_adult_ppp") ? "income_pretax_adult_ppp" : avail[0];
  }
  state.pop = reconcile(state.metric, state.pop);
}
function writeURL(push = false) {
  const u = new URLSearchParams();
  u.set("m", state.metric);
  const p = state.pop;
  if (p.country) u.set("c", p.country);
  if (p.sex && p.sex !== "all") u.set("s", p.sex);
  if (p.age_band) u.set("a", p.age_band);
  if (p.source_category) u.set("g", p.source_category);
  u.set("q", state.pct.slice(1));
  const url = `${location.pathname}?${u.toString()}`;
  if (push) history.pushState(null, "", url); else history.replaceState(null, "", url);
}

// ---------- controls ----------
function option(value, label, selected) {
  const o = document.createElement("option"); o.value = value; o.textContent = label; o.selected = selected; return o;
}
function renderMetricSelect() {
  const sel = $("#sel-metric");
  sel.replaceChildren();
  const avail = metricsWithData();
  for (const [fid, f] of Object.entries(M.families).sort((a, b) => a[1].order - b[1].order)) {
    const ids = avail.filter((m) => M.metrics[m].family === fid);
    if (!ids.length) continue;
    const og = document.createElement("optgroup"); og.label = f.label;
    for (const mid of ids) og.appendChild(option(mid, M.metrics[mid].label, mid === state.metric));
    sel.appendChild(og);
  }
}
function dimLabel(dim, v) {
  if (dim === "country") return v ? (COUNTRY_SHORT[v] || v) : "Worldwide";
  if (dim === "sex") return v === "m" ? "Men" : v === "f" ? "Women" : "Everyone";
  if (dim === "age_band") return v ? ageBandPhrase(v).replace(/^aged /, "Aged ") : "All ages";
  return v || "All categories";
}
function renderGroupSelects() {
  const map = { country: "#sel-country", sex: "#sel-sex", age_band: "#sel-age", source_category: "#sel-cat" };
  for (const dim of DIMS) {
    const sel = $(map[dim]);
    const opts = optionsFor(state.metric, state.pop, dim);
    const cur = state.pop[dim] || (dim === "sex" ? "all" : null);
    if (!opts.includes(cur)) opts.push(cur);
    const sorted = opts.sort((a, b) => {
      if (a === null || a === "all") return -1; if (b === null || b === "all") return 1;
      if (dim === "age_band") return parseInt(a, 10) - parseInt(b, 10);
      return dimLabel(dim, a).localeCompare(dimLabel(dim, b));
    });
    sel.replaceChildren();
    for (const o of sorted) sel.appendChild(option(o === null ? "" : o, dimLabel(dim, o), o === cur));
    // A select that offers no choice in the current context is hidden, not
    // greyed out; it reappears when another selection unlocks it.
    sel.hidden = sorted.length < 2;
  }
}
function renderPct(fact) {
  const seg = $("#pct-seg");
  seg.replaceChildren();
  for (const pk of PCT_KEYS) {
    const b = document.createElement("button");
    b.type = "button"; b.textContent = M.percentiles[pk.slice(1)].label;
    b.setAttribute("aria-pressed", pk === state.pct ? "true" : "false");
    b.disabled = fact ? !(gridKeyFor(fact.direction, pk) in fact.grid) : false;
    b.addEventListener("click", () => { state.pct = pk; update(true); });
    seg.appendChild(b);
  }
}

// ---------- answer ----------
function gradeTag(f) {
  const s = document.createElement("span");
  s.className = `grade${f.grade === "D" ? " d" : ""}`;
  s.textContent = f.grade === "D" ? "Grade D, unreviewed" : `Grade ${f.grade}`;
  return s;
}
function renderAnswer(fact) {
  const pl = $("#punchline"), sub = $("#subline"), panel = $("#panel");
  pl.classList.remove("skeleton", "skeleton--title");
  panel.hidden = true;
  if (!fact) {
    pl.classList.add("empty");
    pl.textContent = "No data for this group yet.";
    sub.textContent = "";
    $("#land-form").hidden = true;
    renderQueue(null);
    return;
  }
  $("#queue").hidden = true;
  pl.classList.remove("empty");
  const { text, value } = punchline(M, fact, state.pct);
  const i = text.lastIndexOf(value);
  pl.replaceChildren(text.slice(0, i));
  const b = document.createElement("b"); b.textContent = value; pl.appendChild(b);
  pl.append(text.slice(i + value.length));

  sub.replaceChildren(gradeTag(fact));
  const bits = [];
  if (fact.n) {
    const top = { p50: 0.5, p90: 0.1, p99: 0.01 }[state.pct];
    bits.push(state.pct === "p50" ? `${formatCount(fact.n)} people in the group` : `that's ${formatCount(fact.n * top)} people`);
  }
  bits.push(`reference year ${fact.year}`);
  sub.append(bits.join(" · ") + " · ");
  const why = document.createElement("button"); why.type = "button"; why.textContent = "Why this grade?";
  why.addEventListener("click", () => { panel.hidden = !panel.hidden; why.textContent = panel.hidden ? "Why this grade?" : "Hide sources"; });
  sub.appendChild(why);
  renderPanel(fact);
  renderLand(fact);
  $("#btn-card").href = `cards/${fact.id}.png`;
  $("#btn-card").download = `${fact.id}.png`;
}
function renderPanel(fact) {
  const panel = $("#panel");
  panel.replaceChildren();
  const gk = gridKeyFor(fact.direction, state.pct);
  if (fact.status === "queued") {
    const u = document.createElement("p"); u.className = "unrev";
    u.textContent = "Unreviewed: researched automatically, not yet checked by a person.";
    panel.appendChild(u);
  }
  const h = document.createElement("h3"); h.textContent = `Grade ${fact.grade}`; panel.appendChild(h);
  const r = document.createElement("p"); r.textContent = fact.reason || ""; panel.appendChild(r);
  const dl = document.createElement("dl");
  const add = (k, v) => { const dt = document.createElement("dt"); dt.textContent = k; const dd = document.createElement("dd"); dd.textContent = v; dl.append(dt, dd); };
  const rng = fact.range && fact.range[gk];
  if (rng && rng.length === 2 && rng[0] !== rng[1]) add("Range across sources", `${formatValue(M, fact.metric, rng[0])} to ${formatValue(M, fact.metric, rng[1])}`);
  else if (fact.sources.length === 1) add("Range", "one source, no spread to show");
  add("Definition", fact.definition || "");
  if (fact.caveat) add("Caveat", fact.caveat);
  if (fact.n && fact.n_source) add("Group size from", fact.n_source_name || fact.n_source);
  panel.appendChild(dl);
  const wrap = document.createElement("div"); wrap.className = "table-scroll";
  const t = document.createElement("table"); t.className = "sources-table";
  t.innerHTML = "<thead><tr><th>Source</th><th>Measures</th><th class=\"num\">Value here</th><th>Accessed</th></tr></thead>";
  const tb = document.createElement("tbody");
  for (const s of fact.sources) {
    const tr = document.createElement("tr");
    const td1 = document.createElement("td"); const a = document.createElement("a"); a.href = s.url; a.textContent = s.name; a.rel = "noopener"; td1.appendChild(a);
    const td2 = document.createElement("td"); td2.textContent = s.measures || "";
    const td3 = document.createElement("td"); td3.className = "num"; const v = s.values && s.values[gk]; td3.textContent = v == null ? "-" : formatValue(M, fact.metric, v);
    const td4 = document.createElement("td"); td4.textContent = s.accessed || "";
    tr.append(td1, td2, td3, td4); tb.appendChild(tr);
  }
  t.appendChild(tb); wrap.appendChild(t); panel.appendChild(wrap);
}
function renderQueue(parsed) {
  const q = $("#queue");
  q.hidden = false;
  const near = slicesFor(state.metric).filter((s) => popMatches(s, state.pop, "age_band") || popMatches(s, state.pop, "country") || popMatches(s, state.pop, "sex")).slice(0, 4);
  $("#queue-text").textContent = parsed && parsed.unmatched && parsed.unmatched.metric
    ? `We don't have "${parsed.unmatched.metric}" as a measure.`
    : "This exact group has no fact yet.";
  $("#queue-near").textContent = near.length ? " Nearest groups with data: " + near.map((s) => groupName(M, s, state.metric, s.year)).join("; ") + "." : "";
}

// ---------- where do I land ----------
function cumulative(pk) { return parseFloat(pk.slice(1)) / 100; }
function placeValue(fact, v) {
  const keys = Object.keys(fact.grid).sort((a, b) => cumulative(a) - cumulative(b));
  const pts = keys.map((k) => [cumulative(k), fact.grid[k]]);
  const log = M.metrics[fact.metric].format === "money" && v > 0 && pts.every((p) => p[1] > 0);
  const tr = (x) => (log ? Math.log(x) : x);
  const asc = fact.direction === "high";
  const inside = (asc ? pts : pts.slice().reverse()).map((p) => [p[0], tr(p[1])]);
  const tv = tr(v);
  let lo = null, hi = null;
  for (let i = 0; i < inside.length - 1; i++) {
    const [c0, v0] = inside[i], [c1, v1] = inside[i + 1];
    if (tv >= Math.min(v0, v1) && tv <= Math.max(v0, v1)) { lo = [c0, v0]; hi = [c1, v1]; break; }
  }
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
function renderLand(fact) {
  const form = $("#land-form");
  form.hidden = Object.keys(fact.grid).length < 3;
  if (form.hidden) return;
  const m = M.metrics[fact.metric];
  $("#v-label").textContent = m.format === "money" ? "Your amount (USD)" : m.format.startsWith("time") ? "Your time (h:mm)" : m.format === "height" ? "Your height (cm or ft'in)" : m.format === "weight" ? "Your weight (kg or lb)" : `Your ${m.label.toLowerCase()}`;
  const stored = loadValues()[fact.metric];
  if (state.v == null && stored != null) state.v = stored;
  $("#v").value = state.v == null ? "" : rawToInput(fact, state.v);
  showPlacement(fact);
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
  if (fmt.startsWith("time") && (m = s.match(/^(\d{1,2}):(\d{2})(?::(\d{2}))?$/))) {
    if (m[3]) return (+m[1]) * 3600 + (+m[2]) * 60 + (+m[3]);
    return fmt === "time_hm" ? (+m[1]) * 3600 + (+m[2]) * 60 : (+m[1]) * 60 + (+m[2]);
  }
  if ((m = s.match(/^(\d+)\s*(?:ft|')\s*(\d{1,2})?/))) return ((+m[1]) * 12 + (m[2] ? +m[2] : 0)) * 2.54;
  if ((m = s.match(/^([\d.]+)\s*(lb|lbs)$/))) return (+m[1]) / 2.20462;
  if ((m = s.match(/^([\d.]+)\s*k$/))) return (+m[1]) * 1000;
  if ((m = s.match(/^([\d.]+)\s*(m|million)$/))) return (+m[1]) * 1e6;
  const n = parseFloat(s);
  return Number.isFinite(n) ? n : null;
}
function showPlacement(fact) {
  const out = $("#land-out");
  out.replaceChildren();
  if (state.v == null) return;
  const r = placeValue(fact, state.v);
  const v = formatValue(M, fact.metric, state.v);
  const b = document.createElement("b");
  if (r.kind === "beyond") { b.textContent = `top ${pctText(r.top)} or better`; out.append(`${v}: `, b, "; the data stops there."); }
  else if (r.kind === "below") { b.textContent = `below the ${pctText(r.bottom)} mark`; out.append(`${v}: `, b, "; the data stops there."); }
  else { b.textContent = `roughly top ${pctText(r.top)}`; out.append(`${v}: `, b, ` (between the top ${pctText(r.bandTop[0])} and top ${pctText(r.bandTop[1])} marks).`); }
}
function loadValues() { try { return JSON.parse(localStorage.getItem(LS_KEY) || "{}"); } catch { return {}; } }
function saveValue(metric, v) { try { const o = loadValues(); if (v == null) delete o[metric]; else o[metric] = v; localStorage.setItem(LS_KEY, JSON.stringify(o)); } catch { /* storage unavailable */ } }

// ---------- surprise ----------
function surprise() {
  const pool = Object.values(FACTS).filter((f) => f.grade === "A" || f.grade === "B");
  const recent = JSON.parse(sessionStorage.getItem("oih.recent") || "[]");
  // Favour whole-population facts (no age band, no category) so the surprise reads cleanly.
  const clean = pool.filter((f) => !f.population.age_band && !f.population.source_category && !recent.includes(f.id));
  const cand = clean.length ? clean : pool;
  const f = cand[Math.floor(Math.random() * cand.length)];
  sessionStorage.setItem("oih.recent", JSON.stringify([f.id, ...recent].slice(0, 8)));
  state.metric = f.metric; state.pop = { ...blankPop(), ...f.population }; delete state.pop.base;
  state.pct = ["p99", "p90", "p50"].find((k) => gridKeyFor(f.direction, k) in f.grid) || "p50"; state.v = null;
  update(true);
}

// ---------- typed questions ----------
async function ask(q) {
  const note = $("#ask-note");
  note.hidden = false; note.textContent = "Reading your question…";
  let parsed = null;
  if (WORKER) {
    try {
      const ctl = new AbortController(); const t = setTimeout(() => ctl.abort(), 2500);
      const r = await fetch(`${WORKER}/parse`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ q }), signal: ctl.signal });
      clearTimeout(t);
      const j = await r.json();
      if (j.ok) parsed = { ...j.triple, confidence: j.confidence, parser: "llm", unmatched: j.unmatched || {} };
    } catch { parsed = null; }
  }
  if (!parsed) parsed = parseRules(q, M);
  applyParsed(parsed);
  note.textContent = parsed.metric && slicesFor(parsed.metric).length
    ? `Understood as ${describeParsed(parsed)}.${parsed.confidence === "low" ? " Adjust the menus above if that's wrong." : ""}`
    : "Couldn't match that to a measure we have.";
}
function describeParsed(p) {
  const bits = [M.metrics[p.metric].label.toLowerCase()];
  if (p.population.country) bits.push(COUNTRY_SHORT[p.population.country]);
  if (p.population.sex !== "all") bits.push(p.population.sex === "m" ? "men" : "women");
  if (p.population.age_band) bits.push(ageBandPhrase(p.population.age_band));
  bits.push((M.percentiles[String(p.percentile)] || M.percentiles["99"]).label.toLowerCase());
  return bits.join(", ");
}
function inBand(b, age) {
  if (b.endsWith("+")) return age >= parseInt(b, 10);
  const [lo, hi] = b.split("-").map(Number);
  return age >= lo && age <= hi;
}
function snapAge(metric, pop) {
  if (!pop.age_band) return pop;
  const bands = optionsFor(metric, { ...pop, age_band: null }, "age_band").filter(Boolean);
  if (bands.includes(pop.age_band)) return pop;
  const lo = parseInt(pop.age_band, 10);
  return { ...pop, age_band: bands.find((b) => inBand(b, lo)) || null };
}
function applyParsed(p) {
  if (p.metric && M.metrics[p.metric] && slicesFor(p.metric).length) {
    state.metric = p.metric;
    let pop = { ...blankPop(), ...p.population }; delete pop.base;
    pop = snapAge(p.metric, pop);
    state.pop = reconcile(p.metric, pop);
    state.pct = PCT_KEYS.includes(`p${p.percentile}`) ? `p${p.percentile}` : "p99";
    state.v = p.value;
    update(true);
  } else {
    renderAnswer(null);
    renderQueue(p);
  }
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
  renderMetricSelect();
  renderGroupSelects();
  renderPct(fact);
  renderAnswer(fact);
  writeURL(push);
}

async function init() {
  await loadData();
  readURL();
  update(false);
  $("#sel-metric").addEventListener("change", (e) => {
    state.metric = e.target.value; state.v = null;
    state.pop = reconcile(state.metric, state.pop);
    update(true);
  });
  const dimOf = { "sel-country": "country", "sel-sex": "sex", "sel-age": "age_band", "sel-cat": "source_category" };
  for (const [id, dim] of Object.entries(dimOf)) {
    document.getElementById(id).addEventListener("change", (e) => {
      const v = e.target.value || (dim === "sex" ? "all" : null);
      state.pop = reconcile(state.metric, { ...state.pop, [dim]: v }, dim);
      state.v = null;
      update(true);
    });
  }
  $("#land-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const fact = findFact(state.metric, state.pop); if (!fact) return;
    const v = inputToRaw(fact, $("#v").value);
    if (v == null) { $("#land-out").textContent = "Couldn't read that value."; return; }
    state.v = v; saveValue(fact.metric, v); showPlacement(fact);
  });
  $("#ask-form").addEventListener("submit", (e) => { e.preventDefault(); const q = $("#q").value.trim(); if (q) ask(q); });
  $("#btn-surprise").addEventListener("click", surprise);
  $("#btn-link").addEventListener("click", shareLink);
  window.addEventListener("popstate", () => { readURL(); update(false); });
}
init().catch((e) => { $("#punchline").classList.remove("skeleton"); $("#punchline").textContent = "The data failed to load. Reload the page."; console.error(e); });
