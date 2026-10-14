"""NCD-RisC adult BMI (Nature 2026): prevalence in BMI bands by country, sex, age.

The release gives the share of people in each band (<18.5, 18.5-20, 20-25,
25-30, 30-35, 35-40, >=40). That is a cumulative distribution with cut points
at 18.5, 20, 25, 30, 35 and 40, so a percentile is located by linear
interpolation inside its band. A percentile that falls in the open top band
(>=40) cannot be located and is not emitted. All rows are derived=True.

Files (git-ignored): raw/src-ncdrisc-bmi/xm/*.csv (men), xf/*.csv (women)
Licence: CC BY 4.0.
"""
from __future__ import annotations

import zipfile

import pandas as pd

from .common import RAW, Row, GRID, LAUNCH_COUNTRIES, ISO3_TO_2, write_meta

SOURCE_ID = "src-ncdrisc-bmi"
URLS = [
    "https://www.ncdrisc.org/downloads/bmi-2026/adult/NCD_RisC_Nature_2026_BMI_male_age_specific_country.zip",
    "https://www.ncdrisc.org/downloads/bmi-2026/adult/NCD_RisC_Nature_2026_BMI_female_age_specific_country.zip",
]
SOURCE = {
    "id": SOURCE_ID,
    "name": "NCD Risk Factor Collaboration, adult BMI (Nature 2026)",
    "url": "https://www.ncdrisc.org/data-downloads-adiposity.html",
    "measures": "share of adults in BMI bands by country, sex and five-year age group, pooled from population surveys; percentiles interpolated within bands",
    "independent_of": [],
}

BANDS = [  # (column, lower, upper)
    ("Prevalence of BMI<18.5 kg/m² (underweight)", 12.0, 18.5),
    ("Prevalence of BMI 18.5 kg/m² to <20 kg/m²", 18.5, 20.0),
    ("Prevalence of BMI 20 kg/m² to <25 kg/m²", 20.0, 25.0),
    ("Prevalence of BMI 25 kg/m² to <30 kg/m²", 25.0, 30.0),
    ("Prevalence of BMI 30 kg/m² to <35 kg/m²", 30.0, 35.0),
    ("Prevalence of BMI 35 kg/m² to <40 kg/m²", 35.0, 40.0),
]
TOP = "Prevalence of BMI >=40 kg/m² (morbid obesity)"
AGE_GROUPS = ["20-24", "25-29", "30-34", "35-39", "40-44", "45-49", "50-54", "55-59",
              "60-64", "65-69", "70-74", "75-79", "80-84", "85plus"]


def _frames() -> pd.DataFrame:
    out = []
    for sex, z, d in (("m", "male_age_specific_country.zip", "xm"), ("f", "female_age_specific_country.zip", "xf")):
        dest = RAW / SOURCE_ID / d
        if not dest.exists():
            zipfile.ZipFile(RAW / SOURCE_ID / z).extractall(dest)
        f = next(dest.glob("*.csv"))
        df = pd.read_csv(f)
        df["sex"] = sex
        out.append(df)
    return pd.concat(out)


def _quantiles(row) -> dict[str, float]:
    cum = 0.0
    edges = []
    for col, lo, hi in BANDS:
        share = float(row[col])
        edges.append((cum, cum + share, lo, hi))
        cum += share
    out = {}
    for pk, p in GRID:
        for i, (c0, c1, lo, hi) in enumerate(edges):
            if c0 <= p <= c1 and c1 > c0:
                if i == 0:
                    # The bottom band (<18.5) has no published lower edge; a
                    # percentile inside it cannot be located. Skip it.
                    break
                out[pk] = round(lo + (hi - lo) * (p - c0) / (c1 - c0), 1)
                break
    return out


def load(population_fn=None) -> list[Row]:
    write_meta(SOURCE_ID, URLS)
    df = _frames()
    year = int(df.Year.max())
    df = df[df.Year == year]
    rows: list[Row] = []
    for iso3, iso2 in ISO3_TO_2.items():
        sub = df[df.ISO == iso3]
        if sub.empty:
            continue
        for sex in ("m", "f"):
            ss = sub[sub.sex == sex]
            for _, r in ss.iterrows():
                band = r["Age group"]
                if band not in AGE_GROUPS:
                    continue
                band_out = "85+" if band == "85plus" else band
                q = _quantiles(r)
                for pk, v in q.items():
                    rows.append(Row("bmi_adult", "country", iso2, sex, band_out, None, None, year, pk, v,
                                    "kg_m2", SOURCE_ID, derived=True,
                                    note="interpolated within published BMI bands"))
    return rows


if __name__ == "__main__":
    rs = load()
    print(len(rs), "rows")
    for r in rs:
        if r.country == "US" and r.age_band == "30-34":
            print(r.sex, r.percentile, r.value)
