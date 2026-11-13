"""Freeze eval/semantic/dev.jsonl, the tuning split for the semantic parser.

Provenance: dev_prompt.txt was sent once to Claude Sonnet through
`claude -p --model sonnet` on 2026-11-13 (API-equivalent cost reported by the
Claude CLI: $0.16). The model wrote both the questions and their expected
triples; no person labeled them. Its raw output is dev_raw_sonnet.jsonl.

This script drops any dev question that overlaps the frozen gold set
(eval/gold.jsonl): an exact match after normalising, or a word-set Jaccard
similarity of 0.5 or more with any gold question. The gold set is never used
for tuning; it is scored once with the settings chosen on this split.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
GOLD = HERE.parent / "gold.jsonl"


def words(q: str) -> set[str]:
    return set(re.sub(r"[^a-z0-9%]+", " ", q.lower()).split())


def main() -> None:
    gold = [words(json.loads(l)["q"]) for l in GOLD.read_text().splitlines() if l.strip()]
    kept, dropped = [], []
    for line in (HERE / "dev_raw_sonnet.jsonl").read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        w = words(row["q"])
        sim = max((len(w & g) / len(w | g) if (w | g) else 1.0) for g in gold)
        (dropped if sim >= 0.5 else kept).append((row, round(sim, 2)))
    out = HERE / "dev.jsonl"
    out.write_text("".join(json.dumps(r) + "\n" for r, _ in kept))
    print(f"kept {len(kept)}, dropped {len(dropped)} for overlap with gold:")
    for r, s in dropped:
        print(f"  {s:.2f}  {r['q']}")
    print("dev sha1", hashlib.sha1(out.read_bytes()).hexdigest()[:12])


if __name__ == "__main__":
    main()
