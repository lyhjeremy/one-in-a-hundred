"""Marathon finish times: Allen, Dechow, Pope and Wu (2017), Management Science,
"Reference-Dependent Preferences: Evidence from Marathon Runners".

The authors publish their full sample (9,789,093 finisher records, 1970 to
2013, US, Canada, Europe and elsewhere) at
https://faculty.chicagobooth.edu/george.wu/research/marathon/ as a 1.15 GB CSV
with age, gender, chiptime (minutes), marathon, year, country and the
finisher count per marathon-year. The records are the races' own official
results, republished for research, so the source is treated as
official-equivalent for grading and the fact says where it came from.

Facts: marathon_time for the latest year with a large sample (REF_YEAR), for
the whole sample ("world": every marathon in the data that year, which skews
to North America and Europe; the caveat says so) and for the US, Canada and
the countries in the launch list that have enough finishers, by sex and
five-year age band.

File (git-ignored): raw/src-booth-marathon/*.csv (whatever the download is
named). Read in chunks; only the needed columns are kept.
"""
from __future__ import annotations

import glob

import pandas as pd

from .common import RAW, Row, GRID, LAUNCH_COUNTRIES, weighted_quantiles, write_meta

SOURCE_ID = "src-booth-marathon"
URL = "https://faculty.chicagobooth.edu/george.wu/research/marathon/"
SOURCE = {
    "id": SOURCE_ID,
    "name": "Allen, Dechow, Pope and Wu (2017), marathon finisher records",
    "url": URL,
    "measures": "chip finish times of individual marathon finishers compiled from official race results, 1970 to 2013; by age, sex, race and country",
    "independent_of": [],
}
REF_YEAR = 2013
MIN_N = 300
AGE_BANDS = [(18, 24, "18-24"), (25, 29, "25-29"), (30, 34, "30-34"), (35, 39, "35-39"), (40, 44, "40-44"),
             (45, 49, "45-49"), (50, 54, "50-54"), (55, 59, "55-59"), (60, 64, "60-64"), (65, 69, "65-69"),
             (70, 120, "70+")]
COUNTRY_NAMES = {
    "US": ["united states", "usa", "us"], "CA": ["canada"], "GB": ["united kingdom", "uk", "england", "great britain"],
    "DE": ["germany"], "FR": ["france"], "NL": ["netherlands"], "CH": ["switzerland"], "JP": ["japan"],
    "AU": ["australia"], "KR": ["south korea", "korea"], "BR": ["brazil"], "MX": ["mexico"], "KE": ["kenya"],
    "ET": ["ethiopia"], "CN": ["china"], "IN": ["india"], "SG": ["singapore"], "HK": ["hong kong"], "ID": ["indonesia"], "NG": ["nigeria"],
}


def _iso2(name: str) -> str | None:
    n = str(name).strip().lower()
    for cc, names in COUNTRY_NAMES.items():
        if n in names:
            return cc
    return None


def _frame() -> pd.DataFrame | None:
    files = [f for f in glob.glob(str(RAW / SOURCE_ID / "*.csv"))]
    if not files:
        return None
    want = ["age", "gender", "chiptime", "year", "country", "marathon"]
    parts = []
    for f in files:
        # The file is Windows-1252, not UTF-8 (race names carry accented characters).
        for chunk in pd.read_csv(f, usecols=lambda c: c.lower() in want, chunksize=500_000, low_memory=False, encoding="cp1252"):
            chunk.columns = [c.lower() for c in chunk.columns]
            chunk = chunk[chunk.year == REF_YEAR]
            if len(chunk):
                parts.append(chunk)
    if not parts:
        return None
    df = pd.concat(parts)
    df["sec"] = pd.to_numeric(df.chiptime, errors="coerce") * 60
    df["age"] = pd.to_numeric(df.age, errors="coerce")
    df["sex"] = df.gender.astype(str).str.upper().str[0].map({"M": "m", "F": "f"})
    df["cc"] = df.country.map(_iso2)
    df = df.dropna(subset=["sec", "sex"])
    df = df[(df.sec > 2 * 3600) & (df.sec < 9 * 3600)]
    return df


def _emit(rows, sub, base, country, sex, band, n_races):
    sub = sub[sub.sec.notna()]
    if len(sub) < MIN_N:
        return
    probs = [s for _, s in GRID]
    qs = weighted_quantiles(sub.sec.tolist(), [1.0] * len(sub), probs)
    for (pk, _), v in zip(GRID, qs):
        rows.append(Row("marathon_time", base, country, sex, band, "marathon_finishers", None, REF_YEAR, pk,
                        float(round(v)), "seconds", SOURCE_ID, n=len(sub),
                        note=f"{len(sub):,} finishers across {n_races} marathons in the sample; the sample skews to North America and Europe"))


def load(population_fn=None) -> list[Row]:
    df = _frame()
    if df is None:
        print("booth: no CSV present under raw/src-booth-marathon, skipping")
        return []
    write_meta(SOURCE_ID, [URL], {"ref_year": REF_YEAR, "rows_ref_year": int(len(df))})
    rows: list[Row] = []
    scopes = [("world", None, df)]
    for cc in LAUNCH_COUNTRIES:
        sub = df[df.cc == cc]
        if len(sub) >= MIN_N:
            scopes.append(("country", cc, sub))
    for base, cc, d in scopes:
        n_races = d.marathon.nunique() if "marathon" in d else 0
        for sex in ("all", "m", "f"):
            s = d if sex == "all" else d[d.sex == sex]
            _emit(rows, s, base, cc, sex, None, n_races)
            if base == "world" or cc in ("US", "CA"):
                for lo, hi, band in AGE_BANDS:
                    sb = s[(s.age >= lo) & (s.age <= hi)]
                    _emit(rows, sb, base, cc, sex, band, n_races)
    return rows


if __name__ == "__main__":
    rs = load()
    print(len(rs), "rows")
    for r in rs:
        if r.base == "world" and r.age_band is None and r.percentile in ("p1", "p10", "p50"):
            print(r.sex, r.percentile, f"{r.value / 60:.1f} min", "n", r.n)
