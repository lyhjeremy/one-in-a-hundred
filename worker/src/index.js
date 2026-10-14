// One in a Hundred Worker: /parse, /request, /health.
// Static site does everything else. See SPEC.md section 8.1.
import { parseWithLLM } from "./llm.js";
import { buildSystemPrompt, validateTriple } from "./prompt.js";
import catalogue from "./catalogue.json";

const MAX_Q = 300;

function cors(env, extra = {}) {
  return {
    "access-control-allow-origin": env.ALLOWED_ORIGIN,
    "access-control-allow-methods": "POST, GET, OPTIONS",
    "access-control-allow-headers": "content-type",
    "content-type": "application/json; charset=utf-8",
    ...extra,
  };
}
const json = (env, body, status = 200) => new Response(JSON.stringify(body), { status, headers: cors(env) });

export function normalise(q) {
  return (q || "").toLowerCase().replace(/[’']/g, "").replace(/[^a-z0-9%$:.\-\s]/g, " ").replace(/\s+/g, " ").trim();
}
async function sha1(s) {
  const b = await crypto.subtle.digest("SHA-1", new TextEncoder().encode(s));
  return [...new Uint8Array(b)].map((x) => x.toString(16).padStart(2, "0")).join("");
}

async function rateLimited(env, request) {
  if (!env.PARSE_LIMIT) return false;
  const ip = request.headers.get("cf-connecting-ip") || "unknown";
  try {
    const { success } = await env.PARSE_LIMIT.limit({ key: ip });
    return !success;
  } catch { return false; }
}

async function handleParse(request, env) {
  let body;
  try { body = await request.json(); } catch { return json(env, { ok: false, reason: "bad-json" }, 400); }
  const q = typeof body.q === "string" ? body.q.trim() : "";
  if (!q) return json(env, { ok: false, reason: "empty" }, 400);
  if (q.length > MAX_Q) return json(env, { ok: false, reason: "too-long" }, 413);
  if (await rateLimited(env, request)) return json(env, { ok: false, reason: "rate-limited" }, 429);

  const key = normalise(q);
  // Cache API is a no-op on *.workers.dev; harmless there, useful on a custom domain.
  const cacheKey = new Request(`https://cache.oih.invalid/parse/${await sha1(key)}`);
  const cache = caches.default;
  const hit = await cache.match(cacheKey);
  if (hit) {
    const j = await hit.json();
    return json(env, { ...j, cached: true });
  }
  let result;
  try {
    const raw = await parseWithLLM(env, buildSystemPrompt(catalogue), q);
    const v = validateTriple(raw, catalogue);
    result = { ok: true, triple: v.triple, unmatched: v.unmatched, confidence: v.confidence, model: env.GROQ_MODEL, cached: false };
  } catch (e) {
    const reason = e && e.reason ? e.reason : "llm-down";
    return json(env, { ok: false, reason }, reason === "unparseable" ? 422 : 502);
  }
  const resp = new Response(JSON.stringify(result), { headers: { "content-type": "application/json", "cache-control": "public, max-age=2592000" } });
  try { await cache.put(cacheKey, resp); } catch { /* no cache on workers.dev */ }
  return json(env, result);
}

async function handleRequest(request, env) {
  let body;
  try { body = await request.json(); } catch { return json(env, { ok: false, reason: "bad-json" }, 400); }
  const q = typeof body.q === "string" ? body.q.trim() : "";
  if (!q) return json(env, { ok: false, reason: "empty" }, 400);
  if (q.length > MAX_Q) return json(env, { ok: false, reason: "too-long" }, 413);
  if (!env.QUEUE) return json(env, { ok: false, reason: "no-queue" }, 503);
  const key = `q:${await sha1(normalise(q))}`;
  const existing = await env.QUEUE.get(key);
  if (existing) return json(env, { ok: true, queued: false, reason: "duplicate" });
  const value = JSON.stringify({ q, triple: body.triple || null, at: new Date().toISOString() });
  try {
    await env.QUEUE.put(key, value);
  } catch (e) {
    // KV free tier: 1,000 writes/day. Say so instead of pretending.
    return json(env, { ok: true, queued: false, reason: "queue-full" });
  }
  return json(env, { ok: true, queued: true });
}

let healthCache = { at: 0, body: null };
async function handleHealth(env) {
  const now = Date.now();
  if (healthCache.body && now - healthCache.at < 3600_000) return json(env, { ...healthCache.body, cached: true });
  const out = { ok: true, groq: false, kv: false, version: env.VERSION, model: env.GROQ_MODEL, checked: new Date(now).toISOString() };
  try {
    const r = await parseWithLLM(env, "Reply with the single word OK.", "ping", { maxTokens: 5, rawText: true });
    out.groq = typeof r === "string" && r.length > 0;
  } catch { out.groq = false; }
  try {
    if (env.QUEUE) { await env.QUEUE.get("health:probe"); out.kv = true; }
  } catch { out.kv = false; }
  out.ok = out.groq && out.kv;
  healthCache = { at: now, body: out };
  // 200 even when ok is false: the body carries the meaning, the checker reads the fields.
  return json(env, out);
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: cors(env) });
    if (url.pathname === "/health" && request.method === "GET") return handleHealth(env);
    if (url.pathname === "/parse" && request.method === "POST") return handleParse(request, env);
    if (url.pathname === "/request" && request.method === "POST") return handleRequest(request, env);
    return json(env, { ok: false, reason: "not-found" }, 404);
  },
};
