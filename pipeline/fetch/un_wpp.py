"""UN World Population Prospects 2024: age distribution and population counts.

Gives: `age_years` grids for the world and the launch countries, by sex, for
the reference year; `life_expectancy_at_birth` grid across all countries
(population "countries"); and the population counts other fetchers use for
`n` (adults 20+ by country and sex, total population).

Files (downloaded by fetch_all.py, git-ignored):
  raw/src-un-wpp-2024/WPP2024_PopulationBySingleAgeSex_Medium_2024-2100.csv.gz
  raw/src-un-wpp-2024/WPP2024_Demographic_Indicators_Medium.csv.gz
Licence: CC BY 3.0 IGO.
"""
from __future__ import annotations

import gzip
import csv
from functools import lru_cache

from .common import RAW, Row, GRID, LAUNCH_COUNTRIES, write_meta

SOURCE_ID = "src-un-wpp-2024"
YEAR = 2025
LE_YEAR = 2023  # matches WHO GHE's latest year so the two sources merge into one fact
URLS = [
    "https://population.un.org/wpp/assets/Excel%20Files/1_Indicator%20(Standard)/CSV_FILES/WPP2024_PopulationBySingleAgeSex_Medium_2024-2100.csv.gz",
    "https://population.un.org/wpp/assets/Excel%20Files/1_Indicator%20(Standard)/CSV_FILES/WPP2024_Demographic_Indicators_Medium.csv.gz",
]
SOURCE = {
    "id": SOURCE_ID,
    "name": "UN World Population Prospects 2024",
    "url": "https://population.un.org/wpp/",
    "measures": "population by single year of age and sex, medium variant, mid-2025",
    "independent_of": [],
}


@lru_cache(maxsize=1)
def _pyramids() -> dict:
    """{(iso2 or 'WO', sex): [(age, pop_thousands), ...]} for YEAR."""
    out: dict = {}
    with gzip.open(RAW / SOURCE_ID / "WPP2024_PopulationBySingleAgeSex_Medium_2024-2100.csv.gz", "rt", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if r["Time"] != str(YEAR):
                continue
            loc = r["Location"]
            iso2 = r["ISO2_code"]
            if loc == "World":
                key = "WO"
            elif iso2 in LAUNCH_COUNTRIES and r["LocTypeName"] == "Country/Area":
                key = iso2
            else:
                continue
            age = int(r["AgeGrpStart"])
            for sex, col in (("all", "PopTotal"), ("m", "PopMale"), ("f", "PopFemale")):
                out.setdefault((key, sex), []).append((age, float(col and r[col])))
    return out


def _age_quantiles(pyramid: list[tuple[int, float]]) -> dict:
    """Percentile ages from a single-year pyramid. Ages are completed years;
    the quantile is linear within the year."""
    pyramid = sorted(pyramid)
    total = sum(p for _, p in pyramid)
    out = {}
    for key, share in GRID:
        target = share * total
        cum = 0.0
        for age, pop in pyramid:
            if cum + pop >= target:
                frac = (target - cum) / pop if pop else 0
                out[key] = round(age + frac, 1)
                break
            cum += pop
    return out, total


def population(key: str, sex: str = "all", min_age: int = 0) -> float:
    """People (not thousands) in YEAR at or above min_age. key: 'WO' or ISO2."""
    pyr = _pyramids().get((key, sex), [])
    return sum(p for a, p in pyr if a >= min_age) * 1000


def _life_expectancy() -> list[tuple[str, float, float, float]]:
    rows = []
    with gzip.open(RAW / SOURCE_ID / "WPP2024_Demographic_Indicators_Medium.csv.gz", "rt", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if r["Time"] != str(LE_YEAR) or r["LocTypeName"] != "Country/Area":
                continue
            try:
                rows.append((r["ISO2_code"], float(r["LEx"]), float(r["LExMale"]), float(r["LExFemale"])))
            except ValueError:
                continue
    return rows


def load() -> list[Row]:
    write_meta(SOURCE_ID, URLS)
    rows: list[Row] = []
    for (key, sex), pyr in _pyramids().items():
        q, total = _age_quantiles(pyr)
        base = "world" if key == "WO" else "country"
        country = None if key == "WO" else key
        for pk, v in q.items():
            rows.append(Row("age_years", base, country, sex, None, None, None, YEAR, pk, v,
                            "years", SOURCE_ID, n=total * 1000))
    # Life expectancy: the population is "countries", one value per country.
    le = _life_expectancy()
    for sex, idx in (("all", 1), ("m", 2), ("f", 3)):
        vals = sorted(x[idx] for x in le)
        n = len(vals)
        for pk, share in GRID:
            i = min(n - 1, max(0, int(round(share * (n - 1)))))
            rows.append(Row("life_expectancy_at_birth", "world", None, sex, None, None, None,
                            LE_YEAR, pk, round(vals[i], 1), "years", SOURCE_ID, n=n,
                            note="distribution across countries, one value per country"))
    return rows


if __name__ == "__main__":
    rs = load()
    print(len(rs), "rows")
    for r in rs:
        if r.metric == "age_years" and r.base == "world" and r.sex == "all":
            print(r.percentile, r.value, "n", f"{r.n:,.0f}")
    print("adults 20+ world:", f"{population('WO', 'all', 20):,.0f}")
