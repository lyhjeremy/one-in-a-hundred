"""Build data/semantic_index.json: one MiniLM embedding per canonical phrasing
of every measure, for the in-browser semantic parser (parser-semantic.js).

The phrasings come from the catalogue only, never from the eval sets: each
measure's label, short name, definition and keyword phrasings from
data/metrics.json, the question phrasings already in data/metrics_extra.json,
and three fixed templates applied to the short name. Core measures are
flagged `core` so the eval can score against the same catalogue as
eval/eval_parser.py.

Model: sentence-transformers/all-MiniLM-L6-v2 (fp32, mean pooling, L2
normalised), the same weights the browser runs as a q8 ONNX file. Vectors
are stored as int8 (value * 127, rounded) in base64; eval/semantic/parity.json
records how far the browser's q8 vectors sit from these.

Needs sentence-transformers (venv outside Drive):
  ~/venvs/<venv>/bin/python pipeline/build_semantic_index.py
"""
from __future__ import annotations

import base64
import hashlib
import json
from datetime import date
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "semantic_index.json"
MODEL = "sentence-transformers/all-MiniLM-L6-v2"
TEMPLATES = ["what {x} puts you in the top 1%", "median {x}", "how does my {x} compare"]


def phrasings() -> list[dict]:
    core = json.loads((ROOT / "data" / "metrics.json").read_text())["metrics"]
    extra = json.loads((ROOT / "data" / "metrics_extra.json").read_text())["metrics"]
    rows: list[dict] = []
    for is_core, cat in ((True, core), (False, extra)):
        for mid, md in cat.items():
            seen: set[str] = set()
            texts = [md["label"], md.get("short", ""), md.get("definition", "")]
            texts += md.get("phrasings", [])
            short = (md.get("short") or md["label"]).lower()
            texts += [t.format(x=short) for t in TEMPLATES]
            for t in texts:
                t = " ".join(t.split())
                if t and t.lower() not in seen:
                    seen.add(t.lower())
                    rows.append({"m": mid, "t": t, "core": is_core})
    return rows


def main() -> None:
    from sentence_transformers import SentenceTransformer

    rows = phrasings()
    model = SentenceTransformer(MODEL, device="cpu")
    vecs = model.encode([r["t"] for r in rows], normalize_embeddings=True, batch_size=64)
    q = np.clip(np.rint(vecs * 127), -127, 127).astype(np.int8)
    blob = base64.b64encode(q.tobytes()).decode()
    out = {
        "model": "all-MiniLM-L6-v2",
        "python_model": MODEL,
        "dim": int(vecs.shape[1]),
        "scale": 127,
        "built": date.today().isoformat(),
        "templates": TEMPLATES,
        "entries": rows,
        "q8": blob,
        "sha1": hashlib.sha1(q.tobytes()).hexdigest()[:12],
    }
    OUT.write_text(json.dumps(out, separators=(",", ":")))
    n_core = sum(r["core"] for r in rows)
    print(f"{len(rows)} phrasings ({n_core} core, {len(rows) - n_core} researched) -> {OUT.relative_to(ROOT)}, "
          f"{OUT.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
