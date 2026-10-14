"""World Bank Poverty and Inequality Platform: consumption/income per capita.

For countries, the `pip` endpoint's `popshare` parameter returns the welfare
level (per person per day, 2021 PPP) at a cumulative population share, which
is exactly a percentile threshold. For the world aggregate the `pip-grp`
endpoint only accepts a poverty line, so the threshold is found by bisection
on the line until the headcount matches the share.

Values are per day; the metric is stored per year (x 365.25). PIP's welfare
aggregate is income for some countries and consumption for others; the fact
caveat names which. Hong Kong and Singapore have no PIP survey and are skipped.

Results are cached in raw/src-wb-pip/cache.json so a rebuild costs no calls.
Licence: CC BY 4.0.
"""
from __future__ import annotations

import json
import time
import urllib.request
import urllib.parse

from .common import RAW, Row, GRID, LAUNCH_COUNTRIES, write_meta, WPP_ID

SOURCE_ID = "src-wb-pip"
YEAR = 2022
PPP = "2021"
BASE = "https://api.worldbank.org/pip/v1/"
SOURCE = {
    "id": SOURCE_ID,
    "name": "World Bank Poverty and Inequality Platform",
    "url": "https://pip.worldbank.org/",
    "measures": "household income or consumption per capita from household surveys, 2021 PPP dollars per day",
    "independent_of": [],
}
ISO3 = {"US": "USA", "GB": "GBR", "CA": "CAN", "AU": "AUS", "JP": "JPN", "KR": "KOR", "DE": "DEU",
        "FR": "FRA", "NL": "NLD", "CH": "CHE", "CN": "CHN", "IN": "IND", "ID": "IDN", "BR": "BRA",
        "NG": "NGA", "MX": "MEX", "KE": "KEN", "ET": "ETH"}
CACHE = RAW / SOURCE_ID / "cache.json"


def _get(path: str, **params) -> list[dict]:
    params.setdefault("format", "json")
    url = BASE + path + "?" + urllib.parse.urlencode(params)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=90) as r:
                return json.loads(r.read().decode())
        except Exception as e:  # noqa: BLE001
            if attempt == 3:
                raise
            time.sleep(2 * (attempt + 1))
    return []


def _load_cache() -> dict:
    return json.loads(CACHE.read_text()) if CACHE.exists() else {}


def _country(iso3: str, cache: dict) -> dict | None:
    key = f"{iso3}:{YEAR}:{PPP}"
    if key in cache:
        return cache[key]
    out = {"grid": {}, "welfare_type": None, "pop": None}
    for pk, share in GRID:
        rs = _get("pip", country=iso3, year=YEAR, popshare=share, fill_gaps="true", ppp_version=PPP)
        if not rs:
            cache[key] = None
            return None
        r = rs[0]
        out["grid"][pk] = r["poverty_line"]
        out["welfare_type"] = r["welfare_type"]
        out["pop"] = r.get("reporting_pop")
    cache[key] = out
    return out


def _world(cache: dict) -> dict | None:
    key = f"WLD:{YEAR}:{PPP}"
    if key in cache:
        return cache[key]
    out = {"grid": {}, "welfare_type": "mixed", "pop": None}

    def headcount(line: float) -> tuple[float, float]:
        rs = _get("pip-grp", country="WLD", year=YEAR, povline=round(line, 4), group_by="wb", ppp_version=PPP)
        r = rs[0]
        return r["headcount"], r.get("reporting_pop")

    for pk, share in GRID:
        lo, hi = 0.1, 2000.0
        for _ in range(22):  # 2000 / 2^22 < 0.001 $/day
            mid = (lo + hi) / 2
            h, pop = headcount(mid)
            out["pop"] = pop
            if h < share:
                lo = mid
            else:
                hi = mid
            if hi - lo < 0.005:
                break
        out["grid"][pk] = round((lo + hi) / 2, 3)
    cache[key] = out
    return out


def load(population_fn=None) -> list[Row]:
    write_meta(SOURCE_ID, [BASE + "pip", BASE + "pip-grp"], {"year": YEAR, "ppp_version": PPP})
    cache = _load_cache()
    rows: list[Row] = []
    try:
        w = _world(cache)
        if w:
            n = population_fn("WO", "all", 0) if population_fn else w["pop"]
            for pk, v in w["grid"].items():
                rows.append(Row("consumption_percap_ppp", "world", None, "all", None, None, None, YEAR, pk,
                                round(v * 365.25, 2), "usd_year", SOURCE_ID, n=n, n_source=WPP_ID if population_fn else None,
                                note="world aggregate mixes income-based and consumption-based surveys; lined up by the World Bank"))
        for cc in LAUNCH_COUNTRIES:
            if cc not in ISO3:
                continue
            c = _country(ISO3[cc], cache)
            if not c:
                print(f"pip: no data for {cc}")
                continue
            n = population_fn(cc, "all", 0) if population_fn else c["pop"]
            for pk, v in c["grid"].items():
                rows.append(Row("consumption_percap_ppp", "country", cc, "all", None, None, None, YEAR, pk,
                                round(v * 365.25, 2), "usd_year", SOURCE_ID, n=n, n_source=WPP_ID if population_fn else None,
                                note=f"survey welfare measure is {c['welfare_type']}, per person"))
    finally:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(cache, indent=1) + "\n")
    return rows


if __name__ == "__main__":
    rs = load()
    print(len(rs), "rows")
    for r in rs:
        if r.base == "world" or r.country in ("US", "IN"):
            print(r.country or "WO", r.percentile, f"{r.value:,.0f}")
