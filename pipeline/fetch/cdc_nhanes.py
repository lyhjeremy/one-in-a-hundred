"""US CDC NHANES August 2021 to August 2023 cycle: measured height, weight, BMI.

Gives weighted percentile grids for US adults (20+) by sex, by sex and age
band, and by sex and the survey's own race and Hispanic-origin categories
(RIDRETH3). The categories are the survey's, reproduced verbatim, per the
sensitive-dimension rule in SPEC.md section 0.

Files (git-ignored): raw/src-cdc-nhanes/BMX_L.xpt, DEMO_L.xpt
Licence: public domain (US government).
Weights: WTMEC2YR (examination weights). Pregnant respondents are excluded
from weight and BMI but kept for height.
"""
from __future__ import annotations

import pandas as pd

from .common import RAW, Row, GRID, weighted_quantiles, write_meta, WPP_ID

SOURCE_ID = "src-cdc-nhanes"
YEAR = 2022  # midpoint of the 2021-2023 cycle
URLS = [
    "https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2021/DataFiles/BMX_L.xpt",
    "https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2021/DataFiles/DEMO_L.xpt",
]
SOURCE = {
    "id": SOURCE_ID,
    "name": "CDC NHANES 2021-2023, body measures",
    "url": "https://wwwn.cdc.gov/nchs/nhanes/continuousnhanes/default.aspx?Cycle=2021-2023",
    "measures": "measured height, weight and BMI of a nationally representative US sample, examination-weighted",
    "independent_of": [],
}

RETH3 = {
    1: "Mexican American", 2: "Other Hispanic", 3: "Non-Hispanic White",
    4: "Non-Hispanic Black", 6: "Non-Hispanic Asian", 7: "Other Race - Including Multi-Racial",
}
AGE_BANDS = [(20, 29, "20-29"), (30, 39, "30-39"), (40, 49, "40-49"), (50, 59, "50-59"),
             (60, 69, "60-69"), (70, 200, "70+")]
MIN_N = 150  # unweighted respondents needed before a slice is published

METRICS = [("height_adult_cm", "BMXHT", "cm", False),
           ("weight_adult_kg", "BMXWT", "kg", True),
           ("bmi_adult", "BMXBMI", "kg_m2", True)]


def _frame() -> pd.DataFrame:
    b = pd.read_sas(RAW / SOURCE_ID / "BMX_L.xpt")
    d = pd.read_sas(RAW / SOURCE_ID / "DEMO_L.xpt")
    m = b.merge(d, on="SEQN")
    m = m[(m.RIDAGEYR >= 20) & (m.WTMEC2YR > 0)]
    m["sex"] = m.RIAGENDR.map({1: "m", 2: "f"})
    m["pregnant"] = m.RIDEXPRG.eq(1)
    return m


def _emit(rows, sub, metric, col, unit, sex, band, cat, n_people):
    sub = sub[sub[col].notna()]
    if len(sub) < MIN_N:
        return
    probs = [s for _, s in GRID]
    qs = weighted_quantiles(sub[col].tolist(), sub.WTMEC2YR.tolist(), probs)
    for (pk, _), v in zip(GRID, qs):
        rows.append(Row(metric, "country", "US", sex, band, None, cat, YEAR, pk, round(float(v), 1),
                        unit, SOURCE_ID, n=n_people, note=f"unweighted n={len(sub)}", n_source=WPP_ID if n_people else None))


def load(population_fn=None) -> list[Row]:
    """population_fn(country, sex, min_age) -> people, from un_wpp, for n."""
    write_meta(SOURCE_ID, URLS)
    df = _frame()
    rows: list[Row] = []
    for metric, col, unit, excl_preg in METRICS:
        base = df[~df.pregnant] if excl_preg else df
        for sex in ("m", "f", "all"):
            s = base if sex == "all" else base[base.sex == sex]
            n_people = population_fn("US", sex, 20) if population_fn else None
            _emit(rows, s, metric, col, unit, sex, None, None, n_people)
            for lo, hi, band in AGE_BANDS:
                sb = s[(s.RIDAGEYR >= lo) & (s.RIDAGEYR <= hi)]
                # n for an age band comes from the weighted share of the sample.
                share = sb.WTMEC2YR.sum() / s.WTMEC2YR.sum() if len(s) else 0
                _emit(rows, sb, metric, col, unit, sex, band, None,
                      n_people * share if n_people else None)
            if sex != "all":
                for code, label in RETH3.items():
                    sc = s[s.RIDRETH3 == code]
                    share = sc.WTMEC2YR.sum() / s.WTMEC2YR.sum() if len(s) else 0
                    _emit(rows, sc, metric, col, unit, sex, None, label,
                          n_people * share if n_people else None)
    return rows


if __name__ == "__main__":
    rs = load()
    print(len(rs), "rows")
    for r in rs:
        if r.metric == "height_adult_cm" and r.age_band is None and r.source_category is None:
            print(r.sex, r.percentile, r.value)
