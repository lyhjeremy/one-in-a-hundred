// Mirror of pipeline/format.py. pipeline/test_format.py checks both agree
// on eval/format_fixtures.json. Keep the two in step.

export const COUNTRY_NAMES = {
  US: "the United States", GB: "the United Kingdom", CA: "Canada", AU: "Australia",
  HK: "Hong Kong", SG: "Singapore", JP: "Japan", KR: "South Korea", DE: "Germany",
  FR: "France", NL: "the Netherlands", CH: "Switzerland", CN: "China", IN: "India",
  ID: "Indonesia", BR: "Brazil", NG: "Nigeria", MX: "Mexico", KE: "Kenya", ET: "Ethiopia",
};
export const COUNTRY_SHORT = {
  US: "United States", GB: "United Kingdom", CA: "Canada", AU: "Australia", HK: "Hong Kong",
  SG: "Singapore", JP: "Japan", KR: "South Korea", DE: "Germany", FR: "France", NL: "Netherlands",
  CH: "Switzerland", CN: "China", IN: "India", ID: "Indonesia", BR: "Brazil", NG: "Nigeria",
  MX: "Mexico", KE: "Kenya", ET: "Ethiopia",
};

export function sig2(x) {
  if (x === 0) return 0;
  const digits = 2 - Math.floor(Math.log10(Math.abs(x))) - 1;
  const f = Math.pow(10, digits);
  return Math.round(x * f) / f;
}
const g = (n) => Number(n.toPrecision(12)).toString();

export function formatCount(n) {
  n = sig2(n);
  if (n >= 1e9) return `about ${g(n / 1e9)} billion`;
  if (n >= 1e6) return `about ${g(n / 1e6)} million`;
  return `about ${Math.round(n).toLocaleString("en-US")}`;
}
export function formatMoney(v) {
  if (v < 0) return `-${formatMoney(-v)}`;
  if (v >= 1e6) return `$${g(sig2(v) / 1e6)} million`;
  return `$${Math.round(sig2(v)).toLocaleString("en-US")}`;
}
export function formatTimeHm(s) {
  const m = Math.round(s / 60);
  return `${Math.floor(m / 60)}:${String(m % 60).padStart(2, "0")}`;
}
export function formatTimeMs(s) {
  const t = Math.round(s / 15) * 15;
  return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`;
}
export function formatHeight(cm) {
  const totalIn = cm / 2.54;
  let ft = Math.floor(totalIn / 12);
  let inch = Math.round(totalIn - ft * 12);
  if (inch === 12) { ft += 1; inch = 0; }
  return `${Math.round(cm)} cm (${ft} ft ${inch} in)`;
}
export function formatWeight(kg) {
  return `${Math.round(kg)} kg (${Math.round(kg * 2.20462)} lb)`;
}
export const FORMATTERS = {
  money: formatMoney,
  time_hm: formatTimeHm,
  time_ms: formatTimeMs,
  height: formatHeight,
  weight: formatWeight,
  bmi: (v) => v.toFixed(1),
  years: (v) => String(Math.round(v)),
  years_1dp: (v) => `${v.toFixed(1)} years`,
  hours: (v) => `${Math.round(sig2(v)).toLocaleString("en-US")} hours`,
};

export function ageBandPhrase(band) {
  if (!band) return "";
  if (band.endsWith("+")) return `aged ${band.slice(0, -1)} and over`;
  const [lo, hi] = band.split("-");
  return `aged ${lo} to ${hi}`;
}

export function groupName(M, population, metricId, year) {
  const m = M.metrics[metricId];
  const sex = population.sex || "all";
  const baseNoun = m.base_noun || "people";
  const { activity, country, age_band: band, source_category: cat } = population;
  let noun;
  if (sex === "m") noun = "men";
  else if (sex === "f") noun = "women";
  else noun = (country || band || activity || cat) ? baseNoun : null;
  if (noun === null) {
    if (metricId === "age_years") return "everyone alive";
    return `all ${baseNoun} worldwide`;
  }
  const parts = [noun];
  if (cat) parts.push(`(${cat})`);
  if (band) parts.push(ageBandPhrase(band));
  if (country) parts.push(`in ${COUNTRY_NAMES[country] || country}`);
  if (activity) { parts.push(M.activities[activity].label); parts.push(`in ${year}`); }
  return parts.join(" ");
}

export function gridKeyFor(direction, pctKey) {
  if (direction === "high" || pctKey === "p50") return pctKey;
  return { p90: "p10", p99: "p1", "p99.9": "p0.1" }[pctKey];
}

export function stripArticle(p) {
  for (const a of ["an ", "a "]) if (p.startsWith(a)) return p.slice(a.length);
  return p;
}

export function formatValue(M, metricId, v) {
  return FORMATTERS[M.metrics[metricId].format](v);
}

// Returns {text, value} so the UI can wrap the value in <b>.
export function punchline(M, fact, pctKey) {
  const m = M.metrics[fact.metric];
  const pct = pctKey.slice(1);
  const gk = gridKeyFor(fact.direction, pctKey);
  const value = formatValue(M, fact.metric, fact.grid[gk]);
  const group = groupName(M, fact.population, fact.metric, fact.year);
  const tpl = M.templates[`${fact.direction}_${pct === "50" ? "median" : "top"}`];
  const top = M.percentiles[pct].top;
  let phrase = m.metric_phrase;
  if (pct === "50") phrase = stripArticle(phrase);
  const text = tpl.replace("{top}", top === null ? "" : g(top)).replace("{group}", group)
    .replace("{metric_phrase}", phrase).replace("{value}", value);
  return { text, value };
}
