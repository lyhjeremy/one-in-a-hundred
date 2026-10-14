"""Write worker/src/catalogue.json from data/metrics.json so the Worker's
prompt and validator use the same metric ids, phrasings, activities and
country list as the site. Run after any change to metrics.json.

Usage: python3 pipeline/build_catalogue.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.format import COUNTRY_NAMES  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
M = json.loads((ROOT / "data" / "metrics.json").read_text())
INDEX = json.loads((ROOT / "data" / "index.json").read_text()) if (ROOT / "data" / "index.json").exists() else {"metrics": {}}

cat = {
    "metrics": {mid: {"label": m["label"], "phrasings": m["phrasings"], "activity": m.get("activity")}
                for mid, m in M["metrics"].items() if mid in INDEX["metrics"] or not INDEX["metrics"]},
    "activities": {aid: a["label"] for aid, a in M["activities"].items()},
    "countries": {cc: n.replace("the ", "") for cc, n in COUNTRY_NAMES.items()},
}
out = ROOT / "worker" / "src" / "catalogue.json"
out.write_text(json.dumps(cat, indent=1, ensure_ascii=False) + "\n")
print(f"catalogue: {len(cat['metrics'])} metrics, {len(cat['countries'])} countries -> {out.relative_to(ROOT)}")
