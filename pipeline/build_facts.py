"""Build data/facts/<family>.json and data/index.json from the fetchers.

Groups fetcher Rows by (metric, population, year) into facts, merges sources,
attaches n from UN WPP where the fetcher did not supply one, folds in
pipeline/inbox/*.json (queued facts), then calls verify.py.

Usage: python3 pipeline/build_facts.py
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.fetch import common  # noqa: E402
from pipeline.fetch import un_wpp, cdc_nhanes, ncdrisc_height, ncdrisc_bmi, wid, wb_pip, running, who_ghe, booth_marathon  # noqa: E402
from pipeline import verify  # noqa: E402

ROOT = common.ROOT
from pipeline import catalog  # noqa: E402
METRICS = catalog.CATALOG
FACTS_DIR = ROOT / "data" / "facts"
INBOX = ROOT / "pipeline" / "inbox"

FETCHERS = [un_wpp, who_ghe, wid, wb_pip, cdc_nhanes, ncdrisc_height, ncdrisc_bmi, booth_marathon, running]
N_NAMES = {m.SOURCE["id"]: m.SOURCE["name"] for m in FETCHERS}


def pop_key(r: common.Row) -> tuple:
    return (r.metric, r.base, r.country, r.sex, r.age_band, r.activity, r.source_category)


def fact_id(k: tuple, year: int) -> str:
    metric, base, country, sex, band, activity, cat = k
    parts = [metric, country.lower() if country else "world", sex]
    if band:
        parts.append(band.replace("+", "plus"))
    if activity:
        parts.append(activity)
    if cat:
        parts.append(cat.lower().replace(" ", "-").replace(",", ""))
    parts.append(str(year))
    return ".".join(parts)


def main() -> int:
    skip = set()
    if "--skip" in sys.argv:
        skip = set(sys.argv[sys.argv.index("--skip") + 1].split(","))
    rows: list[common.Row] = []
    sources: dict[str, dict] = {}
    for mod in FETCHERS:
        if mod.__name__.rsplit(".", 1)[-1] in skip:
            print(f"skipping {mod.__name__}")
            continue
        kwargs = {"population_fn": un_wpp.population} if "population_fn" in mod.load.__code__.co_varnames else {}
        got = mod.load(**kwargs)
        print(f"{mod.SOURCE['id']}: {len(got)} rows")
        rows += got
        meta = common.read_meta(mod.SOURCE["id"])
        sources[mod.SOURCE["id"]] = {**mod.SOURCE, "accessed": meta.get("accessed", date.today().isoformat())}

    groups: dict[tuple, list[common.Row]] = defaultdict(list)
    for r in rows:
        groups[pop_key(r)].append(r)

    facts_by_family: dict[str, list[dict]] = defaultdict(list)
    for k, all_rs in groups.items():
        metric = METRICS["metrics"][k[0]]
        year = max(r.year for r in all_rs)
        rs = [r for r in all_rs if r.year == year]
        # Earlier years become the time series, but only from the same sources that
        # make the latest-year fact; a derived series must not pose as the history
        # of a measured one.
        latest_sources = {r.source_id for r in rs}
        series: dict[str, dict] = {}
        for r in all_rs:
            if r.year != year and r.source_id in latest_sources:
                series.setdefault(str(r.year), {}).setdefault(r.percentile, []).append(r.value)
        series = {y: {pk: round(sum(v) / len(v), 4) for pk, v in d.items()} for y, d in sorted(series.items())}
        by_src: dict[str, dict] = defaultdict(dict)
        derived_points = set()
        n = None
        n_source = None
        notes = set()
        for r in rs:
            by_src[r.source_id][r.percentile] = r.value
            if r.derived:
                derived_points.add(r.percentile)
            if r.n and n is None:
                n, n_source = r.n, (r.n_source or r.source_id)
            if r.note:
                notes.add(r.note)
        # Grid: mean across sources per point (the range is kept separately by verify).
        grid = {}
        for pk in {p for s in by_src.values() for p in s}:
            vals = [s[pk] for s in by_src.values() if pk in s]
            grid[pk] = round(sum(vals) / len(vals), 4)
        src_list = []
        for sid, vals in by_src.items():
            s = dict(sources[sid])
            s["values"] = vals
            src_list.append(s)
        metric_id, base, country, sex, band, activity, cat = k
        fact = {
            "id": fact_id(k, year),
            "metric": metric_id,
            "population": {"base": base, "country": country, "sex": sex, "age_band": band,
                            "activity": activity, "source_category": cat},
            "year": year,
            "n": round(n) if n else None,
            "n_source": n_source,
            "n_source_name": N_NAMES.get(n_source, n_source),
            "direction": metric["direction"],
            "unit": metric["unit"],
            "grid": dict(sorted(grid.items(), key=lambda kv: float(kv[0][1:]))),
            "sources": src_list,
            "definition": metric["definition"],
            "derived_points": sorted(derived_points),
            "caveat": " ".join(sorted(notes)) if notes else None,
            "series": series or None,
            "status": "curated",
            "added": date.today().isoformat(),
        }
        facts_by_family[metric["family"]].append(fact)

    # Metrics defined by the research loop: merge into data/metrics_extra.json first.
    extra_path = ROOT / "data" / "metrics_extra.json"
    extra = json.loads(extra_path.read_text()) if extra_path.exists() else {"metrics": {}, "activities": {}}
    for p in sorted((INBOX / "metrics").glob("*.json")) if (INBOX / "metrics").exists() else []:
        m = json.loads(p.read_text())
        mid = m.pop("id", p.stem)
        act = m.pop("activity", None)
        act_label = m.pop("activity_label", None)
        if act:
            extra["activities"][act] = {"label": act_label or act.replace("_", " "), "metric": mid}
            m["activity"] = act
        m.setdefault("family", "more")
        extra["metrics"][mid] = {**extra["metrics"].get(mid, {}), **m}
    # A researched fact can reuse a catalogue measure with a group of its own
    # (height of NBA players); register that group so its label resolves.
    for p in sorted(INBOX.glob("*.json")):
        f = json.loads(p.read_text())
        act = f.get("population", {}).get("activity")
        if act and act not in METRICS["activities"] and act not in extra["activities"]:
            extra["activities"][act] = {"label": act.replace("_", " "), "metric": f["metric"]}
    extra_path.write_text(json.dumps(extra, indent=1, ensure_ascii=False) + "\n")
    for mid, m in extra["metrics"].items():
        METRICS["metrics"].setdefault(mid, m)
    METRICS["activities"].update(extra["activities"])

    # Value range of each curated measure, to catch researched facts in the wrong unit.
    curated_range: dict[str, tuple[float, float]] = {}
    for facts in facts_by_family.values():
        for cf in facts:
            vals = list(cf["grid"].values())
            lo, hi = curated_range.get(cf["metric"], (min(vals), max(vals)))
            curated_range[cf["metric"]] = (min(lo, *vals), max(hi, *vals))

    # Queued facts from the research loop ship alongside, flagged by status.
    for p in sorted(INBOX.glob("*.json")):
        f = json.loads(p.read_text())
        if f["metric"] not in METRICS["metrics"]:
            print(f"inbox: skipping {f['id']}, metric {f['metric']} not in catalogue")
            continue
        errs = verify.structural_errors(f)
        if errs:
            # A bad research result must never break the build; it waits for review.
            print(f"inbox: skipping {f['id']}: {'; '.join(errs)}")
            continue
        lo_hi = curated_range.get(f["metric"])
        if lo_hi and any(v < lo_hi[0] / 1.5 or v > lo_hi[1] * 1.5 for v in f["grid"].values()):
            # Usually a unit slip (inches given for a centimetre measure).
            print(f"inbox: skipping {f['id']}: values {f['grid']} far outside curated range {lo_hi}")
            continue
        fam = METRICS["metrics"][f["metric"]]["family"]
        facts_by_family[fam].append(f)

    FACTS_DIR.mkdir(parents=True, exist_ok=True)
    total = 0
    for fam, facts in facts_by_family.items():
        facts.sort(key=lambda f: f["id"])
        (FACTS_DIR / f"{fam}.json").write_text(json.dumps(facts, indent=1, ensure_ascii=False) + "\n")
        total += len(facts)
    print(f"{total} facts across {len(facts_by_family)} families")

    rc = verify.main()
    build_index()
    return rc


def build_index() -> None:
    """data/index.json: for each metric, the population slices that exist and
    the grid keys each has, so the UI can decide which chips to show without
    loading every fact. Also a flat id list and counts for the overview."""
    index = {"metrics": {}, "facts": {}, "built": date.today().isoformat()}
    for p in FACTS_DIR.glob("*.json"):
        for f in json.loads(p.read_text()):
            m = index["metrics"].setdefault(f["metric"], {"slices": []})
            pop = f["population"]
            m["slices"].append({"id": f["id"], **pop, "year": f["year"], "grade": f["grade"],
                                "keys": list(f["grid"].keys()), "status": f["status"]})
            index["facts"][f["id"]] = {"family": METRICS["metrics"][f["metric"]]["family"], "grade": f["grade"]}
    (ROOT / "data" / "index.json").write_text(json.dumps(index, separators=(",", ":"), ensure_ascii=False) + "\n")
    print(f"index: {len(index['facts'])} facts, {len(index['metrics'])} metrics")


if __name__ == "__main__":
    sys.exit(main())
