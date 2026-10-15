"""NCD-RisC height (Lancet 2020): mean height at age 19 by country, sex, year.

NCD-RisC publishes means and uncertainty intervals, not percentiles. The grid
is derived under a normal assumption using the sex-specific standard
deviation of measured adult height from NHANES (computed in cdc_nhanes.py),
and every row is flagged derived=True, which caps the fact at grade B unless
an independent measured source confirms the point (pipeline.md section 3).

"Height at age 19 in 2019" is the most recent adult-height estimate the
collaboration publishes; it describes the 2000 birth cohort, and the fact's
definition says so.

Files (git-ignored): raw/src-ncdrisc-height/x/*.csv (country), global.csv
Licence: CC BY 4.0.
"""
from __future__ import annotations

import glob

import pandas as pd

from .common import RAW, Row, GRID, LAUNCH_COUNTRIES, normal_quantile, write_meta, WPP_ID

SOURCE_ID = "src-ncdrisc-height"
YEAR = 2019
URLS = [
    "https://www.ncdrisc.org/downloads/bmi-height-2020/height/all_countries/NCD_RisC_Lancet_2020_height_child_adolescent_country.zip",
    "https://www.ncdrisc.org/downloads/bmi-height-2020/height/global/NCD_RisC_Lancet_2020_height_child_adolescent_global.csv",
]
SOURCE = {
    "id": SOURCE_ID,
    "name": "NCD Risk Factor Collaboration, height at age 19 (Lancet 2020)",
    "url": "https://www.ncdrisc.org/data-downloads-height.html",
    "measures": "mean height at age 19 by country and sex, pooled from population surveys; percentiles derived under a normal assumption",
    "independent_of": [],
}

NAMES = {
    "US": "United States of America", "GB": "United Kingdom", "CA": "Canada", "AU": "Australia",
    "HK": "China (Hong Kong SAR)", "SG": "Singapore", "JP": "Japan", "KR": "South Korea",
    "DE": "Germany", "FR": "France", "NL": "Netherlands", "CH": "Switzerland", "CN": "China",
    "IN": "India", "ID": "Indonesia", "BR": "Brazil", "NG": "Nigeria", "MX": "Mexico",
    "KE": "Kenya", "ET": "Ethiopia",
}
SEX = {"Boys": "m", "Girls": "f"}


def _sd_by_sex() -> dict[str, float]:
    """Weighted SD of measured adult height from NHANES, by sex."""
    from .cdc_nhanes import _frame
    df = _frame()
    df = df[df.BMXHT.notna()]
    out = {}
    for s in ("m", "f"):
        sub = df[df.sex == s]
        w = sub.WTMEC2YR
        mean = (sub.BMXHT * w).sum() / w.sum()
        var = ((sub.BMXHT - mean) ** 2 * w).sum() / w.sum()
        out[s] = float(var ** 0.5)
    return out


def _rows_for(mean: float, sd: float, base, country, sex, n, year=YEAR) -> list[Row]:
    rows = []
    for pk, share in GRID:
        rows.append(Row("height_adult_cm", base, country, sex, None, None, None, year, pk,
                        round(normal_quantile(mean, sd, share), 1), "cm", SOURCE_ID, n=n, n_source=WPP_ID if n else None,
                        derived=True,
                        note=f"derived from mean {mean:.1f} cm and an assumed SD of {sd:.1f} cm (NHANES measured, same sex)"))
    return rows


def load(population_fn=None) -> list[Row]:
    write_meta(SOURCE_ID, URLS)
    sd = _sd_by_sex()
    rows: list[Row] = []
    country = pd.concat(pd.read_csv(f) for f in glob.glob(str(RAW / SOURCE_ID / "x" / "*.csv")))
    country = country[(country["Age group"] == 19) & (country.Year % 5 == 4)]  # 1989, 1994, ... 2019
    for iso2 in LAUNCH_COUNTRIES:
        sub = country[country.Country == NAMES[iso2]]
        for _, r in sub.iterrows():
            s = SEX[r.Sex]
            latest = int(r.Year) == YEAR
            n = population_fn(iso2, s, 20) if (population_fn and latest) else None
            rows += _rows_for(float(r["Mean height"]), sd[s], "country", iso2, s, n, int(r.Year))
    g = pd.read_csv(RAW / SOURCE_ID / "global.csv")
    g = g[(g["Age group"] == 19) & (g.Year % 5 == 4)]
    for _, r in g.iterrows():
        s = SEX[r.Sex]
        latest = int(r.Year) == YEAR
        n = population_fn("WO", s, 20) if (population_fn and latest) else None
        rows += _rows_for(float(r["Mean height"]), sd[s], "world", None, s, n, int(r.Year))
    return rows


if __name__ == "__main__":
    rs = load()
    print(len(rs), "rows; SD used:", _sd_by_sex())
    for r in rs:
        if r.base == "world" and r.percentile in ("p50", "p99"):
            print(r.sex, r.percentile, r.value)
