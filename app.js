// One in a Hundred: the core screen. State lives in the URL; data is static.
import { punchline, groupName, formatCount, formatValue, gridKeyFor, COUNTRY_SHORT, ageBandPhrase } from "./format.js";
import { parseRules } from "./parser-rules.js";
import { renderCard } from "./cards.js";

const $ = (s) => document.querySelector(s);
const PCT_KEYS = ["p50", "p90", "p99", "p99.9"];
const WORKER = null; // set to the Worker origin when phase 3 ships; null = rules parser only
const LS_KEY = "oih.values";

let M, INDEX, FACTS = {}, THEMES = [];
const state = { metric: null, pop: blankPop(), pct: "p99", b: null, v: null, parser: null };

function blankPop() { return { country: null, sex: "all", age_band: null, activity: null, source_category: null }; }

// ---------- data ----------
async function loadData() {
  const [m, idx] = await Promise.all([fetch("data/metrics.json").then((r) => r.json()), fetch("data/index.json").then((r) => r.json())]);
  M = m; INDEX = idx;
  const fams = Object.keys(M.families);
  const files = await Promise.all(fams.map((f) => fetch(`data/facts/${f}.json`).then((r) => (r.ok ? r.json() : []))));
  for (const list of files) for (const f of list) FACTS[f.id] = f;
  try { THEMES = await fetch("data/themes.json").then((r) => (r.ok ? r.json() : [])); } catch { THEMES = []; }
  $("#built").textContent = INDEX.built || "";
}

function slicesFor(metric) { return (INDEX.metrics[metric] || { slices: [] }).slices; }
function popMatches(slice, pop, ignore = null) {
  for (const k of ["country", "sex", "age_band", "activity", "source_category"]) {
    if (k === ignore) continue;
    if ((slice[k] || null) !== (pop[k] || null)) return false;
  }
  return true;
}
function findFact(metric, pop) {
  const s = slicesFor(metric).find((x) => popMatches(x, pop));
  return s ? FACTS[s.id] : null;
}
function optionsFor(metric, pop, dim) {
  const vals = new Set();
  for (const s of slicesFor(metric)) if (popMatches(s, pop, dim) && s[dim]) vals.add(s[dim]);
  return [...vals];
}
function metricsWithData() { return Object.keys(M.metrics).filter((m) => slicesFor(m).length); }

// ---------- URL ----------
function readURL() {
  const u = new URLSearchParams(location.search);
  if (u.get("f") && FACTS[u.get("f")]) {
    const f = FACTS[u.get("f")];
    state.metric = f.metric; state.pop = { ...blankPop(), ...f.population }; delete state.pop.base;
  } else {
    state.metric = u.get("m") && M.metrics[u.get("m")] ? u.get("m") : null;
    state.pop = { country: u.get("c") || null, sex: u.get("s") || "all", age_band: u.get("a") || null,
      activity: u.get("act") || null, source_category: u.get("g") || null };
  }
  if (u.get("q") && M.percentiles[u.get("q")]) state.pct = `p${u.get("q")}`;
  if (u.get("bc") || u.get("bs") || u.get("ba") || u.get("b") === "1") {
    state.b = { country: u.get("bc") || null, sex: u.get("bs") || "all", age_band: u.get("ba") || null,
      activity: u.get("bact") || null, source_category: u.get("bg") || null };
  }
  if (u.get("v")) state.v = parseFloat(u.get("v"));
  if (!state.metric) {
    const avail = metricsWithData();
    state.metric = avail.includes("income_pretax_adult_ppp") ? "income_pretax_adult_ppp" : avail[0];
  }
  const act = M.metrics[state.metric].activity;
  if (act) state.pop.activity = act;
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
  if (state.b) {
    u.set("b", "1");
    if (state.b.country) u.set("bc", state.b.country);
    if (state.b.sex && state.b.sex !== "all") u.set("bs", state.b.sex);
    if (state.b.age_band) u.set("ba", state.b.age_band);
    if (state.b.source_category) u.set("bg", state.b.source_category);
  }
  const url = `${location.pathname}?${u.toString()}`;
  if (push) history.pushState(null, "", url); else history.replaceState(null, "", url);
}

// ---------- rendering ----------
function chip(label, pressed, onClick, extra = {}) {
  const b = document.createElement("button");
  b.type = "button"; b.className = "chip"; b.textContent = label;
  b.setAttribute("aria-pressed", pressed ? "true" : "false");
  if (extra.remove) b.classList.add("remove");
  if (extra.disabled) b.disabled = true;
  b.addEventListener("click", onClick);
  return b;
}
function sexLabel(s) { return s === "m" ? "Men" : s === "f" ? "Women" : "Everyone"; }
function dimLabel(dim, v) {
  if (dim === "country") return COUNTRY_SHORT[v] || v;
  if (dim === "sex") return sexLabel(v);
  if (dim === "age_band") return ageBandPhrase(v).replace(/^aged /, "Aged ");
  if (dim === "activity") return M.activities[v] ? M.activities[v].label.replace(/^who /, "Who ") : v;
  return v;
}

function renderPop(pop, container, narrowEl, onChange) {
  container.replaceChildren();
  const base = M.metrics[state.metric].base_noun || "people";
  container.appendChild(chip(pop.country || pop.sex !== "all" || pop.age_band || pop.source_category ? `All ${base}` : (state.metric === "age_years" ? "Everyone alive" : `All ${base} worldwide`), true, () => {
    onChange({ ...blankPop(), activity: pop.activity });
  }));
  for (const dim of ["country", "sex", "age_band", "source_category"]) {
    const v = pop[dim];
    if (!v || (dim === "sex" && v === "all")) continue;
    container.appendChild(chip(dimLabel(dim, v), true, () => onChange({ ...pop, [dim]: dim === "sex" ? "all" : null }), { remove: true }));
  }
  narrowEl.replaceChildren();
  const dims = [["country", "Country"], ["sex", "Sex"], ["age_band", "Age"], ["source_category", "Category (as published by the source)"]];
  for (const [dim, label] of dims) {
    const opts = optionsFor(state.metric, pop, dim).filter((o) => o !== pop[dim] && !(dim === "sex" && o === "all"));
    if (!opts.length) continue;
    const sel = document.createElement("select");
    sel.setAttribute("aria-label", `Narrow by ${label}`);
    const o0 = document.createElement("option"); o0.value = ""; o0.textContent = `Narrow by ${label.toLowerCase()}`; sel.appendChild(o0);
    const sorted = dim === "country" ? opts.sort((a, b) => dimLabel(dim, a).localeCompare(dimLabel(dim, b))) : opts.sort((a, b) => (dim === "age_band" ? parseInt(a) - parseInt(b) : a.localeCompare(b)));
    for (const o of sorted) { const op = document.createElement("option"); op.value = o; op.textContent = dimLabel(dim, o); sel.appendChild(op); }
    sel.addEventListener("change", () => { if (sel.value) onChange({ ...pop, [dim]: sel.value }); });
    narrowEl.appendChild(sel);
  }
}

function renderMetrics() {
  const fams = $("#family-chips"), mets = $("#metric-chips");
  fams.replaceChildren(); mets.replaceChildren();
  const avail = metricsWithData();
  const curFam = M.metrics[state.metric].family;
  for (const [fid, f] of Object.entries(M.families).sort((a, b) => a[1].order - b[1].order)) {
    const has = avail.some((m) => M.metrics[m].family === fid);
    fams.appendChild(chip(f.label, fid === curFam, () => {
      const first = avail.find((m) => M.metrics[m].family === fid);
      if (first) setMetric(first);
    }, { disabled: !has }));
  }
  for (const mid of avail.filter((m) => M.metrics[m].family === curFam)) {
    mets.appendChild(chip(M.metrics[mid].label, mid === state.metric, () => setMetric(mid)));
  }
}

function renderPct(fact) {
  const el = $("#pct-chips");
  el.replaceChildren();
  for (const pk of PCT_KEYS) {
    const has = fact ? gridKeyFor(fact.direction, pk) in fact.grid : true;
    el.appendChild(chip(M.percentiles[pk.slice(1)].label, pk === state.pct, () => { state.pct = pk; update(true); }, { disabled: !has }));
  }
}

function gradeTag(f) {
  const s = document.createElement("span");
  s.className = `grade${f.grade === "D" ? " d" : ""}`;
  s.textContent = f.grade === "D" ? "Grade D, unreviewed" : `Grade ${f.grade}`;
  return s;
}

function renderAnswer(fact) {
  const pl = $("#punchline"), sub = $("#subline"), panel = $("#panel");
  pl.classList.remove("skeleton", "skeleton--title");
  if (!fact) {
    pl.classList.add("empty");
    pl.textContent = "No data for this group yet.";
    sub.textContent = "";
    panel.hidden = true;
    $("#land").hidden = true;
    renderQueue(null);
    return;
  }
  $("#queue").hidden = true;
  pl.classList.remove("empty");
  const { text, value } = punchline(M, fact, state.pct);
  const i = text.lastIndexOf(value);
  pl.replaceChildren();
  pl.append(text.slice(0, i));
  const b = document.createElement("b"); b.textContent = value; pl.appendChild(b);
  pl.append(text.slice(i + value.length));

  sub.replaceChildren();
  sub.appendChild(gradeTag(fact));
  const bits = [];
  if (fact.n) {
    const top = { p50: 0.5, p90: 0.1, p99: 0.01, "p99.9": 0.001 }[state.pct];
    bits.push(state.pct === "p50" ? `${formatCount(fact.n)} people in the group` : `that's ${formatCount(fact.n * top)} people`);
  }
  bits.push(`reference year ${fact.year}`);
  sub.append(bits.join(" · ") + " · ");
  const why = document.createElement("button"); why.type = "button"; why.textContent = panel.hidden ? "Why this grade?" : "Hide sources";
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
  const near = slicesFor(state.metric).filter((s) => popMatches(s, state.pop, "age_band") || popMatches(s, state.pop, "country") || popMatches(s, state.pop, "sex")).slice(0, 6);
  $("#queue-text").textContent = parsed && parsed.unmatched && parsed.unmatched.metric
    ? `We don't have "${parsed.unmatched.metric}" as a measure.`
    : "This exact group has no fact yet.";
  $("#queue-near").textContent = near.length ? "Nearest groups with data: " + near.map((s) => groupName(M, s, state.metric, s.year)).join("; ") + "." : "";
  const btn = $("#btn-queue");
  btn.hidden = !WORKER;
  $("#queue-out").textContent = WORKER ? "" : "Queuing opens when the question service is live; until then, this gap is logged by hand from the request list.";
}

// ---------- where do I land ----------
function cumulative(pk) { return parseFloat(pk.slice(1)) / 100; }
function placeValue(fact, v) {
  const keys = Object.keys(fact.grid).sort((a, b) => cumulative(a) - cumulative(b));
  const pts = keys.map((k) => [cumulative(k), fact.grid[k]]);
  const log = M.metrics[fact.metric].format === "money" && v > 0 && pts.every((p) => p[1] > 0);
  const tr = (x) => (log ? Math.log(x) : x);
  const asc = fact.direction === "high";
  // For 'high' metrics value rises with cumulative share; for 'low' it falls.
  const ordered = asc ? pts : pts.slice().reverse();
  const inside = ordered.map((p) => [p[0], tr(p[1])]);
  const tv = tr(v);
  let lo = null, hi = null;
  for (let i = 0; i < inside.length - 1; i++) {
    const [c0, v0] = inside[i], [c1, v1] = inside[i + 1];
    if ((tv >= Math.min(v0, v1) && tv <= Math.max(v0, v1))) { lo = [c0, v0]; hi = [c1, v1]; break; }
  }
  const topShare = (c) => (asc ? 1 - c : c);
  if (!lo) {
    const first = inside[0], last = inside[inside.length - 1];
    const beyondTop = asc ? tv > last[1] : tv < first[1];
    if (beyondTop) { const edge = asc ? last[0] : first[0]; return { kind: "beyond", top: topShare(edge) }; }
    const edge = asc ? first[0] : last[0];
    return { kind: "below", bottom: edge };
  }
  const f = hi[1] === lo[1] ? 0 : (tv - lo[1]) / (hi[1] - lo[1]);
  const c = lo[0] + f * (hi[0] - lo[0]);
  return { kind: "between", top: topShare(c), bandTop: [topShare(lo[0]), topShare(hi[0])].sort((a, b) => a - b) };
}
function pctText(x) { return x < 0.01 ? `${(x * 100).toFixed(1)}%` : `${Math.round(x * 100)}%`; }
function renderLand(fact) {
  const sec = $("#land");
  const keys = Object.keys(fact.grid);
  sec.hidden = keys.length < 3;
  if (sec.hidden) return;
  const m = M.metrics[fact.metric];
  $("#v-label").textContent = `Your ${m.format === "money" ? "amount in US dollars" : m.format.startsWith("time") ? "time (h:mm or mm:ss)" : m.format === "height" ? "height (cm, or ft'in)" : m.format === "weight" ? "weight (kg or lb)" : m.label.toLowerCase()}`;
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
  const group = groupName(M, fact.population, fact.metric, fact.year);
  const v = formatValue(M, fact.metric, state.v);
  const b = document.createElement("b");
  if (r.kind === "beyond") { b.textContent = `top ${pctText(r.top)} or better`; out.append(`${v} puts you in the `, b, ` of ${group}; the data stops there.`); }
  else if (r.kind === "below") { b.textContent = `below the ${pctText(r.bottom)} mark`; out.append(`${v} is `, b, ` for ${group}; the data stops there.`); }
  else { b.textContent = `roughly top ${pctText(r.top)}`; out.append(`${v} puts you `, b, ` of ${group} (between the top ${pctText(r.bandTop[0])} and top ${pctText(r.bandTop[1])} marks).`); }
  $("#btn-card").dataset.custom = "1";
}
function loadValues() { try { return JSON.parse(localStorage.getItem(LS_KEY) || "{}"); } catch { return {}; } }
function saveValue(metric, v) { try { const o = loadValues(); if (v == null) delete o[metric]; else o[metric] = v; localStorage.setItem(LS_KEY, JSON.stringify(o)); } catch { /* storage unavailable */ } }

// ---------- compare ----------
function renderCompare(factA) {
  const wrap = $("#compare-wrap");
  if (!state.b) { wrap.hidden = true; $("#btn-compare").textContent = "Compare with another group"; return; }
  wrap.hidden = false;
  $("#btn-compare").textContent = "Stop comparing";
  const left = wrap.children[0], right = $("#compare-b");
  left.replaceChildren(); right.replaceChildren();
  const hA = document.createElement("p"); hA.className = "colhead"; hA.textContent = "This group"; left.appendChild(hA);
  const pA = document.createElement("p"); pA.className = "punchline"; pA.textContent = factA ? punchline(M, factA, state.pct).text : "No data."; left.appendChild(pA);
  const hB = document.createElement("p"); hB.className = "colhead"; hB.textContent = "Compared with"; right.appendChild(hB);
  const chips = document.createElement("div"); chips.className = "chips"; const narrow = document.createElement("div"); narrow.className = "narrow";
  right.append(chips, narrow);
  renderPop(state.b, chips, narrow, (np) => { state.b = np; update(true); });
  const factB = findFact(state.metric, state.b);
  const pB = document.createElement("p"); pB.className = "punchline";
  if (factB) { pB.textContent = punchline(M, factB, state.pct).text; right.appendChild(pB); const s = document.createElement("p"); s.className = "subline"; s.appendChild(gradeTag(factB)); s.append(` reference year ${factB.year}`); right.appendChild(s); }
  else { pB.textContent = "No data for that group."; pB.classList.add("empty"); right.appendChild(pB); }
}

// ---------- theme and surprise ----------
function renderToday() {
  if (!THEMES.length) return;
  const days = Math.floor((Date.now() - Date.UTC(2026, 10, 1)) / 86400000);
  const t = THEMES[((days % THEMES.length) + THEMES.length) % THEMES.length];
  const f = FACTS[t.id];
  if (!f) return;
  $("#today").hidden = false;
  const pk = ["p99", "p90", "p50"].find((k) => gridKeyFor(f.direction, k) in f.grid);
  $("#today-text").textContent = punchline(M, f, pk).text;
  $("#today-note").textContent = `${t.note || ""} Grade ${f.grade}.`;
  $("#today-text").style.cursor = "pointer";
  $("#today-text").onclick = () => gotoFact(f, pk);
}
function surprise() {
  const pool = Object.values(FACTS).filter((f) => (f.grade === "A" || f.grade === "B"));
  const flagged = pool.filter((f) => f.surprising);
  const recent = JSON.parse(sessionStorage.getItem("oih.recent") || "[]");
  const cand = (flagged.length ? flagged : pool).filter((f) => !recent.includes(f.id));
  const f = cand[Math.floor(Math.random() * cand.length)] || pool[0];
  sessionStorage.setItem("oih.recent", JSON.stringify([f.id, ...recent].slice(0, 5)));
  const pk = ["p99", "p90", "p50"].find((k) => gridKeyFor(f.direction, k) in f.grid);
  gotoFact(f, pk);
}
function gotoFact(f, pk) {
  state.metric = f.metric; state.pop = { ...blankPop(), ...f.population }; delete state.pop.base; state.pct = pk || "p99"; state.b = null; state.v = null;
  update(true);
  $("#answer").scrollIntoView({ behavior: "auto", block: "start" });
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
  const how = parsed.parser === "llm" ? "" : WORKER ? " Understood by the simple parser; the usual one is unavailable." : "";
  note.textContent = (parsed.metric ? `Understood as: ${describeParsed(parsed)}.` : "Couldn't match that to a measure we have.") + how + (parsed.confidence === "low" ? " Check the chips below and fix anything wrong." : "");
}
function describeParsed(p) {
  const bits = [M.metrics[p.metric].label.toLowerCase()];
  if (p.population.country) bits.push(COUNTRY_SHORT[p.population.country]);
  if (p.population.sex !== "all") bits.push(sexLabel(p.population.sex).toLowerCase());
  if (p.population.age_band) bits.push(ageBandPhrase(p.population.age_band));
  bits.push(M.percentiles[String(p.percentile)].label.toLowerCase());
  return bits.join(", ");
}
function snapAge(metric, pop) {
  if (!pop.age_band || pop.age_band.includes("-") || pop.age_band.endsWith("+")) {
    // A band typed exactly, or a decade: snap to an existing band that overlaps.
    if (!pop.age_band) return pop;
    const bands = optionsFor(metric, { ...pop, age_band: null }, "age_band");
    if (bands.includes(pop.age_band)) return pop;
    const lo = parseInt(pop.age_band, 10);
    const hit = bands.find((b) => inBand(b, lo));
    return { ...pop, age_band: hit || null };
  }
  const age = parseInt(pop.age_band, 10);
  const bands = optionsFor(metric, { ...pop, age_band: null }, "age_band");
  const hit = bands.find((b) => inBand(b, age));
  return { ...pop, age_band: hit || null };
}
function inBand(b, age) {
  if (b.endsWith("+")) return age >= parseInt(b, 10);
  const [lo, hi] = b.split("-").map(Number);
  return age >= lo && age <= hi;
}
function applyParsed(p) {
  if (p.metric && M.metrics[p.metric] && slicesFor(p.metric).length) {
    state.metric = p.metric;
    let pop = { ...blankPop(), ...p.population }; delete pop.base;
    const act = M.metrics[p.metric].activity; if (act) pop.activity = act;
    pop = snapAge(p.metric, pop);
    state.pop = pop;
    state.pct = `p${p.percentile}`;
    state.v = p.value;
    state.b = null;
    update(true);
    if (!findFact(state.metric, state.pop)) renderQueue(p);
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
async function customCard() {
  const fact = findFact(state.metric, state.pop);
  if (!fact || state.v == null) return null;
  const r = placeValue(fact, state.v);
  const group = groupName(M, fact.population, fact.metric, fact.year);
  const v = formatValue(M, fact.metric, state.v);
  const head = r.kind === "between" ? `${v} puts me in roughly the top ${pctText(r.top)} of ${group}.` : r.kind === "beyond" ? `${v} puts me in the top ${pctText(r.top)} or better of ${group}.` : `${v} is below the ${pctText(r.bottom)} mark for ${group}.`;
  return renderCard({ headline: head, subline: `Reference year ${fact.year}. Grade ${fact.grade}. Compared against ${fact.sources.map((s) => s.name).join("; ")}.`, grade: fact.grade, stamp: fact.status === "queued" ? "UNREVIEWED" : null });
}

// ---------- orchestration ----------
function setMetric(mid) {
  state.metric = mid;
  const act = M.metrics[mid].activity || null;
  const keep = { ...state.pop, activity: act };
  // Drop dims the new metric has no data for.
  for (const dim of ["country", "sex", "age_band", "source_category"]) {
    const v = keep[dim]; if (!v || (dim === "sex" && v === "all")) continue;
    if (!slicesFor(mid).some((s) => (s[dim] || null) === v)) keep[dim] = dim === "sex" ? "all" : null;
  }
  state.pop = keep; state.v = null;
  if (state.b) { state.b = { ...state.b, activity: act }; }
  update(true);
}
function update(push = false) {
  const fact = findFact(state.metric, state.pop);
  if (fact && !(gridKeyFor(fact.direction, state.pct) in fact.grid)) state.pct = PCT_KEYS.find((k) => gridKeyFor(fact.direction, k) in fact.grid) || "p50";
  renderMetrics();
  renderPop(state.pop, $("#pop-chips"), $("#pop-narrow"), (np) => { state.pop = np; state.v = null; update(true); });
  $("#pop-count").textContent = fact && fact.n ? `${formatCount(fact.n)} people in this group (count from ${fact.n_source_name || fact.n_source || "the source in the panel"})` : "";
  renderPct(fact);
  $("#panel").hidden = true;
  renderAnswer(fact);
  renderCompare(fact);
  writeURL(push);
}

async function init() {
  await loadData();
  readURL();
  update(false);
  renderToday();
  $("#ask-form").addEventListener("submit", (e) => { e.preventDefault(); const q = $("#q").value.trim(); if (q) ask(q); });
  $("#land-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const fact = findFact(state.metric, state.pop); if (!fact) return;
    const v = inputToRaw(fact, $("#v").value);
    if (v == null) { $("#land-out").textContent = "Couldn't read that value."; return; }
    state.v = v; saveValue(fact.metric, v); showPlacement(fact);
  });
  $("#v-clear").addEventListener("click", () => { const fact = findFact(state.metric, state.pop); state.v = null; $("#v").value = ""; $("#land-out").replaceChildren(); if (fact) saveValue(fact.metric, null); delete $("#btn-card").dataset.custom; });
  $("#btn-compare").addEventListener("click", () => {
    // Start the comparison from the same sex (and activity) as the main group so
    // metrics that only exist per sex, like height, show something immediately.
    state.b = state.b ? null : { ...blankPop(), sex: state.pop.sex, activity: state.pop.activity };
    update(true);
  });
  $("#btn-surprise").addEventListener("click", surprise);
  $("#btn-link").addEventListener("click", shareLink);
  $("#btn-card").addEventListener("click", async (e) => {
    if (!$("#btn-card").dataset.custom || state.v == null) return;
    e.preventDefault();
    const blob = await customCard(); if (!blob) return;
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = "where-i-land.png"; a.click();
  });
  if (navigator.share) {
    $("#btn-share").hidden = false;
    $("#btn-share").addEventListener("click", async () => {
      const fact = findFact(state.metric, state.pop); if (!fact) return;
      const url = `${location.origin}${location.pathname.replace(/[^/]*$/, "")}f/${fact.id}/`;
      try { await navigator.share({ title: "One in a Hundred", text: punchline(M, fact, state.pct).text, url }); } catch { /* cancelled */ }
    });
  }
  window.addEventListener("popstate", () => { readURL(); update(false); });
}
init().catch((e) => { $("#punchline").classList.remove("skeleton"); $("#punchline").textContent = "The data failed to load. Reload the page."; console.error(e); });
