"""Compare the browser's q8 MiniLM vectors with sentence-transformers fp32.

Reads browser_vectors_sample.json (written by eval_semantic.py), embeds the
same texts in Python, and writes parity.json with the cosine between the two
for each text, plus the cosine between the stored int8 index vectors and
fp32 for every index entry. Run in a venv with sentence-transformers, then
rerun eval_semantic.py (or just its write_md) to refresh results.md.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent

s = json.loads((HERE / "browser_vectors_sample.json").read_text())
model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2", device="cpu")
py = model.encode(s["texts"], normalize_embeddings=True)
br = np.array(s["vectors"], dtype=np.float32)
br /= np.linalg.norm(br, axis=1, keepdims=True)
cos = (py * br).sum(1)

idx = json.loads((ROOT / "data" / "semantic_index.json").read_text())
q = np.frombuffer(base64.b64decode(idx["q8"]), dtype=np.int8).reshape(len(idx["entries"]), idx["dim"]).astype(np.float32)
q /= np.linalg.norm(q, axis=1, keepdims=True)
fp = model.encode([e["t"] for e in idx["entries"]], normalize_embeddings=True, batch_size=64)
c2 = (q * fp).sum(1)

out = {
    "n": len(cos),
    "browser_vs_python": {"min": round(float(cos.min()), 4), "mean": round(float(cos.mean()), 4)},
    "int8_vs_fp32": {"n": len(c2), "min": round(float(c2.min()), 4), "mean": round(float(c2.mean()), 4)},
    "per_text": [{"text": t, "cos": round(float(c), 4)} for t, c in zip(s["texts"], cos)],
}
(HERE / "parity.json").write_text(json.dumps(out, indent=1))
print(json.dumps({k: out[k] for k in ("n", "browser_vs_python", "int8_vs_fp32")}))
