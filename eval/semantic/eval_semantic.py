"""Score the in-browser semantic parser against the rules parser.

Runs the shipped parser-semantic.js in headless Chromium (Playwright) through
eval/semantic/harness.html, so the numbers come from the same code and the
same q8 model a visitor's browser runs.

1. Tune on the dev split only (eval/semantic/dev.jsonl): grid over the
   embedded text (residual after slot removal, or the full question), the
   cosine threshold, the top-1/top-2 margin and whether hybrid keeps a fuzzy
   rules match, and the cosine at which the embedding overrides a rules
   phrasing hit. Ties go to fewer out-of-scope ids, then the higher threshold.
2. Score the frozen gold set (eval/gold.jsonl, sha1 0b1dd183b3f8, frozen in
   commit b31ff53) once with the chosen settings: rules, embeddings alone,
   hybrid. Scoring is eval_parser.score(), unchanged.
3. Latency per question (WASM, and WebGPU when the browser exposes an
   adapter), cold model load, bytes downloaded, and every request's origin.
4. Dump browser vectors for a parity sample; parity.py compares them with
   sentence-transformers in Python.

Writes eval/semantic/results.json, results.md, gold_outputs.jsonl,
browser_vectors_sample.json. Usage: python3 eval/semantic/eval_semantic.py
(needs playwright; PORT env var picks the local server port, default 8850).
"""
from __future__ import annotations

import hashlib
import itertools
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "eval"))
from eval_parser import score  # noqa: E402

PORT = int(os.environ.get("PORT", "8850"))
BUCKETS = ["canonical", "paraphrase", "value", "ambiguous", "out_of_scope"]


def load(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


def accuracy(outs: list[dict], rows: list[dict]) -> dict:
    by = defaultdict(list)
    halluc = 0
    abstain = 0
    for o, r in zip(outs, rows):
        s = score(o, r)
        by[r["bucket"]].append(s["exact"])
        halluc += s["hallucinated"]
        abstain += o.get("metric") in (None, "")
    n = len(rows)
    exact = sum(sum(v) for v in by.values())
    in_scope = [(o, r) for o, r in zip(outs, rows) if r["expect"] is not None and r["expect"]["metric"] is not None]
    false_abstain = sum(1 for o, r in in_scope if not o.get("metric"))
    oos = sum(1 for r in rows if r["expect"] is None)
    return {
        "exact": exact, "n": n, "acc": round(exact / n, 4),
        "buckets": {b: [sum(by[b]), len(by[b])] for b in BUCKETS if by[b]},
        "hallucinated_oos": [halluc, oos],
        "abstain_rate": round(abstain / n, 4), "abstained": abstain,
        "false_abstain_in_scope": [false_abstain, len(in_scope)],
    }


def pct(xs: list[float], q: float) -> float:
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, int(len(xs) * q))], 1)


def key(cfg: dict, a: dict) -> tuple:
    return (a["exact"], -a["hallucinated_oos"][0], cfg["tauHybrid"], cfg["input"] == "residual", -cfg["override"], -cfg["margin"])


def grid() -> list[dict]:
    out = []
    taus = [round(0.30 + 0.025 * i, 3) for i in range(17)]
    for inp, tau, margin, keep, ov in itertools.product(["residual", "full"], taus, [0, 0.02, 0.05], [False, True],
                                                       [0, 0.6, 0.65, 0.7, 0.75, 0.8]):
        out.append({"input": inp, "tauEmbed": tau, "tauHybrid": tau, "margin": margin, "trustRules": 1,
                    "keepFuzzy": keep, "override": ov})
    return out


def main() -> int:
    from playwright.sync_api import sync_playwright

    dev = load(HERE / "dev.jsonl")
    gold = load(ROOT / "eval" / "gold.jsonl")
    gold_sha = hashlib.sha1((ROOT / "eval" / "gold.jsonl").read_bytes()).hexdigest()[:12]
    dev_sha = hashlib.sha1((HERE / "dev.jsonl").read_bytes()).hexdigest()[:12]
    assert gold_sha == "0b1dd183b3f8", gold_sha

    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT), "--bind", "127.0.0.1"], cwd=ROOT,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.0)
    res: dict = {"date": date.today().isoformat(), "gold_sha1": gold_sha, "gold_frozen_commit": "b31ff53",
                 "dev_sha1": dev_sha, "dev_n": len(dev), "machine": f"Apple M4, {platform.system()} {platform.release()}"}
    try:
        with sync_playwright() as p:
            # channel="chromium" is the new headless mode; the old headless shell has no WebGPU adapter.
            browser = p.chromium.launch(channel="chromium")
            res["browser"] = f"Chromium {browser.version} (Playwright, new headless)"
            page = browser.new_page()
            origins: Counter = Counter()
            sizes: dict[str, int] = {}

            def on_resp(r):
                u = urlparse(r.url)
                origins[f"{u.scheme}://{u.netloc}"] += 1
                if u.path.startswith("/assets/ai/") or u.path.endswith("semantic_index.json"):
                    f = ROOT / u.path.lstrip("/")
                    if f.is_file():
                        sizes[u.path] = f.stat().st_size
            page.on("response", on_resp)
            page.goto(f"http://127.0.0.1:{PORT}/eval/semantic/harness.html")
            page.wait_for_function("document.getElementById('status').textContent === 'ready'", timeout=60000)
            setup = page.evaluate("setup()")
            res["cold_load_ms_localhost"] = round(setup["loadMs"])
            res["download_bytes"] = sum(sizes.values())
            res["download_files"] = sizes

            # 1. tune on dev
            page.evaluate("qs => embedAll(qs).then(() => true)", [r["q"] for r in dev])
            dev_rules = accuracy(page.evaluate("combineAll('rules', null)"), dev)
            best_e, best_h = None, None
            for cfg in grid():
                if not cfg["keepFuzzy"] and not cfg["override"]:
                    a = accuracy(page.evaluate("([m, c]) => combineAll(m, c)", ["embed", cfg]), dev)
                    if best_e is None or key(cfg, a) > key(*best_e):
                        best_e = (cfg, a)
                a = accuracy(page.evaluate("([m, c]) => combineAll(m, c)", ["hybrid", cfg]), dev)
                if best_h is None or key(cfg, a) > key(*best_h):
                    best_h = (cfg, a)
            chosen = {**best_h[0], "tauEmbed": best_e[0]["tauEmbed"]}
            embed_cfg = {**best_e[0]}
            res["dev"] = {"rules": dev_rules, "embed": best_e[1], "hybrid": best_h[1],
                          "chosen_hybrid": best_h[0], "chosen_embed": best_e[0], "grid_size": len(grid())}

            # 2. score the frozen gold set once
            gold_embed = page.evaluate("qs => embedAll(qs)", [r["q"] for r in gold])
            outs = {
                "rules": page.evaluate("combineAll('rules', null)"),
                "embed": page.evaluate("([m, c]) => combineAll(m, c)", ["embed", embed_cfg]),
                "hybrid": page.evaluate("([m, c]) => combineAll(m, c)", ["hybrid", best_h[0]]),
            }
            res["gold"] = {k: accuracy(v, gold) for k, v in outs.items()}
            with (HERE / "gold_outputs.jsonl").open("w") as f:
                for i, r in enumerate(gold):
                    f.write(json.dumps({"q": r["q"], "bucket": r["bucket"], "expect": r["expect"],
                                        **{k: {"metric": outs[k][i].get("metric"),
                                               "country": outs[k][i]["population"].get("country"),
                                               "sex": outs[k][i]["population"].get("sex"),
                                               "age_band": outs[k][i]["population"].get("age_band"),
                                               "percentile": outs[k][i].get("percentile"),
                                               "value": outs[k][i].get("value"),
                                               "exact": score(outs[k][i], r)["exact"]} for k in outs},
                                        "top3": gold_embed[i]["top"][best_h[0]["input"]]}) + "\n")

            # 3. latency (WASM)
            ms = [g["ms"][best_h[0]["input"]] for g in gold_embed if g["ms"][best_h[0]["input"]] > 0]
            needs = sum(1 for o in outs["hybrid"] if o.get("parser") != "rules" or o.get("semantic") is None)
            used_embed = sum(1 for o in outs["hybrid"] if (o.get("semantic") or {}).get("accepted") and o.get("parser") == "semantic")
            res["latency_wasm"] = {"n": len(ms), "p50_ms": pct(ms, 0.5), "p95_ms": pct(ms, 0.95), "max_ms": round(max(ms), 1)}
            res["hybrid_embedding_calls"] = needs
            res["hybrid_embedding_answers"] = used_embed

            # 4. parity sample: 20 index phrasings and 20 dev questions
            idx = json.loads((ROOT / "data" / "semantic_index.json").read_text())
            sample = [e["t"] for e in idx["entries"][::37][:20]] + [r["q"] for r in dev[::5][:20]]
            vecs = page.evaluate("t => embedRaw(t)", sample)
            (HERE / "browser_vectors_sample.json").write_text(json.dumps({"texts": sample, "vectors": [[round(x, 6) for x in v] for v in vecs]}))
            res["origins_seen"] = dict(origins)
            page.close()

            # WebGPU, if this headless browser has an adapter
            page = browser.new_page()
            page.goto(f"http://127.0.0.1:{PORT}/eval/semantic/harness.html?device=webgpu")
            gpu = page.evaluate("async () => !!(navigator.gpu && await navigator.gpu.requestAdapter())")
            res["webgpu_adapter"] = gpu
            if gpu:
                try:
                    page.wait_for_function("document.getElementById('status').textContent === 'ready'", timeout=60000)
                    s2 = page.evaluate("setup()")
                    g2 = page.evaluate("qs => embedAll(qs)", [r["q"] for r in gold])
                    o2 = page.evaluate("([m, c]) => combineAll(m, c)", ["hybrid", best_h[0]])
                    ms2 = [g["ms"][best_h[0]["input"]] for g in g2 if g["ms"][best_h[0]["input"]] > 0]
                    res["latency_webgpu"] = {"n": len(ms2), "p50_ms": pct(ms2, 0.5), "p95_ms": pct(ms2, 0.95),
                                             "cold_load_ms_localhost": round(s2["loadMs"]),
                                             "hybrid_exact": accuracy(o2, gold)["exact"]}
                except Exception as e:  # noqa: BLE001
                    res["latency_webgpu"] = {"error": str(e)[:200]}
            browser.close()
    finally:
        srv.terminate()

    # blob: URLs are in-memory worker scripts that onnxruntime creates, not network requests.
    third = {k: v for k, v in res["origins_seen"].items()
             if not k.startswith(f"http://127.0.0.1:{PORT}") and not k.startswith(("blob:", "data:"))}
    res["third_party_origins"] = third
    (HERE / "results.json").write_text(json.dumps(res, indent=1))
    write_md(res)
    print(json.dumps({k: res[k] for k in ("gold", "latency_wasm", "download_bytes", "third_party_origins")}, indent=1))
    return 0


def write_md(res: dict) -> None:
    g = res["gold"]
    lines = ["# Semantic parser evaluation", "",
             f"Run {res['date']} on {res['machine']}, {res['browser']}. Gold set: 200 questions, sha1 {res['gold_sha1']} "
             f"(frozen in commit {res['gold_frozen_commit']}). Settings tuned on the dev split only: {res['dev_n']} questions, sha1 {res['dev_sha1']}.", "",
             "## Frozen gold set", "",
             "| Parser | Exact | Accuracy | canonical | paraphrase | value | ambiguous | out of scope | OOS ids returned | Abstain rate |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for k, name in (("rules", "Rules (baseline)"), ("embed", "Embeddings alone"), ("hybrid", "Hybrid")):
        a = g[k]
        b = a["buckets"]
        lines.append(f"| {name} | {a['exact']}/{a['n']} | {a['acc'] * 100:.1f}% | " + " | ".join(f"{b[x][0]}/{b[x][1]}" for x in BUCKETS)
                     + f" | {a['hallucinated_oos'][0]}/{a['hallucinated_oos'][1]} | {a['abstain_rate'] * 100:.1f}% |")
    d = res["dev"]
    lines += ["", "## Dev split (used for tuning)", "",
              f"Rules {d['rules']['exact']}/{d['rules']['n']}, embeddings alone {d['embed']['exact']}/{d['embed']['n']}, hybrid {d['hybrid']['exact']}/{d['hybrid']['n']}.",
              f"Chosen hybrid settings: `{json.dumps(d['chosen_hybrid'])}`. Embeddings-alone threshold: {d['chosen_embed']['tauEmbed']} on `{d['chosen_embed']['input']}` text. Grid size {d['grid_size']}.", "",
              "## Cost of running it", "",
              f"- Download on first use: {res['download_bytes'] / 1e6:.1f} MB (files listed in results.json), cached by the browser afterwards.",
              f"- Cold model load from localhost: {res['cold_load_ms_localhost']} ms.",
              f"- Embedding one question, WASM: p50 {res['latency_wasm']['p50_ms']} ms, p95 {res['latency_wasm']['p95_ms']} ms (n={res['latency_wasm']['n']}).",
              f"- Hybrid ran the embedding on {res['hybrid_embedding_calls']} of 200 gold questions (the rest were rules phrasing hits) and took the embedding's answer on {res['hybrid_embedding_answers']}."]
    w = res.get("latency_webgpu")
    if w and "p50_ms" in w:
        lines.append(f"- WebGPU: p50 {w['p50_ms']} ms, p95 {w['p95_ms']} ms (n={w['n']}), hybrid exact {w['hybrid_exact']}/200.")
    elif w:
        lines.append(f"- WebGPU: failed ({w['error']}).")
    else:
        lines.append("- WebGPU: headless Chromium exposed no adapter, so not measured.")
    lines += [f"- Origins requested: {', '.join(res['origins_seen'])}. Third-party origins: {len(res['third_party_origins'])}.", ""]
    lines += ["## Run history", "",
              "The gold set was scored twice. The first run used a hybrid that always kept a rules phrasing hit; it scored "
              "180/200 on gold and 64/104 on dev, below embeddings alone on dev (69/104). Prompted by that dev result, the "
              "`override` option (an embedding can replace a rules hit above a cosine) was added to the grid; the dev split "
              "picked override 0.6, which raised dev to 66/104 and lowered gold to 172/200. This page reports the second run, "
              "the one chosen by the stated protocol. Nothing was changed after seeing the second gold score.", ""]
    par = HERE / "parity.json"
    if par.exists():
        pj = json.loads(par.read_text())
        lines += ["## Python and browser parity", "",
                  f"Cosine between the browser's q8 vector and sentence-transformers fp32 for the same text (n={pj['n']}): "
                  f"min {pj['browser_vs_python']['min']}, mean {pj['browser_vs_python']['mean']}. "
                  f"Stored int8 index vs fp32: min {pj['int8_vs_fp32']['min']}.", ""]
    (HERE / "results.md").write_text("\n".join(lines))


if __name__ == "__main__":
    sys.exit(main())
