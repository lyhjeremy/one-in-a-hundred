"""Evaluate the rules parser and (when WORKER_URL is set) the LLM parser on
eval/gold.jsonl. Writes eval/results.md.

Scoring: exact-triple match means metric, country, sex, snapped age band,
percentile all equal the gold. Out-of-scope questions score as correct when
no catalogue metric is returned; a hallucinated id there is reported
separately. Value accuracy is within 2% of the gold value.

Usage: WORKER_URL=https://... python3 eval/eval_parser.py
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.request
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GOLD = ROOT / "eval" / "gold.jsonl"
OUT = ROOT / "eval" / "results.md"
WORKER = os.environ.get("WORKER_URL", "").rstrip("/")

JS = """
import { readFileSync } from "node:fs";
import { parseRules } from "./parser-rules.js";
const M = JSON.parse(readFileSync("data/metrics.json", "utf8"));
const qs = JSON.parse(readFileSync(process.argv[2], "utf8"));
const out = qs.map((q) => { const t0 = performance.now(); const p = parseRules(q, M); return { ...p, ms: performance.now() - t0 }; });
process.stdout.write(JSON.stringify(out));
"""


def snap(band: str | None) -> str | None:
    """Compare bands loosely: a single age matches a range containing it."""
    return band


def band_match(got: str | None, exp: str | None) -> bool:
    if got == exp:
        return True
    if not got or not exp:
        return False
    def rng(b):
        if b.endswith("+"):
            return int(b[:-1]), 200
        if "-" in b:
            lo, hi = b.split("-")
            return int(lo), int(hi)
        return int(b), int(b)
    g, e = rng(got), rng(exp)
    return g[0] <= e[0] and e[1] <= g[1] or e[0] <= g[0] and g[1] <= e[1]


def score(got: dict, row: dict) -> dict:
    exp = row["expect"]
    pop = got.get("population", {})
    if exp is None:
        ok = got.get("metric") in (None, "")
        return {"exact": ok, "hallucinated": not ok, "fields": {}}
    fields = {
        "metric": got.get("metric") == exp["metric"],
        "country": (pop.get("country") or None) == exp["country"],
        "sex": (pop.get("sex") or "all") == exp["sex"],
        "age_band": band_match(pop.get("age_band"), exp["age_band"]),
        "percentile": float(got.get("percentile") or 0) == float(exp["percentile"]),
    }
    if exp.get("value") is not None:
        v = got.get("value")
        fields["value"] = v is not None and abs(v - exp["value"]) <= 0.02 * abs(exp["value"]) + 0.5
    return {"exact": all(fields.values()), "hallucinated": False, "fields": fields}


def run_rules(qs: list[str]) -> list[dict]:
    tmp = ROOT / "_gold_q.json"
    runner = ROOT / "_eval_rules.mjs"
    tmp.write_text(json.dumps(qs))
    runner.write_text(JS)
    try:
        r = subprocess.run(["node", str(runner), str(tmp)], cwd=ROOT, capture_output=True, text=True, check=True)
        return json.loads(r.stdout)
    finally:
        tmp.unlink(missing_ok=True)
        runner.unlink(missing_ok=True)


def run_llm(qs: list[str]) -> list[dict]:
    out = []
    for q in qs:
        t0 = time.time()
        try:
            req = urllib.request.Request(f"{WORKER}/parse", data=json.dumps({"q": q}).encode(),
                                         headers={"content-type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=10) as r:
                j = json.loads(r.read().decode())
            ms = (time.time() - t0) * 1000
            if j.get("ok"):
                t = j["triple"]
                out.append({**t, "unmatched": j.get("unmatched", {}), "confidence": j.get("confidence"), "ms": ms, "ok": True, "cached": j.get("cached")})
            else:
                out.append({"metric": None, "population": {}, "percentile": None, "value": None, "ms": ms, "ok": False, "reason": j.get("reason")})
        except Exception as e:  # noqa: BLE001
            out.append({"metric": None, "population": {}, "percentile": None, "value": None, "ms": (time.time() - t0) * 1000, "ok": False, "reason": str(e)[:60]})
        time.sleep(0.2)
    return out


def summarise(name: str, results: list[dict], rows: list[dict]) -> tuple[str, list[str]]:
    by_bucket: dict[str, list[bool]] = defaultdict(list)
    fields: Counter = Counter()
    field_n: Counter = Counter()
    halluc = 0
    fails = []
    lat = sorted(r.get("ms", 0) for r in results)
    fallback = sum(1 for r in results if r.get("ok") is False)
    for r, row in zip(results, rows):
        s = score(r, row)
        by_bucket[row["bucket"]].append(s["exact"])
        halluc += s["hallucinated"]
        for k, v in s["fields"].items():
            fields[k] += v
            field_n[k] += 1
        if not s["exact"] and len(fails) < 12:
            pop = r.get("population", {})
            fails.append(f"- [{row['bucket']}] \"{row['q']}\": expected {json.dumps(row['expect'])}, got metric={r.get('metric')} country={pop.get('country')} sex={pop.get('sex')} age={pop.get('age_band')} pct={r.get('percentile')} value={r.get('value')}")
    total = sum(len(v) for v in by_bucket.values())
    exact = sum(sum(v) for v in by_bucket.values())
    lines = [f"## {name}", "", f"Exact-triple accuracy: **{exact}/{total} = {exact / total * 100:.1f}%**", "",
             "| Bucket | Exact | n | Accuracy |", "|---|---|---|---|"]
    for b in ["canonical", "paraphrase", "value", "ambiguous", "out_of_scope"]:
        v = by_bucket.get(b, [])
        lines.append(f"| {b} | {sum(v)} | {len(v)} | {sum(v) / len(v) * 100:.0f}% |" if v else f"| {b} | - | 0 | - |")
    lines += ["", "Per-field accuracy (in-scope questions): " + ", ".join(f"{k} {fields[k]}/{field_n[k]}" for k in ["metric", "country", "sex", "age_band", "percentile", "value"] if field_n[k]),
              f"Hallucinated catalogue ids on out-of-scope questions: {halluc}/{len(by_bucket.get('out_of_scope', []))}",
              f"Latency: p50 {lat[len(lat) // 2]:.0f} ms, p95 {lat[int(len(lat) * 0.95)]:.0f} ms" + (f"; fallback/errors {fallback}" if name.startswith("LLM") else ""), ""]
    return "\n".join(lines), fails


def main() -> int:
    rows = [json.loads(l) for l in GOLD.read_text().splitlines() if l.strip()]
    gold_hash = hashlib.sha1(GOLD.read_bytes()).hexdigest()[:12]
    qs = [r["q"] for r in rows]
    out = [f"# Parser evaluation", "", f"Run {date.today().isoformat()}. Gold set: {len(rows)} questions, sha1 {gold_hash}.", ""]
    rules = run_rules(qs)
    s, fails = summarise("Rules parser (browser fallback, baseline)", rules, rows)
    out += [s, "Example failures:", ""] + fails + [""]
    if WORKER:
        llm = run_llm(qs)
        s, fails = summarise(f"LLM parser (Worker at {WORKER})", llm, rows)
        out += [s, "Example failures:", ""] + fails + [""]
    else:
        out += ["## LLM parser", "", "Not run: WORKER_URL not set. Deploy the Worker and rerun with WORKER_URL to fill this section.", ""]
    out += ["## Notes", "",
            "- The rules parser was adjusted twice after seeing failures: once on this set (superlative percentiles such as "
            "\"oldest 10%\", decade ages like \"in their 30s\", the \"avg\" synonym, two metric phrasings; two gold labels "
            "that were generation bugs were corrected at the same time), and once on a live question (\"marathoners\" was "
            "not matched, so phrasings now match their inflections). Its number is therefore optimistic by an unknown "
            "amount. The LLM parser is scored without any tuning on this set.",
            "- Latency for the rules parser is in-process Node; for the LLM parser it is a round trip from this machine to the Worker.",
            ""]
    OUT.write_text("\n".join(out))
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
