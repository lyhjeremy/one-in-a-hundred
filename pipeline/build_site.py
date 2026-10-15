"""Generate the static pages that derive from the fact data:
sources/index.html (every source with licence, access date and fact count)
and data/meta.json (build date, counts by grade and family).

Usage: python3 pipeline/build_site.py
"""
from __future__ import annotations

import html
import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FACTS_DIR = ROOT / "data" / "facts"
METRICS = json.loads((ROOT / "data" / "metrics.json").read_text())["metrics"]

LICENCES = {
    "src-un-wpp-2024": "CC BY 3.0 IGO",
    "src-who-ghe": "CC BY-NC-SA 3.0 IGO",
    "src-wid": "CC BY 4.0",
    "src-wb-pip": "CC BY 4.0",
    "src-cdc-nhanes": "Public domain (US government)",
    "src-ncdrisc-height": "CC BY 4.0",
    "src-ncdrisc-bmi": "CC BY 4.0",
    "src-kaggle-us-marathons-2023": "As stated on the Kaggle page",
    "src-booth-marathon": "Research data published by the authors; cite Allen, Dechow, Pope and Wu (2017)",
}

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sources</title>
<link rel="stylesheet" href="../assets/ledger.css"><link rel="stylesheet" href="../assets/app.css"></head>
<body><main class="wrap wrap-wide">
<p class="kicker"><a href="../">One in a Hundred</a></p>
<h1>Sources</h1>
<p class="meta">Built {built}. {n_facts} facts from {n_sources} sources. Grades: {grades}.</p>
<p>Every fact on the site traces to at least one row in this table. Raw downloads are not redistributed; the fetch scripts in the repository re-create them. Where a source publishes means rather than percentiles, the fact says the percentile is derived and the grade is capped at B.</p>
<div class="table-scroll"><table>
<thead><tr><th>Source</th><th>What it measures</th><th>Licence</th><th>Accessed</th><th class="num">Facts</th><th>Metrics</th></tr></thead>
<tbody>{rows}</tbody></table></div>
<h2>How grades work</h2>
<p>A: two or more independent sources, at least one official, agreeing within 10% at every shown percentile. B: one official source, or a derived percentile. C: sources disagree by more than 10%, or a known definitional mismatch. D: produced by the automated research step and not yet reviewed by a person.</p>
</main>
<footer class="wrap site-footer"><p><a href="../">Home</a> · <a href="../overview/">How this works</a> · <a href="../privacy/">Privacy</a> · <a href="../terms/">Terms</a></p></footer>
</body></html>
"""


def main() -> None:
    facts = []
    for p in sorted(FACTS_DIR.glob("*.json")):
        facts += json.loads(p.read_text())
    by_src: dict[str, dict] = {}
    count: Counter = Counter()
    metrics_by_src: dict[str, set] = defaultdict(set)
    for f in facts:
        for s in f["sources"]:
            by_src.setdefault(s["id"], s)
            count[s["id"]] += 1
            metrics_by_src[s["id"]].add(METRICS[f["metric"]]["label"])
    rows = []
    for sid, s in sorted(by_src.items(), key=lambda kv: -count[kv[0]]):
        rows.append(
            f"<tr><td><a href=\"{html.escape(s['url'])}\">{html.escape(s['name'])}</a><br><code>{sid}</code></td>"
            f"<td>{html.escape(s.get('measures', ''))}</td><td>{html.escape(LICENCES.get(sid, 'see source'))}</td>"
            f"<td>{html.escape(s.get('accessed', ''))}</td><td class=\"num\">{count[sid]}</td>"
            f"<td>{html.escape(', '.join(sorted(metrics_by_src[sid])))}</td></tr>")
    grades = Counter(f["grade"] for f in facts)
    fams = Counter(METRICS[f["metric"]]["family"] for f in facts)
    built = date.today().isoformat()
    (ROOT / "sources").mkdir(exist_ok=True)
    (ROOT / "sources" / "index.html").write_text(PAGE.format(
        built=built, n_facts=len(facts), n_sources=len(by_src),
        grades=", ".join(f"{g} {grades.get(g, 0)}" for g in "ABCD"), rows="".join(rows)))
    meta = {"built": built, "facts": len(facts), "grades": dict(grades), "families": dict(fams),
            "sources": len(by_src), "next_queue_run": None}
    (ROOT / "data" / "meta.json").write_text(json.dumps(meta, indent=1) + "\n")
    print(f"sources page: {len(by_src)} sources, {len(facts)} facts; meta.json written")


if __name__ == "__main__":
    main()
