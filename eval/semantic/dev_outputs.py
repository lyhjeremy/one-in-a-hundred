"""Write per-question dev-split outputs for the rules parser and the chosen hybrid.

eval_semantic.py tunes on the dev split but only saves the aggregate counts. This
reruns the dev split once with the settings it chose (read from results.json),
through the same harness and shipped model, and writes eval/semantic/dev_outputs.jsonl
plus a summary of which questions the hybrid gets right and the rules miss, and the
reverse. It does not touch results.json.

Usage: python3 eval/semantic/dev_outputs.py (needs playwright; PORT picks the port, default 8851).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "eval"))
from eval_parser import score  # noqa: E402

PORT = int(os.environ.get("PORT", "8851"))


def row(o: dict, r: dict) -> dict:
    return {"metric": o.get("metric"), "country": o["population"].get("country"),
            "sex": o["population"].get("sex"), "age_band": o["population"].get("age_band"),
            "percentile": o.get("percentile"), "value": o.get("value"),
            "parser": o.get("parser"), "exact": score(o, r)["exact"]}


def main() -> int:
    from playwright.sync_api import sync_playwright

    dev = [json.loads(l) for l in (HERE / "dev.jsonl").read_text().splitlines() if l.strip()]
    res = json.loads((HERE / "results.json").read_text())
    cfg = res["dev"]["chosen_hybrid"]
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT), "--bind", "127.0.0.1"], cwd=ROOT,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.0)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chromium")
            page = browser.new_page()
            page.goto(f"http://127.0.0.1:{PORT}/eval/semantic/harness.html")
            page.wait_for_function("document.getElementById('status').textContent === 'ready'", timeout=60000)
            page.evaluate("setup()")
            emb = page.evaluate("qs => embedAll(qs)", [r["q"] for r in dev])
            rules = page.evaluate("combineAll('rules', null)")
            hybrid = page.evaluate("([m, c]) => combineAll(m, c)", ["hybrid", cfg])
            browser.close()
    finally:
        srv.terminate()

    gained, lost = [], []
    with (HERE / "dev_outputs.jsonl").open("w") as f:
        for i, r in enumerate(dev):
            a, b = row(rules[i], r), row(hybrid[i], r)
            top = emb[i]["top"][cfg["input"]]
            f.write(json.dumps({"q": r["q"], "bucket": r["bucket"], "expect": r["expect"],
                                "rules": a, "hybrid": b, "top3": top}) + "\n")
            if b["exact"] and not a["exact"]:
                gained.append({"q": r["q"], "metric": b["metric"], "top_cosine": round(top[0]["score"], 2) if top else None})
            if a["exact"] and not b["exact"]:
                lost.append({"q": r["q"], "rules_metric": a["metric"], "hybrid_metric": b["metric"]})
    summary = {"settings": cfg, "n": len(dev),
               "rules_exact": sum(row(rules[i], r)["exact"] for i, r in enumerate(dev)),
               "hybrid_exact": sum(row(hybrid[i], r)["exact"] for i, r in enumerate(dev)),
               "hybrid_right_rules_wrong": gained, "rules_right_hybrid_wrong": lost}
    (HERE / "dev_diff.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False))
    print(json.dumps({k: (len(v) if isinstance(v, list) else v) for k, v in summary.items()}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
