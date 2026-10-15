"""Render cards/<id>.png and f/<id>/index.html for every fact.

The PNG is 1200 x 630, Ledger palette parsed from assets/ledger.css at run
time, fonts from pipeline/fonts-ttf/ (converted once from assets/fonts/*.woff2
with fonttools). The HTML page is a static Ledger page with OpenGraph tags
pointing at the PNG, the punchline, the grade and the sources, plus a link to
the live screen. D-grade facts print UNREVIEWED in the top rule.

Incremental by content hash: unchanged facts are skipped.

Usage: python3 pipeline/render_cards.py [--all]
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.format import punchline, format_count, group_name, format_value, grid_key_for, METRICS as M_FULL  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FACTS_DIR = ROOT / "data" / "facts"
CARDS = ROOT / "cards"
FPAGES = ROOT / "f"
FONTS_TTF = ROOT / "pipeline" / "fonts-ttf"
SITE = "https://lyhjeremy.github.io/one-in-a-hundred/"
from pipeline.catalog import METRICS  # noqa: E402


def palette() -> dict:
    css = (ROOT / "assets" / "ledger.css").read_text()
    root = css.split(":root{", 1)[1].split("}", 1)[0]
    return dict(re.findall(r"--([a-z0-9-]+):(#[0-9A-Fa-f]{6})", root))


def ensure_ttf() -> None:
    FONTS_TTF.mkdir(exist_ok=True)
    from fontTools.ttLib import TTFont
    for w in (ROOT / "assets" / "fonts").glob("*.woff2"):
        out = FONTS_TTF / (w.stem + ".ttf")
        if not out.exists():
            f = TTFont(str(w))
            f.flavor = None
            f.save(str(out))


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS_TTF / f"{name}.ttf"), size)


def wrap(draw, text, fnt, max_w):
    words, lines, line = text.split(), [], ""
    for w in words:
        t = f"{line} {w}".strip()
        if draw.textlength(t, font=fnt) > max_w and line:
            lines.append(line)
            line = w
        else:
            line = t
    if line:
        lines.append(line)
    return lines


def subline_for(fact: dict, pct_key: str) -> str:
    bits = []
    if fact.get("n"):
        top = {"p50": 0.5, "p90": 0.1, "p99": 0.01, "p99.9": 0.001}[pct_key]
        bits.append(f"{format_count(fact['n'] * top)} people" if pct_key != "p50" else f"{format_count(fact['n'])} people in the group")
    bits.append(f"reference year {fact['year']}")
    bits.append(f"grade {fact['grade']}")
    return " · ".join(bits)


def draw_card(fact: dict, pct_key: str, P: dict, out: Path) -> None:
    img = Image.new("RGB", (1200, 630), P["paper"])
    d = ImageDraw.Draw(img)
    d.rectangle([72, 72, 1128, 74], fill=P["ink"])
    d.rectangle([72, 556, 1128, 557], fill=P["ink"])
    d.text((72, 36), "ONE IN A HUNDRED", font=font("IBMPlexSans-600", 22), fill=P["ink-2"])
    if fact["status"] == "queued":
        f = font("IBMPlexMono-400", 22)
        s = "UNREVIEWED"
        d.text((1128 - d.textlength(s, font=f), 36), s, font=f, fill=P["signal"])
    head = punchline(fact, pct_key)
    size = 60
    while True:
        f = font("SourceSerif4-600", size)
        lines = wrap(d, head, f, 1056)
        if len(lines) <= 4 or size <= 32:
            break
        size -= 4
    y = 140
    for ln in lines:
        d.text((72, y), ln, font=f, fill=P["ink"])
        y += int(size * 1.15)
    sub = subline_for(fact, pct_key)
    fs = font("IBMPlexSans-400", 26)
    y = max(y + 10, 470)
    for ln in wrap(d, sub, fs, 1056)[:2]:
        d.text((72, y), ln, font=fs, fill=P["ink-2"])
        y += 34
    fm = font("IBMPlexMono-400", 22)
    label = f"GRADE {fact['grade']}"
    w = d.textlength(label, font=fm) + 24
    d.rectangle([1128 - w, 574, 1128, 610], outline=P["ink"], width=2)
    d.text((1128 - w + 12, 580), label, font=fm, fill=P["ink"])
    d.text((72, 582), "lyhjeremy.github.io/one-in-a-hundred", font=font("IBMPlexSans-400", 20), fill=P["ink-2"])
    out.parent.mkdir(parents=True, exist_ok=True)
    # Flat colour and text only: a 64-colour palette keeps the antialiasing
    # and cuts each card from about 50 KB to about 10 KB.
    img.convert("P", palette=Image.Palette.ADAPTIVE, colors=64).save(out, optimize=True)


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{desc}">
<meta property="og:title" content="{title}"><meta property="og:description" content="{desc}">
<meta property="og:type" content="article"><meta property="og:url" content="{url}">
<meta property="og:image" content="{img}"><meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="{title}"><meta name="twitter:description" content="{desc}"><meta name="twitter:image" content="{img}">
<link rel="stylesheet" href="../../assets/ledger.css"><link rel="stylesheet" href="../../assets/app.css"></head>
<body><main class="wrap">
<p class="kicker"><a href="../../">One in a Hundred</a></p>
{unrev}
<h1 class="punchline">{head}</h1>
<p class="subline"><span class="grade{dcls}">Grade {grade}</span>{sub}</p>
<p>{reason}</p>
<h2>Definition</h2><p>{definition}</p>{caveat}
<h2>Sources</h2>
<div class="table-scroll"><table class="sources-table"><thead><tr><th>Source</th><th>Measures</th><th class="num">Value here</th><th>Accessed</th></tr></thead><tbody>{rows}</tbody></table></div>
{rng}
<p><a class="btn" href="../../?f={fid}&q={q}">Open the live screen with this group</a> <a class="btn" href="../../cards/{fid}.png" download>Download card</a></p>
<p class="small">Numbers can be wrong; the grade says how likely. <a href="../../overview/">How this works</a> · <a href="../../privacy/">Privacy</a></p>
</main></body></html>
"""


def page_for(fact: dict, pct_key: str) -> str:
    head = punchline(fact, pct_key)
    gk = grid_key_for(fact["direction"], pct_key)
    rows = []
    for s in fact["sources"]:
        v = s.get("values", {}).get(gk)
        rows.append(f"<tr><td><a href=\"{html.escape(s['url'])}\">{html.escape(s['name'])}</a></td><td>{html.escape(s.get('measures', ''))}</td>"
                    f"<td class=\"num\">{html.escape(format_value(fact['metric'], v)) if v is not None else '-'}</td><td>{html.escape(s.get('accessed', ''))}</td></tr>")
    rng = fact.get("range", {}).get(gk)
    rng_html = ""
    if rng and len(rng) == 2 and rng[0] != rng[1]:
        rng_html = f"<p>Range across sources at this percentile: {html.escape(format_value(fact['metric'], rng[0]))} to {html.escape(format_value(fact['metric'], rng[1]))}.</p>"
    elif len(fact["sources"]) == 1:
        rng_html = "<p>One source, no spread to show.</p>"
    unrev = "<p class=\"unrev\">Unreviewed: researched automatically, not yet checked by a person.</p>" if fact["status"] == "queued" else ""
    caveat = f"<p>{html.escape(fact['caveat'])}</p>" if fact.get("caveat") else ""
    return PAGE.format(
        title=html.escape(head), desc=html.escape(subline_for(fact, pct_key)), url=f"{SITE}f/{fact['id']}/",
        img=f"{SITE}cards/{fact['id']}.png", unrev=unrev, head=html.escape(head), grade=fact["grade"],
        dcls=" d" if fact["grade"] == "D" else "", sub=html.escape(subline_for(fact, pct_key)),
        reason=html.escape(fact.get("reason", "")), definition=html.escape(fact.get("definition", "")),
        caveat=caveat, rows="".join(rows), rng=rng_html, fid=fact["id"], q=pct_key[1:])


def default_pct(fact: dict) -> str:
    # The card shows the top 1% where the grid has it, else top 10%, else median.
    for pk in ("p99", "p90", "p50"):
        if grid_key_for(fact["direction"], pk) in fact["grid"]:
            return pk
    return "p50"


def main(force: bool = False) -> None:
    ensure_ttf()
    P = palette()
    stamp_file = ROOT / "pipeline" / ".cards_hash.json"
    seen = json.loads(stamp_file.read_text()) if stamp_file.exists() and not force else {}
    done = 0
    live_ids = set()
    for p in sorted(FACTS_DIR.glob("*.json")):
        for fact in json.loads(p.read_text()):
            live_ids.add(fact["id"])
            key = json.dumps({k: fact[k] for k in ("grid", "grade", "status", "sources", "n", "year")}, sort_keys=True, default=str)
            h = hashlib.sha1(key.encode()).hexdigest()
            if seen.get(fact["id"]) == h and (CARDS / f"{fact['id']}.png").exists():
                continue
            pk = default_pct(fact)
            draw_card(fact, pk, P, CARDS / f"{fact['id']}.png")
            d = FPAGES / fact["id"]
            d.mkdir(parents=True, exist_ok=True)
            (d / "index.html").write_text(page_for(fact, pk))
            seen[fact["id"]] = h
            done += 1
    # Remove cards for facts that no longer exist.
    for png in CARDS.glob("*.png"):
        if png.stem not in live_ids:
            png.unlink()
            seen.pop(png.stem, None)
    stamp_file.write_text(json.dumps(seen, indent=0))
    print(f"rendered {done} cards; {len(live_ids)} facts total")


if __name__ == "__main__":
    main(force="--all" in sys.argv)
