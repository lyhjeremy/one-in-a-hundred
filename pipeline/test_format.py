"""Check that pipeline/format.py and format.js agree on the fixtures.

Writes eval/format_fixtures.json from the Python side, then runs the JS side
in Node over the same inputs and diffs. Usage: python3 pipeline/test_format.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline import format as F  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "eval" / "format_fixtures.json"

CASES = [
    ("money", 31234), ("money", 1_234_567), ("money", 999), ("money", 150_000), ("money", 2_672_251),
    ("time_hm", 9540), ("time_hm", 14280), ("time_ms", 1312), ("time_ms", 2400),
    ("height", 193.2), ("height", 160.7), ("height", 182.88), ("weight", 80.4), ("bmi", 28.34),
    ("years", 84.6), ("years_1dp", 73.25), ("hours", 1731), ("count", 82_000_000), ("count", 2850),
    ("count", 8_231_613_067), ("count", 456_700),
]
GROUPS = [
    ({"base": "world", "country": None, "sex": "all", "age_band": None, "activity": None, "source_category": None}, "age_years", 2025),
    ({"base": "world", "country": None, "sex": "all", "age_band": None, "activity": None, "source_category": None}, "income_pretax_adult_ppp", 2023),
    ({"base": "country", "country": "CH", "sex": "all", "age_band": None, "activity": None, "source_category": None}, "income_pretax_adult_ppp", 2023),
    ({"base": "country", "country": "US", "sex": "m", "age_band": "30-39", "activity": None, "source_category": "Non-Hispanic Asian"}, "height_adult_cm", 2022),
    ({"base": "country", "country": "US", "sex": "f", "age_band": "40-44", "activity": "marathon_finishers", "source_category": None}, "marathon_time", 2023),
    ({"base": "country", "country": "JP", "sex": "f", "age_band": "70+", "activity": None, "source_category": None}, "bmi_adult", 2024),
]


def py_side() -> dict:
    out = {"values": [], "groups": []}
    for fmt, v in CASES:
        s = F.format_count(v) if fmt == "count" else F.FORMATTERS[fmt](v)
        out["values"].append({"format": fmt, "input": v, "expected": s})
    for pop, metric, year in GROUPS:
        out["groups"].append({"population": pop, "metric": metric, "year": year, "expected": F.group_name(pop, metric, year)})
    return out


JS = """
import { readFileSync } from "node:fs";
import * as F from "./format.js";
const M = JSON.parse(readFileSync("data/metrics.json", "utf8"));
const fx = JSON.parse(readFileSync("eval/format_fixtures.json", "utf8"));
let bad = 0;
for (const c of fx.values) {
  const got = c.format === "count" ? F.formatCount(c.input) : F.FORMATTERS[c.format](c.input);
  if (got !== c.expected) { bad++; console.log("MISMATCH", c.format, c.input, "py:", c.expected, "js:", got); }
}
for (const g of fx.groups) {
  const got = F.groupName(M, g.population, g.metric, g.year);
  if (got !== g.expected) { bad++; console.log("MISMATCH group", g.metric, "py:", g.expected, "js:", got); }
}
console.log(bad ? `${bad} mismatches` : `all ${fx.values.length + fx.groups.length} fixtures agree`);
process.exit(bad ? 1 : 0);
"""


def main() -> int:
    FIX.parent.mkdir(exist_ok=True)
    FIX.write_text(json.dumps(py_side(), indent=1) + "\n")
    runner = ROOT / "_format_check.mjs"
    runner.write_text(JS)
    try:
        r = subprocess.run(["node", str(runner)], cwd=ROOT, capture_output=True, text=True)
        print(r.stdout.strip())
        if r.stderr.strip():
            print(r.stderr.strip())
        return r.returncode
    finally:
        runner.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
