"""Tests for the in-browser semantic parser (parser-semantic.js) and its data.

Standard library plus Node, like test_format.py. The model itself is not
loaded here (that needs a browser; eval/semantic/eval_semantic.py does it);
these tests cover the index file, the combine rules and the eval hygiene.
Usage: python -m pytest -q pipeline/test_semantic.py
"""
from __future__ import annotations

import base64
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = json.loads((ROOT / "data" / "semantic_index.json").read_text())
CORE = json.loads((ROOT / "data" / "metrics.json").read_text())["metrics"]
EXTRA = json.loads((ROOT / "data" / "metrics_extra.json").read_text())["metrics"]


def node(js: str) -> object:
    r = subprocess.run(["node", "--input-type=module", "-e", js], cwd=ROOT, capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def test_index_shape():
    raw = base64.b64decode(INDEX["q8"])
    assert INDEX["dim"] == 384
    assert len(raw) == len(INDEX["entries"]) * INDEX["dim"]
    for e in INDEX["entries"]:
        assert e["m"] in (CORE if e["core"] else EXTRA), e
    assert {e["m"] for e in INDEX["entries"] if e["core"]} == set(CORE)


def test_index_has_no_gold_questions():
    norm = lambda s: re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()  # noqa: E731
    gold = {norm(json.loads(l)["q"]) for l in (ROOT / "eval" / "gold.jsonl").read_text().splitlines() if l.strip()}
    gold.discard("")
    # Core entries only: the eval scores against the core catalogue. Researched measures
    # (metrics_extra.json) carry seed-question phrasings and are never scored.
    leaked = [e["t"] for e in INDEX["entries"] if e["core"] and norm(e["t"]) in gold]
    # Single catalogue keywords ("income", "height") are also one-word ambiguous gold questions; anything longer is a leak.
    assert all(len(t.split()) == 1 for t in leaked), leaked


def test_dev_split_does_not_overlap_gold():
    words = lambda s: set(re.sub(r"[^a-z0-9%]+", " ", s.lower()).split())  # noqa: E731
    gold = [words(json.loads(l)["q"]) for l in (ROOT / "eval" / "gold.jsonl").read_text().splitlines() if l.strip()]
    for l in (ROOT / "eval" / "semantic" / "dev.jsonl").read_text().splitlines():
        w = words(json.loads(l)["q"])
        assert max(len(w & g) / len(w | g) for g in gold) < 0.5, l


def test_decoded_vectors_are_unit_length():
    out = node("""
import { readFileSync } from "node:fs";
import { decodeIndex } from "./parser-semantic.js";
const ix = decodeIndex(JSON.parse(readFileSync("data/semantic_index.json", "utf8")));
const norms = [];
for (let i = 0; i < ix.entries.length; i += 50) { let s = 0; for (let j = 0; j < ix.dim; j++) s += ix.vecs[i * ix.dim + j] ** 2; norms.push(s); }
process.stdout.write(JSON.stringify(norms));
""")
    assert all(abs(n - 1) < 1e-4 for n in out)


COMBINE = """
import { readFileSync } from "node:fs";
import { parseRules } from "./parser-rules.js";
import { combine, DEFAULTS } from "./parser-semantic.js";
const M = JSON.parse(readFileSync("data/metrics.json", "utf8"));
const R = (metric, score) => [{ metric, score, text: "t" }, { metric: "bmi_adult", score: score - 0.2, text: "u" }];
const pick = (o) => ({ metric: o.metric, parser: o.parser, activity: o.population.activity, abstained: !!o.abstained, country: o.population.country, pct: o.percentile });
const out = {
  keep: pick(combine(parseRules("median height of dutch men", M), R("weight_adult_kg", 0.55), M, "hybrid")),
  override: pick(combine(parseRules("median height of dutch men", M), R("weight_adult_kg", 0.7), M, "hybrid")),
  rescue: pick(combine(parseRules("how quick is a top 10% 42 kilometre race in kenya", M), R("marathon_time", 0.6), M, "hybrid")),
  abstain: pick(combine(parseRules("what is the capital of france", M), R("income_pretax_adult_ppp", 0.3), M, "hybrid")),
  embed: pick(combine(parseRules("median height of dutch men", M), R("weight_adult_kg", 0.55), M, "embed")),
  defaults: DEFAULTS,
};
process.stdout.write(JSON.stringify(out));
"""


def test_combine_rules():
    o = node(COMBINE)
    assert o["keep"] == {"metric": "height_adult_cm", "parser": "rules", "activity": None, "abstained": False, "country": "NL", "pct": 50}
    assert o["override"]["metric"] == "weight_adult_kg" and o["override"]["parser"] == "semantic"
    assert o["rescue"]["metric"] == "marathon_time" and o["rescue"]["activity"] == "marathon_finishers"
    assert o["rescue"]["country"] == "KE" and o["rescue"]["pct"] == 90
    assert o["abstain"]["metric"] is None and o["abstain"]["abstained"]
    assert o["embed"]["metric"] == "weight_adult_kg"


def test_defaults_match_the_dev_tuned_settings():
    res = json.loads((ROOT / "eval" / "semantic" / "results.json").read_text())
    want = {**res["dev"]["chosen_hybrid"], "tauEmbed": res["dev"]["chosen_embed"]["tauEmbed"]}
    assert node(COMBINE)["defaults"] == want


def test_rules_baseline_unchanged():
    # Exposing residual and metric_score must not move the published 181/200.
    out = node("""
import { readFileSync } from "node:fs";
import { parseRules } from "./parser-rules.js";
const M = JSON.parse(readFileSync("data/metrics.json", "utf8"));
const rows = readFileSync("eval/gold.jsonl", "utf8").split("\\n").filter(Boolean).map((l) => JSON.parse(l));
process.stdout.write(JSON.stringify(rows.map((r) => parseRules(r.q, M))));
""")
    import sys
    sys.path.insert(0, str(ROOT / "eval"))
    from eval_parser import score
    rows = [json.loads(l) for l in (ROOT / "eval" / "gold.jsonl").read_text().splitlines() if l.strip()]
    assert sum(score(o, r)["exact"] for o, r in zip(out, rows)) == 181
