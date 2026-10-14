"""Terminal review loop for pipeline/inbox/*.json.

For each candidate fact: show the punchline, grid, sources, caveat. Keys:
  a  accept   -> status reviewed, moved into data/facts/<family>.json, verify assigns A/B/C
  e  edit     -> open in $EDITOR, then re-check
  g  lower the grade with a reason (review may only lower, never raise)
  r  reject with a reason -> pipeline/rejected/
  o  open the source URLs in the browser
  s  skip     q  quit
Every decision is one line in pipeline/review_log.jsonl.

Usage: python3 pipeline/review.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import webbrowser
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.format import punchline, grid_key_for  # noqa: E402
from pipeline.verify import structural_errors, grade  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
INBOX = ROOT / "pipeline" / "inbox"
REJECTED = ROOT / "pipeline" / "rejected"
LOG = ROOT / "pipeline" / "review_log.jsonl"
FACTS_DIR = ROOT / "data" / "facts"
METRICS = json.loads((ROOT / "data" / "metrics.json").read_text())["metrics"]


def log(fid: str, action: str, **kw) -> None:
    LOG.open("a").write(json.dumps({"id": fid, "action": action, "on": date.today().isoformat(), "by": "jeremy", **kw}) + "\n")


def show(f: dict) -> None:
    print("\n" + "=" * 72)
    print(f["id"])
    if f["metric"] in METRICS:
        pk = next((k for k in ("p99", "p90", "p50") if grid_key_for(f["direction"], k) in f["grid"]), None)
        if pk:
            print(punchline(f, pk))
    else:
        print("UNMAPPED metric:", f["metric"], "(add it to data/metrics.json before accepting)")
    print("grid:", f["grid"])
    print("definition:", f.get("definition"))
    if f.get("caveat"):
        print("caveat:", f["caveat"])
    for s in f["sources"]:
        print(f"  - {s['name']} | {s.get('measures', '')} | {s['url']}\n    values {s.get('values')} official={s.get('official')}")
    errs = structural_errors(f) if f["metric"] in METRICS else ["metric not in catalogue"]
    if errs:
        print("STRUCTURAL:", errs)
    else:
        g, reason, _ = grade({**f, "status": "reviewed"})
        print(f"would grade {g}: {reason}")


def accept(p: Path, f: dict) -> None:
    f["status"] = "reviewed"
    f["reviewed_by"] = "jeremy"
    f["reviewed_on"] = date.today().isoformat()
    fam = METRICS[f["metric"]]["family"]
    target = FACTS_DIR / f"{fam}.json"
    facts = json.loads(target.read_text()) if target.exists() else []
    facts = [x for x in facts if x["id"] != f["id"]] + [f]
    facts.sort(key=lambda x: x["id"])
    target.write_text(json.dumps(facts, indent=1, ensure_ascii=False) + "\n")
    p.unlink()
    log(f["id"], "accept")
    print("accepted; run build_facts.py to regrade and rebuild the index")


def main() -> None:
    files = sorted(INBOX.glob("*.json"))
    if not files:
        print("inbox empty")
        return
    print(f"{len(files)} facts to review")
    for p in files:
        f = json.loads(p.read_text())
        while True:
            show(f)
            k = input("[a]ccept [e]dit [g]rade-down [r]eject [o]pen [s]kip [q]uit > ").strip().lower()
            if k == "a":
                if f["metric"] not in METRICS or structural_errors(f):
                    print("cannot accept: fix the metric or structure first (e)")
                    continue
                accept(p, f)
                break
            if k == "e":
                subprocess.call([os.environ.get("EDITOR", "nano"), str(p)])
                f = json.loads(p.read_text())
                continue
            if k == "g":
                g = input("new grade (B/C): ").strip().upper()
                why = input("reason: ").strip()
                f["review_grade"], f["review_reason"] = g, why
                p.write_text(json.dumps(f, indent=1, ensure_ascii=False) + "\n")
                log(f["id"], "grade", grade=g, reason=why)
                continue
            if k == "r":
                why = input("reason: ").strip()
                REJECTED.mkdir(exist_ok=True)
                f["rejected_reason"] = why
                (REJECTED / p.name).write_text(json.dumps(f, indent=1, ensure_ascii=False) + "\n")
                p.unlink()
                log(f["id"], "reject", reason=why)
                break
            if k == "o":
                for s in f["sources"]:
                    webbrowser.open(s["url"])
                continue
            if k == "s":
                break
            if k == "q":
                return


if __name__ == "__main__":
    main()
