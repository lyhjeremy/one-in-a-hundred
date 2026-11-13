// Semantic parser: embeds a typed question with MiniLM in the browser and finds
// the nearest canonical phrasing of each measure (data/semantic_index.json).
// The slots (country, sex, age, percentile, value) still come from the rules
// parser; the embedding only chooses the measure, or abstains.
//
// Everything is self-hosted under assets/ai/. env.allowRemoteModels is false,
// so the page never asks Hugging Face or a CDN for anything. The model is only
// loaded when loadModel() is called, which the page does on an explicit click.

import { parseRules } from "./parser-rules.js";

// Settings chosen on the dev split (eval/semantic/dev.jsonl) by
// eval/semantic/eval_semantic.py; the frozen gold set was not used.
export const DEFAULTS = { input: "residual", tauEmbed: 0.525, tauHybrid: 0.525, margin: 0, trustRules: 1, keepFuzzy: false, override: 0.6 };

export function decodeIndex(json) {
  const bin = typeof atob === "function" ? atob(json.q8) : Buffer.from(json.q8, "base64").toString("binary");
  const n = json.entries.length, d = json.dim;
  const vecs = new Float32Array(n * d);
  for (let i = 0; i < n; i++) {
    let norm = 0;
    for (let j = 0; j < d; j++) {
      let b = bin.charCodeAt(i * d + j); if (b > 127) b -= 256;
      vecs[i * d + j] = b; norm += b * b;
    }
    norm = Math.sqrt(norm) || 1;
    for (let j = 0; j < d; j++) vecs[i * d + j] /= norm;
  }
  return { entries: json.entries, dim: d, vecs, model: json.model };
}

// Best cosine per measure, highest first. `allow` limits the catalogue (the
// eval passes the core ids so it scores against the same set as the rules parser).
export function rankMetrics(index, qvec, allow = null) {
  const best = new Map();
  const d = index.dim;
  for (let i = 0; i < index.entries.length; i++) {
    const e = index.entries[i];
    if (allow && !allow.has(e.m)) continue;
    let s = 0;
    for (let j = 0; j < d; j++) s += index.vecs[i * d + j] * qvec[j];
    const cur = best.get(e.m);
    if (!cur || s > cur.score) best.set(e.m, { metric: e.m, score: s, text: e.t });
  }
  return [...best.values()].sort((a, b) => b.score - a.score);
}

// The text that gets embedded for a question.
export function embedText(question, rules, cfg = DEFAULTS) {
  if (cfg.input === "full") return (question || "").trim();
  return (rules.residual || "").trim() || (question || "").trim();
}

// Combine a rules parse with the ranked measures.
// mode "embed": the measure comes from the embedding alone.
// mode "hybrid": a rules phrasing hit (metric_score >= trustRules) is kept unless
// the embedding clears `override` for another measure; otherwise the embedding answers if it clears tauHybrid, else the parser abstains.
export function combine(rules, ranked, M, mode = "hybrid", cfg = DEFAULTS) {
  const out = { ...rules, population: { ...rules.population }, unmatched: { ...rules.unmatched }, notes: [...(rules.notes || [])] };
  const top = ranked && ranked[0];
  const second = ranked && ranked[1];
  const margin = top && second ? top.score - second.score : 1;
  const tau = mode === "embed" ? cfg.tauEmbed : cfg.tauHybrid;
  const embedOk = !!top && top.score >= tau && margin >= cfg.margin;
  out.semantic = top ? { metric: top.metric, score: Math.round(top.score * 1000) / 1000, text: top.text, margin: Math.round(margin * 1000) / 1000, accepted: false } : null;

  const rulesTrusted = rules.metric && (rules.metric_score || 0) >= cfg.trustRules;
  // override > 0: a rules phrasing hit gives way when the embedding names a
  // different measure with at least this cosine.
  const overrides = cfg.override > 0 && embedOk && top.metric !== rules.metric && top.score >= cfg.override;
  if (mode === "hybrid" && rulesTrusted && !overrides) { out.parser = "rules"; return out; }

  const setMetric = (id) => {
    out.metric = id;
    const act = id && M.metrics[id] ? M.metrics[id].activity : null;
    out.population.activity = act || null;
  };
  if (embedOk) {
    setMetric(top.metric);
    out.parser = mode === "embed" ? "embed" : "semantic";
    out.semantic.accepted = true;
    out.unmatched.metric = null;
    if (top.score < tau + 0.1) out.confidence = "low";
  } else if (mode === "hybrid" && cfg.keepFuzzy && rules.metric) {
    out.parser = "rules";
  } else {
    setMetric(null);
    out.parser = mode === "embed" ? "embed" : "semantic";
    out.confidence = "low";
    out.abstained = true;
    if (!out.unmatched.metric) out.unmatched.metric = (rules.residual || "").trim() || null;
  }
  return out;
}

// ---------- model loading (browser only) ----------
let pipePromise = null;
export function loadModel({ base = "./", device = "wasm" } = {}) {
  if (pipePromise) return pipePromise;
  pipePromise = (async () => {
    const t0 = performance.now();
    const { pipeline, env } = await import(new URL("assets/ai/vendor/transformers.min.js", new URL(base, location.href)).href);
    env.allowRemoteModels = false;
    env.allowLocalModels = true;
    // A full URL here breaks tokenizer loading in transformers.js 4.3.2; a same-origin path works.
    env.localModelPath = new URL("assets/ai/models/", new URL(base, location.href)).pathname;
    env.backends.onnx.wasm.wasmPaths = {
      mjs: new URL("assets/ai/vendor/ort-wasm-simd-threaded.jsep.mjs", new URL(base, location.href)).href,
      wasm: new URL("assets/ai/vendor/ort-wasm-simd-threaded.jsep.wasm", new URL(base, location.href)).href,
    };
    const ext = await pipeline("feature-extraction", "all-MiniLM-L6-v2", { dtype: "q8", device });
    const embed = async (texts) => {
      const r = await ext(texts, { pooling: "mean", normalize: true });
      return r.tolist();
    };
    return { embed, device, loadMs: performance.now() - t0 };
  })();
  pipePromise.catch(() => { pipePromise = null; });
  return pipePromise;
}

let indexPromise = null;
export function loadIndex(base = "./") {
  if (!indexPromise) indexPromise = fetch(new URL("data/semantic_index.json", new URL(base, location.href))).then((r) => r.json()).then(decodeIndex);
  return indexPromise;
}

// One call for the page: rules parse, embed, rank, combine.
export async function parseSemantic(question, M, { base = "./", mode = "hybrid", cfg = DEFAULTS, allow = null } = {}) {
  const rules = parseRules(question, M);
  const text = embedText(question, rules, cfg);
  if (!text) return { ...combine(rules, [], M, mode, cfg), ranked: [], embedMs: 0 };
  const [model, index] = await Promise.all([loadModel({ base }), loadIndex(base)]);
  const t0 = performance.now();
  const [vec] = await model.embed([text]);
  const embedMs = performance.now() - t0;
  const ranked = rankMetrics(index, vec, allow);
  return { ...combine(rules, ranked, M, mode, cfg), ranked: ranked.slice(0, 3), embedMs, embedded: text };
}
