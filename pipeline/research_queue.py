"""Pull the KV queue, research each question group with `claude -p`, write
D-grade candidate facts to pipeline/inbox/, delete processed entries.

Env: CF_API_TOKEN, CF_ACCOUNT_ID, CF_KV_NAMESPACE_ID (never in the repo).
Usage: python3 pipeline/research_queue.py [--dry-run] [--limit N] [--from-file q.jsonl]

The raw questions are written to pipeline/queue/ (git-ignored) and deleted at
the end of the run. Refuses to start when the inbox holds 60 or more facts.
Stops after three consecutive failures (quota or network).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.verify import structural_errors  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
QUEUE_DIR = ROOT / "pipeline" / "queue"
INBOX = ROOT / "pipeline" / "inbox"
REJECTED = ROOT / "pipeline" / "rejected"
PROMPT = (ROOT / "pipeline" / "prompts" / "research.md").read_text()
SCHEMA = (ROOT / "pipeline" / "schemas" / "research.json").read_text()
from pipeline.catalog import CATALOG as METRICS  # noqa: E402
INDEX = json.loads((ROOT / "data" / "index.json").read_text())
INBOX_CAP = 60
RUN_CAP = 60
# Seed questions already researched (not visitor text, so safe to commit).
DONE = ROOT / "pipeline" / "seeds" / "done.txt"

UNIT_FOR = {m: v["unit"] for m, v in METRICS["metrics"].items()}


def cf(path: str, method: str = "GET", data: bytes | None = None) -> dict | bytes:
    tok, acct, ns = os.environ.get("CF_API_TOKEN"), os.environ.get("CF_ACCOUNT_ID"), os.environ.get("CF_KV_NAMESPACE_ID")
    if not (tok and acct and ns):
        raise SystemExit("set CF_API_TOKEN, CF_ACCOUNT_ID, CF_KV_NAMESPACE_ID")
    url = f"https://api.cloudflare.com/client/v4/accounts/{acct}/storage/kv/namespaces/{ns}/{path}"
    req = urllib.request.Request(url, data=data, method=method, headers={"authorization": f"Bearer {tok}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        body = r.read()
    try:
        return json.loads(body.decode())
    except ValueError:
        return body


def pull_queue() -> list[dict]:
    keys = cf("keys?prefix=q%3A&limit=1000")["result"]
    out = []
    for k in keys:
        v = cf(f"values/{k['name']}")
        try:
            d = json.loads(v if isinstance(v, str) else v.decode())
        except Exception:  # noqa: BLE001
            continue
        d["key"] = k["name"]
        out.append(d)
    return out


def normalise(q: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9%$:.\-\s]", " ", q.lower().replace("'", ""))).strip()


def group_key(entry: dict) -> str:
    t = entry.get("triple")
    if t and t.get("metric"):
        p = t.get("population", {})
        return f"{t['metric']}|{p.get('country')}|{p.get('sex')}|{p.get('age_band')}|{t.get('percentile')}"
    return "q|" + normalise(entry["q"])


def already_answered(entry: dict) -> bool:
    t = entry.get("triple")
    if not (t and t.get("metric") and t["metric"] in INDEX["metrics"]):
        return False
    p = t.get("population", {})
    for s in INDEX["metrics"][t["metric"]]["slices"]:
        if all((s.get(k) or None) == (p.get(k) or None) for k in ("country", "age_band", "source_category")) and (s.get("sex") or "all") == (p.get("sex") or "all"):
            return True
    return False


def research(questions: list[str]) -> dict:
    ids = ", ".join(sorted(METRICS["metrics"]))
    user = ("Questions:\n" + "\n".join(f"<<<{q}>>>" for q in questions) +
            f"\n\nCatalogue metric ids (use one of these for catalogue_metric, else null and fill new_metric): {ids}\n\nSchema:\n" + SCHEMA)
    cmd = ["claude", "-p", "--output-format", "json", "--allowedTools", "WebSearch,WebFetch", "--append-system-prompt", PROMPT]
    r = subprocess.run(cmd, input=user, capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-400:])
    outer = json.loads(r.stdout)
    text = outer.get("result", "") if isinstance(outer, dict) else str(outer)
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise RuntimeError("no JSON in response")
    return json.loads(m.group(0))


def to_fact(res: dict, questions: list[str]) -> dict | None:
    if not res.get("found"):
        return None
    t = res["triple"]
    metric = t.get("catalogue_metric")
    new_metric = None
    if not metric or metric not in METRICS["metrics"]:
        nm = res.get("new_metric")
        if nm and nm.get("id"):
            metric = re.sub(r"[^a-z0-9_]", "_", nm["id"].lower())
            new_metric = {k: nm.get(k) for k in ("label", "short", "unit", "direction", "format", "metric_phrase",
                                                  "base_noun", "definition", "phrasings", "activity", "activity_label")}
            new_metric["id"] = metric
        else:
            metric = None
    pop = t.get("population", {})
    act_raw = (new_metric or {}).get("activity") or pop.get("activity")
    act = re.sub(r"[^a-z0-9]+", "_", str(act_raw).lower()).strip("_") if act_raw else None
    if new_metric and act:
        new_metric["activity"] = act
        new_metric["activity_label"] = new_metric.get("activity_label") or (f"who are {act_raw}" if not str(act_raw).lower().startswith("who ") else str(act_raw))
    pop = {"base": pop.get("base", "world"), "country": pop.get("country"), "sex": pop.get("sex", "all"),
           "age_band": pop.get("age_band"), "activity": act, "source_category": None}
    direction = t.get("direction") or (new_metric["direction"] if new_metric else (METRICS["metrics"][metric]["direction"] if metric else "high"))
    grid: dict[str, list[float]] = {}
    sources = []
    year = None
    for s in res.get("sources", []):
        vals = {k: float(v) for k, v in (s.get("values") or {}).items() if re.fullmatch(r"p(0\.1|1|10|25|50|75|90|99|99\.9)", k)}
        if not vals:
            continue
        year = year or s.get("year")
        sid = "src-q-" + re.sub(r"[^a-z0-9]+", "-", s["name"].lower())[:40].strip("-")
        sources.append({"id": sid, "name": s["name"], "url": s["url"], "accessed": date.today().isoformat(),
                        "measures": s.get("measures", ""), "values": vals, "independent_of": [],
                        "official": s.get("publisher_type") == "official", "unit_as_published": s.get("unit_as_published"),
                        "notes": s.get("notes")})
        for k, v in vals.items():
            grid.setdefault(k, []).append(v)
    if not sources or not year:
        return None
    parts = [metric or re.sub(r"[^a-z0-9]+", "_", t["metric_phrase"].lower()).strip("_"),
             (pop["country"] or "world").lower(), pop["sex"]]
    if pop["age_band"]:
        parts.append(pop["age_band"].replace("+", "plus"))
    if pop["activity"]:
        parts.append(pop["activity"])
    parts.append(str(year))
    fact = {
        "id": ".".join(parts), "metric": metric or "unmapped:" + t["metric_phrase"], "population": pop, "year": int(year),
        "n": None, "n_source": None, "direction": direction, "unit": (new_metric or {}).get("unit") or t.get("unit") or (UNIT_FOR.get(metric) if metric else "unknown"),
        "grid": {k: round(sum(v) / len(v), 4) for k, v in grid.items()}, "sources": sources,
        "definition": sources[0]["measures"], "derived_points": [], "caveat": res.get("caveat"),
        "status": "queued", "added": date.today().isoformat(), "questions_n": len(questions),
    }
    if new_metric:
        fact["new_metric"] = new_metric
    return fact


def main() -> int:
    dry = "--dry-run" in sys.argv
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else RUN_CAP
    INBOX.mkdir(exist_ok=True)
    if len(list(INBOX.glob("*.json"))) >= INBOX_CAP:
        print(f"inbox has {INBOX_CAP}+ unreviewed facts; review first (python3 pipeline/review.py)")
        return 2
    if "--from-file" in sys.argv:
        entries = [json.loads(l) for l in Path(sys.argv[sys.argv.index("--from-file") + 1]).read_text().splitlines() if l.strip()]
    else:
        entries = pull_queue()
    QUEUE_DIR.mkdir(exist_ok=True)
    snap = QUEUE_DIR / f"{date.today().isoformat()}.jsonl"
    snap.write_text("\n".join(json.dumps(e) for e in entries) + "\n")
    print(f"{len(entries)} queued entries")
    groups: dict[str, list[dict]] = {}
    for e in entries:
        groups.setdefault(group_key(e), []).append(e)
    done_keys = []
    failures = 0
    processed = 0
    for gk, es in groups.items():
        if processed >= limit:
            break
        done = set(DONE.read_text().splitlines()) if DONE.exists() else set()
        if "--from-file" in sys.argv and normalise(es[0]["q"]) in done:
            continue
        if already_answered(es[0]):
            done_keys += [e["key"] for e in es if "key" in e]
            continue
        qs = [e["q"] for e in es]
        print(f"researching: {qs[0][:80]!r} (+{len(qs) - 1})")
        if dry:
            continue
        try:
            res = research(qs)
            fact = to_fact(res, qs)
        except Exception as e:  # noqa: BLE001
            failures += 1
            (QUEUE_DIR / "failed.jsonl").open("a").write(json.dumps({"group": gk, "error": str(e)[:200]}) + "\n")
            print("  failed:", str(e)[:120])
            if failures >= 3:
                print("three consecutive failures; stopping")
                break
            continue
        failures = 0
        processed += 1
        if "--from-file" in sys.argv:
            with DONE.open("a") as fh:
                fh.write(normalise(qs[0]) + "\n")
        if not fact:
            REJECTED.mkdir(exist_ok=True)
            (REJECTED / f"nofound-{abs(hash(gk)) % 10**8}.json").write_text(json.dumps({"group": gk, "result": res}, indent=1))
            print("  nothing credible found")
        else:
            errs = structural_errors(fact) if (fact["metric"] in METRICS["metrics"] or fact.get("new_metric")) else []
            if errs:
                print("  structural errors:", errs)
            (INBOX / f"{fact['id']}.json").write_text(json.dumps(fact, indent=1, ensure_ascii=False) + "\n")
            if fact.get("new_metric"):
                mdir = INBOX / "metrics"
                mdir.mkdir(exist_ok=True)
                (mdir / f"{fact['metric']}.json").write_text(json.dumps(fact["new_metric"], indent=1, ensure_ascii=False) + "\n")
            print("  inbox:", fact["id"])
        done_keys += [e["key"] for e in es if "key" in e]
    if not dry and "--from-file" not in sys.argv:
        for k in done_keys:
            try:
                cf(f"values/{k}", method="DELETE")
            except Exception as e:  # noqa: BLE001
                print("could not delete", k, e)
    # Raw text leaves the machine with the snapshot.
    snap.unlink(missing_ok=True)
    meta_p = ROOT / "data" / "meta.json"
    meta = json.loads(meta_p.read_text()) if meta_p.exists() else {}
    meta["last_queue_run"] = date.today().isoformat()
    meta_p.write_text(json.dumps(meta, indent=1) + "\n")
    print(f"processed {processed} groups; inbox now {len(list(INBOX.glob('*.json')))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
