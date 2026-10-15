// Rules parser: a typed question -> {metric, population, percentile, value, unmatched, confidence}.
// Deterministic, no dependencies, never throws. Runs in the browser as the
// fallback for the LLM parser and in Node as the eval baseline.

const SEX_F = ["women", "woman", "female", "females", "girls", "girl", "ladies", "lady"];
const SEX_M = ["men", "man", "male", "males", "boys", "boy", "guys", "guy", "gentlemen"];

const COUNTRIES = {
  US: ["united states", "usa", "u.s.", "us", "america", "american", "americans"],
  GB: ["united kingdom", "uk", "u.k.", "britain", "british", "brits", "england", "english", "london", "londoners", "scotland", "wales"],
  CA: ["canada", "canadian", "canadians", "toronto", "vancouver"],
  AU: ["australia", "australian", "australians", "aussie", "aussies", "sydney", "melbourne"],
  HK: ["hong kong", "hongkong", "hongkonger", "hongkongers", "hk"],
  SG: ["singapore", "singaporean", "singaporeans"],
  JP: ["japan", "japanese", "tokyo"],
  KR: ["south korea", "korea", "korean", "koreans", "seoul"],
  DE: ["germany", "german", "germans", "berlin", "munich"],
  FR: ["france", "french", "paris", "parisian", "parisians"],
  NL: ["netherlands", "holland", "dutch", "amsterdam"],
  CH: ["switzerland", "swiss", "zurich", "geneva"],
  CN: ["china", "chinese", "beijing", "shanghai"],
  IN: ["india", "indian", "indians", "mumbai", "delhi"],
  ID: ["indonesia", "indonesian", "indonesians", "jakarta"],
  BR: ["brazil", "brazilian", "brazilians", "sao paulo", "rio"],
  NG: ["nigeria", "nigerian", "nigerians", "lagos"],
  MX: ["mexico", "mexican", "mexicans", "mexico city"],
  KE: ["kenya", "kenyan", "kenyans", "nairobi"],
  ET: ["ethiopia", "ethiopian", "ethiopians", "addis"],
};
const CITY_TERMS = new Set(["london", "londoners", "toronto", "vancouver", "sydney", "melbourne", "tokyo", "seoul", "berlin", "munich", "paris", "parisian", "parisians", "amsterdam", "zurich", "geneva", "beijing", "shanghai", "mumbai", "delhi", "jakarta", "sao paulo", "rio", "lagos", "mexico city", "nairobi", "addis"]);

const DECADES = { twenties: "20-29", thirties: "30-39", forties: "40-49", fifties: "50-59", sixties: "60-69", seventies: "70-79" };

export function normalise(q) {
  return (q || "").toLowerCase().replace(/[’']/g, "").replace(/[^a-z0-9%$:.\-\s]/g, " ").replace(/\s+/g, " ").trim();
}

function bigrams(s) {
  const out = new Map();
  for (let i = 0; i < s.length - 1; i++) { const b = s.slice(i, i + 2); out.set(b, (out.get(b) || 0) + 1); }
  return out;
}
function dice(a, b) {
  const A = bigrams(a), B = bigrams(b);
  let inter = 0;
  for (const [k, v] of A) if (B.has(k)) inter += Math.min(v, B.get(k));
  const tot = [...A.values()].reduce((x, y) => x + y, 0) + [...B.values()].reduce((x, y) => x + y, 0);
  return tot ? (2 * inter) / tot : 0;
}

export function parseRules(question, M) {
  const out = {
    metric: null,
    population: { base: "world", country: null, sex: "all", age_band: null, activity: null, source_category: null },
    percentile: 99, value: null,
    unmatched: { metric: null, country: null, activity: null },
    confidence: "high", parser: "rules", notes: [],
  };
  try {
    let q = normalise(question);
    if (!q) { out.confidence = "low"; return out; }
    let rest = ` ${q} `;

    // Percentile
    let m;
    if ((m = q.match(/(?:top|oldest|tallest|richest|fastest|heaviest|wealthiest|best|highest|biggest)\s*(\d+(?:\.\d+)?)\s*(?:%|percent|per cent)/))) { out.percentile = pctFromTop(parseFloat(m[1])); rest = rest.replace(m[0], " "); }
    else if ((m = q.match(/(?:top|oldest|tallest|richest|fastest|heaviest|wealthiest|best)\s*(one|ten)\s*(?:%|percent|per cent)/))) { out.percentile = m[1] === "one" ? 99 : 90; rest = rest.replace(m[0], " "); }
    else if ((m = q.match(/(\d+(?:\.\d+)?)(?:st|nd|rd|th)\s*percentile/))) { out.percentile = snapPct(parseFloat(m[1])); rest = rest.replace(m[0], " "); }
    else if ((m = q.match(/\b(?:1|one) in (\d+)\b/))) { out.percentile = pctFromTop(100 / parseInt(m[1], 10)); rest = rest.replace(m[0], " "); }
    else if (/\b(one|1)\s*percent\b/.test(q) || /\btop 1\b/.test(q)) { out.percentile = 99; }
    else if (/\b(median|average|avg|typical|normal|usual|mean|ordinary)\b/.test(q)) { out.percentile = 50; rest = rest.replace(/\b(median|average|avg|typical|normal|usual|mean|ordinary)\b/, " "); }
    else if (/\b(top|elite|best|richest|tallest|fastest|oldest|wealthiest)\b/.test(q)) { out.percentile = 99; }
    else { out.percentile = 99; out.confidence = "low"; out.notes.push("no percentile stated; assumed top 1%"); }

    // Sex
    for (const w of SEX_F) if (new RegExp(`\\b${w}\\b`).test(rest)) { out.population.sex = "f"; rest = rest.replace(new RegExp(`\\b${w}\\b`), " "); break; }
    if (out.population.sex === "all") for (const w of SEX_M) if (new RegExp(`\\b${w}\\b`).test(rest)) { out.population.sex = "m"; rest = rest.replace(new RegExp(`\\b${w}\\b`), " "); break; }

    // Age
    if ((m = rest.match(/\b(\d{2})\s*(?:to|-)\s*(\d{2})\b(?!\s*(?:%|:|k))/))) { out.population.age_band = `${m[1]}-${m[2]}`; rest = rest.replace(m[0], " "); }
    else if ((m = rest.match(/\b(\d{2})[\s-]*(?:year[\s-]*olds?|yo|y\/o|yrs? old|years of age)\b/))) { out.population.age_band = m[1]; rest = rest.replace(m[0], " "); }
    else if ((m = rest.match(/\b(?:aged?|age of)\s*(\d{2})\b/))) { out.population.age_band = m[1]; rest = rest.replace(m[0], " "); }
    else if ((m = rest.match(/\bin (?:my|their|his|her|your) (twenties|thirties|forties|fifties|sixties|seventies)\b/))) { out.population.age_band = DECADES[m[1]]; rest = rest.replace(m[0], " "); }
    else if ((m = rest.match(/\bin (?:my|their|his|her|your) ([2-7]0)s\b/))) { out.population.age_band = `${m[1]}-${parseInt(m[1], 10) + 9}`; rest = rest.replace(m[0], " "); }
    else if ((m = rest.match(/\b(?:over|above|older than)\s*(\d{2})\b/))) { out.population.age_band = `${m[1]}+`; rest = rest.replace(m[0], " "); }
    else if ((m = rest.match(/\b(?:as an?|im|i am|being an?)\s+(\d{2})\b/))) { out.population.age_band = m[1]; rest = rest.replace(m[0], " "); }

    // Country (longest alias first)
    const aliases = [];
    for (const [cc, list] of Object.entries(COUNTRIES)) for (const a of list) aliases.push([a, cc]);
    aliases.sort((x, y) => y[0].length - x[0].length);
    for (const [a, cc] of aliases) {
      const re = new RegExp(`(^|\\s)${a.replace(/\./g, "\\.")}(?=\\s|$)`);
      if (re.test(rest)) {
        out.population.country = cc; out.population.base = "country";
        if (CITY_TERMS.has(a)) out.notes.push("city resolved to country");
        rest = rest.replace(re, " ");
        break;
      }
    }

    // Value with unit
    if ((m = rest.match(/\b(\d{1,2}):(\d{2})(?::(\d{2}))?\b/))) {
      out.value = parseInt(m[1], 10) * 3600 + parseInt(m[2], 10) * 60 + (m[3] ? parseInt(m[3], 10) : 0);
      if (!m[3] && parseInt(m[1], 10) > 9) out.value = parseInt(m[1], 10) * 60 + parseInt(m[2], 10); // mm:ss
      out.notes.push("value: time"); rest = rest.replace(m[0], " ");
    } else if ((m = rest.match(/\$\s?(\d[\d,]*(?:\.\d+)?)\s*(k|m|million)?\b/))) {
      let v = parseFloat(m[1].replace(/,/g, ""));
      if (m[2] === "k") v *= 1e3; if (m[2] === "m" || m[2] === "million") v *= 1e6;
      out.value = v; out.notes.push("value: money"); rest = rest.replace(m[0], " ");
    } else if ((m = rest.match(/\b(\d{2,3}(?:\.\d+)?)\s*cm\b/))) { out.value = parseFloat(m[1]); out.notes.push("value: cm"); rest = rest.replace(m[0], " "); }
    else if ((m = rest.match(/\b(\d)\s*(?:ft|foot|feet|')\s*(\d{1,2})?\s*(?:in|inch|inches|")?\b/))) { out.value = Math.round((parseInt(m[1], 10) * 12 + (m[2] ? parseInt(m[2], 10) : 0)) * 2.54 * 10) / 10; out.notes.push("value: feet"); rest = rest.replace(m[0], " "); }
    else if ((m = rest.match(/\b(\d{2,3}(?:\.\d+)?)\s*(kg|kilos?|kilograms?)\b/))) { out.value = parseFloat(m[1]); out.notes.push("value: kg"); rest = rest.replace(m[0], " "); }
    else if ((m = rest.match(/\b(\d{2,3}(?:\.\d+)?)\s*(lb|lbs|pounds?)\b/))) { out.value = Math.round(parseFloat(m[1]) / 2.20462 * 10) / 10; out.notes.push("value: lb"); rest = rest.replace(m[0], " "); }

    // Metric: phrasing hits, then fuzzy on the leftover words.
    let best = null, bestScore = 0;
    for (const [id, md] of Object.entries(M.metrics)) {
      let score = 0;
      for (const p of md.phrasings) {
        // A phrasing matches its own inflections too: marathon -> marathoners, earn -> earners, run -> running.
        const re = new RegExp(`(^|\\s)${p.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(?:s|es|er|ers|ner|ners|ing|ed)?(?=\\s|$)`);
        if (re.test(rest)) score = Math.max(score, 1 + p.length / 40);
      }
      if (!score) for (const p of md.phrasings) score = Math.max(score, dice(rest.trim(), p) * 0.9);
      if (score > bestScore) { bestScore = score; best = id; }
    }
    if (best && bestScore >= 0.5) {
      out.metric = best;
      if (bestScore < 1) { out.confidence = "low"; out.notes.push("metric matched fuzzily"); }
      const act = M.metrics[best].activity;
      if (act) out.population.activity = act;
    } else {
      out.confidence = "low";
      const leftover = rest.replace(/\b(how|what|whats|is|are|do|does|i|to|be|the|a|an|of|in|for|need|needed|have|has|you|it|me|my|at|on|and|or|that|this|get|into|much|many|would|should|could|who|which|top|percent|percentile|group|among)\b/g, " ").replace(/\s+/g, " ").trim();
      out.unmatched.metric = leftover || null;
    }
    return out;
  } catch (e) {
    out.confidence = "low"; out.notes.push("parser error");
    return out;
  }
}

function pctFromTop(top) {
  if (top <= 0.3) return 99.9;
  if (top <= 3) return 99;
  if (top <= 25) return 90;
  return 50;
}
function snapPct(p) {
  if (p >= 99.5) return 99.9;
  if (p >= 95) return 99;
  if (p >= 75) return 90;
  return 50;
}
