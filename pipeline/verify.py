"""Verify every fact and assign confidence grades.

Reads data/facts/*.json, checks structure, computes per-point ranges and
agreement across sources, assigns A/B/C/D by the rules in pipeline.md
section 3, writes the grades back into the fact files and a report to
pipeline/verify_report.md. Exits non-zero on any structural failure so a bad
fact never reaches Pages.

Usage: python3 pipeline/verify.py [--check-only]
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FACTS_DIR = ROOT / "data" / "facts"
sys.path.insert(0, str(ROOT))
from pipeline.catalog import METRICS  # noqa: E402
OFFICIAL = set(json.loads((ROOT / "pipeline" / "official.json").read_text()))
AGREE = 0.10  # within 10%

EXPOSED = {
    "high": ["p50", "p90", "p99", "p99.9"],
    "low": ["p50", "p10", "p1", "p0.1"],
}
GRID_KEYS = ["p0.1", "p1", "p10", "p25", "p50", "p75", "p90", "p99", "p99.9"]


def pct_of(key: str) -> float:
    return float(key[1:])


def spread(values: list[float]) -> float:
    """|max - min| / mean, as a fraction. 0 for a single value."""
    if len(values) < 2:
        return 0.0
    lo, hi = min(values), max(values)
    mean = sum(values) / len(values)
    return abs(hi - lo) / mean if mean else 0.0


def independent_groups(sources: list[dict]) -> int:
    """Count mutually independent sources using the independent_of lists.

    Two sources are dependent unless each lists the other as independent (or
    the list is empty, meaning 'depends on nothing listed here' for a lone
    source). We count connected components of the dependency graph.
    """
    ids = [s["id"] for s in sources]
    indep = {s["id"]: set(s.get("independent_of", [])) for s in sources}
    parent = {i: i for i in ids}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a in ids:
        for b in ids:
            if a < b and not (b in indep[a] or a in indep[b]):
                parent[find(a)] = find(b)
    return len({find(i) for i in ids})


def structural_errors(fact: dict) -> list[str]:
    errs = []
    for k in ["id", "metric", "population", "year", "direction", "unit", "grid", "sources", "status"]:
        if k not in fact:
            errs.append(f"missing field {k}")
    if errs:
        return errs
    if fact["metric"] not in METRICS:
        errs.append(f"unknown metric {fact['metric']}")
    if fact["direction"] not in ("high", "low"):
        errs.append("direction must be high or low")
    if not fact["sources"]:
        errs.append("no sources")
    for s in fact["sources"]:
        for k in ["id", "name", "url", "accessed"]:
            if not s.get(k):
                errs.append(f"source {s.get('id', '?')} missing {k}")
    if not fact["grid"]:
        errs.append("empty grid")
    for k in fact["grid"]:
        if k not in GRID_KEYS:
            errs.append(f"bad grid key {k}")
    # Grid keys are cumulative shares from the low end of the value scale, so
    # values never decrease with the key, whatever the direction. Direction
    # only decides which tail the UI calls "top".
    keys = sorted((k for k in fact["grid"] if k in GRID_KEYS), key=pct_of)
    vals = [fact["grid"][k] for k in keys]
    if not all(a <= b for a, b in zip(vals, vals[1:])):
        errs.append(f"grid not monotone: {dict(zip(keys, vals))}")
    if fact.get("n") is not None and fact["n"] <= 0:
        errs.append("n must be positive")
    return errs


def grade(fact: dict) -> tuple[str, str, dict]:
    """Return (grade, reason, per_point) for a fact."""
    exposed = [k for k in EXPOSED[fact["direction"]] if k in fact["grid"]]
    srcs = fact["sources"]
    per_point: dict[str, dict] = {}
    for k in exposed:
        vals = [s["values"][k] for s in srcs if k in s.get("values", {})]
        per_point[k] = {"values": vals, "spread": spread(vals), "n_sources": len(vals)}

    if fact["status"] == "queued":
        return "D", f"Researched automatically on {fact.get('added', 'an unknown date')}; not yet checked by a person.", per_point

    official = [s for s in srcs if s["id"] in OFFICIAL or s.get("official")]
    n_indep = independent_groups(srcs)
    worst = max((p["spread"] for p in per_point.values()), default=0.0)
    worst_key = max(per_point, key=lambda k: per_point[k]["spread"]) if per_point else None
    derived_keys = set(fact.get("derived_points", []))
    multi = [k for k in exposed if per_point[k]["n_sources"] >= 2]

    if worst > AGREE:
        p = per_point[worst_key]
        lo, hi = min(p["values"]), max(p["values"])
        return "C", (f"Sources disagree by {worst * 100:.0f}% at the {label(worst_key, fact)}: "
                     f"{lo:,.0f} vs {hi:,.0f}. The range shows both."), per_point
    if fact.get("definition_mismatch"):
        return "C", fact["definition_mismatch"], per_point

    # Derived exposed points block A unless a second source confirms that point.
    unconfirmed_derived = [k for k in derived_keys if k in exposed and per_point.get(k, {}).get("n_sources", 0) < 2]

    if n_indep >= 2 and official and multi and len(multi) == len(exposed) and not unconfirmed_derived:
        return "A", (f"{n_indep} independent sources agree within {max(worst * 100, 1):.0f}% "
                     f"at every shown percentile."), per_point
    if unconfirmed_derived and official:
        return "B", "Top percentiles derived from a published mean and spread, not measured.", per_point
    if official:
        return "B", f"One official source ({official[0]['name']}); no second source to compare.", per_point
    if n_indep >= 2 and multi:
        return "B", f"{n_indep} independent non-official sources agree within {max(worst * 100, 1):.0f}%.", per_point
    return "C", f"Single non-official source ({srcs[0]['name']}).", per_point


def label(key: str, fact: dict) -> str:
    """'top 1%' / 'median' for a grid key, respecting direction."""
    p = pct_of(key)
    if p == 50:
        return "median"
    top = (100 - p) if fact["direction"] == "high" else p
    return f"top {top:g}%"


def main(check_only: bool = False) -> int:
    files = sorted(FACTS_DIR.glob("*.json"))
    all_facts = []
    errors = []
    for f in files:
        facts = json.loads(f.read_text())
        for fact in facts:
            errs = structural_errors(fact)
            if errs:
                errors.append((fact.get("id", f.name), errs))
                continue
            g, reason, per_point = grade(fact)
            if fact.get("review_grade") and fact["review_grade"] < g:
                # Review may only lower a grade (A < B < C < D as strings, conveniently).
                pass
            if fact.get("review_grade") and fact["review_grade"] > g:
                g, reason = fact["review_grade"], fact.get("review_reason", reason)
            fact["grade"] = g
            fact["reason"] = fact.get("reason_override") or reason
            fact["range"] = {k: [min(p["values"]), max(p["values"])] for k, p in per_point.items() if p["values"]}
            fact["agreement"] = {k: round(p["spread"], 4) for k, p in per_point.items()}
            fact["n_sources"] = {k: p["n_sources"] for k, p in per_point.items()}
            all_facts.append(fact)
        if not check_only and not errors:
            f.write_text(json.dumps(facts, indent=1, ensure_ascii=False) + "\n")

    ids = Counter(f["id"] for f in all_facts)
    for i, c in ids.items():
        if c > 1:
            errors.append((i, [f"duplicate id ({c})"]))

    report = build_report(all_facts, errors)
    (ROOT / "pipeline" / "verify_report.md").write_text(report)
    print(report)
    return 1 if errors else 0


def build_report(facts: list[dict], errors) -> str:
    by_grade = Counter(f["grade"] for f in facts)
    by_fam = defaultdict(Counter)
    for f in facts:
        by_fam[METRICS[f["metric"]]["family"]][f["grade"]] += 1
    multi = [f for f in facts if any(n >= 2 for n in f["n_sources"].values()) and f["status"] != "queued"]
    agree = [f for f in multi if max(f["agreement"].values()) <= AGREE]
    worst = sorted(multi, key=lambda f: -max(f["agreement"].values() or [0]))[:10]
    single = [f["id"] for f in facts if all(n < 2 for n in f["n_sources"].values())]
    lines = ["# Verify report", "", f"Facts: {len(facts)}. Errors: {len(errors)}.", ""]
    lines += ["## By grade", ""] + [f"- {g}: {by_grade.get(g, 0)}" for g in "ABCD"] + [""]
    lines += ["## By family", ""]
    for fam, c in sorted(by_fam.items()):
        lines.append(f"- {fam}: " + ", ".join(f"{g} {c.get(g, 0)}" for g in "ABCD"))
    lines += ["", "## Source agreement", "",
              f"Facts with two or more sources at a shown percentile: {len(multi)}. "
              f"Of those, within {AGREE:.0%} at every shown percentile: {len(agree)} "
              f"({(len(agree) / len(multi) * 100) if multi else 0:.0f}%).", "",
              "## Ten widest disagreements", ""]
    for f in worst:
        k = max(f["agreement"], key=f["agreement"].get) if f["agreement"] else "-"
        lines.append(f"- {f['id']}: {f['agreement'].get(k, 0) * 100:.0f}% at {k}")
    lines += ["", f"## Single-source facts: {len(single)} of {len(facts)}", ""]
    by_metric = Counter(i.split(".")[0] for i in single)
    lines += [f"- {m}: {c}" for m, c in sorted(by_metric.items())]
    if errors:
        lines += ["", "## Errors", ""] + [f"- {i}: {'; '.join(e)}" for i, e in errors]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    sys.exit(main(check_only="--check-only" in sys.argv))
