"""World Inequality Database bulk download: income and wealth thresholds.

Variables (all adults 20+, equal-split within couples, code suffix j992):
  tptincj992  pre-tax national income threshold   -> income_pretax_adult_ppp
  tdiincj992  post-tax disposable income threshold -> income_posttax_adult_ppp
  thwealj992  net personal wealth threshold        -> net_worth_adult_usd
Country values are in constant local currency; xlcuspi999 is the PPP
conversion factor (local currency per USD) for the same year. The world
aggregate (country code WO) is already in USD.

Percentile codes: p50p51 is the threshold entering the 50th percentile, i.e.
the median; p90p91 the top-10% cutoff; p99p100 the top-1% cutoff; p99.9p100
the top-0.1% cutoff.

Files (git-ignored): raw/src-wid/x/WID_data_<CC>.csv, extracted from
wid_all_data.zip by fetch_all.py. Licence: CC BY 4.0.
"""
from __future__ import annotations

import csv

from .common import RAW, Row, LAUNCH_COUNTRIES, write_meta, WPP_ID

SOURCE_ID = "src-wid"
YEAR = 2023
URLS = ["https://wid.world/bulk_download/wid_all_data.zip"]
SOURCE = {
    "id": SOURCE_ID,
    "name": "World Inequality Database (WID.world)",
    "url": "https://wid.world/data/",
    "measures": "income and wealth thresholds per adult from distributional national accounts; local currency converted at WID's PPP factor",
    "independent_of": [],
}

VARS = {
    "tptincj992": ("income_pretax_adult_ppp", "usd_year"),
    "tdiincj992": ("income_posttax_adult_ppp", "usd_year"),
    "thwealj992": ("net_worth_adult_usd", "usd"),
}
PCTS = {"p50p51": "p50", "p90p91": "p90", "p99p100": "p99", "p99.9p100": "p99.9",
        "p10p11": "p10", "p25p26": "p25", "p75p76": "p75", "p1p2": "p1", "p0.1p0.2": "p0.1"}


def _read(cc: str) -> tuple[dict, float | None]:
    """Return ({(var, pct_key): value}, ppp_factor) for YEAR."""
    vals: dict = {}
    ppp = None
    with open(RAW / SOURCE_ID / "x" / f"WID_data_{cc}.csv", encoding="utf-8", errors="ignore") as f:
        for r in csv.DictReader(f, delimiter=";"):
            if r["year"] != str(YEAR):
                continue
            v = r["variable"]
            if v in VARS and r["percentile"] in PCTS:
                vals[(v, PCTS[r["percentile"]])] = float(r["value"])
            elif v == "xlcuspi999" and r["percentile"] == "p0p100":
                ppp = float(r["value"])
    return vals, ppp


def load(population_fn=None) -> list[Row]:
    write_meta(SOURCE_ID, URLS, {"year": YEAR})
    rows: list[Row] = []
    for cc in ["WO"] + LAUNCH_COUNTRIES:
        vals, ppp = _read(cc)
        if cc == "WO":
            ppp = 1.0
        if not vals or not ppp:
            print(f"wid: skipping {cc}, no data or PPP for {YEAR}")
            continue
        base = "world" if cc == "WO" else "country"
        country = None if cc == "WO" else cc
        n = population_fn("WO" if cc == "WO" else cc, "all", 20) if population_fn else None
        for (var, pk), v in vals.items():
            metric, unit = VARS[var]
            usd = v / ppp
            if usd < 0 and metric.startswith("net_worth"):
                # Bottom wealth percentiles are negative (debt); keep them, the UI shows them as is.
                pass
            rows.append(Row(metric, base, country, "all", None, None, None, YEAR, pk, round(usd, 2),
                            unit, SOURCE_ID, n=n, n_source=WPP_ID if population_fn else None,
                            note=None if cc == "WO" else f"converted from local currency at WID PPP factor {ppp:.4g}"))
    return rows


if __name__ == "__main__":
    rs = load()
    print(len(rs), "rows")
    for r in rs:
        if r.base == "world" or r.country in ("US", "KE"):
            if r.percentile in ("p50", "p99"):
                print(r.country or "WO", r.metric, r.percentile, f"{r.value:,.0f}")
