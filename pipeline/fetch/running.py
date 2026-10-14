"""Running finish-time distributions.

Launch source: the Kaggle dataset "2023 Marathon Results" (runningwithrock),
about 429,000 finishers across 641 US marathons in 2023 with gender, age and
finish time in seconds. Kaggle requires an account token to download, so
this fetcher reads whatever CSV files are present under
raw/src-kaggle-us-marathons-2023/ and returns nothing when the folder is
empty. The site then simply has no running facts until the file arrives.

Download once the token exists:
  kaggle datasets download -d runningwithrock/2023-marathon-results \
      -p pipeline/raw/src-kaggle-us-marathons-2023 --unzip

Columns are detected by name (gender/sex, age, finish/time in seconds) so a
renamed file still loads. Licence: as stated on the Kaggle page; record it
in meta.json before publishing facts from it.
"""
from __future__ import annotations

import glob

import pandas as pd

from .common import RAW, Row, GRID, weighted_quantiles, write_meta

SOURCE_ID = "src-kaggle-us-marathons-2023"
YEAR = 2023
SOURCE = {
    "id": SOURCE_ID,
    "name": "2023 US marathon results (Kaggle, runningwithrock)",
    "url": "https://www.kaggle.com/datasets/runningwithrock/2023-marathon-results",
    "measures": "finish times of individual finishers across 641 US marathons in 2023, by gender and age",
    "independent_of": [],
}
AGE_BANDS = [(18, 24, "18-24"), (25, 29, "25-29"), (30, 34, "30-34"), (35, 39, "35-39"), (40, 44, "40-44"),
             (45, 49, "45-49"), (50, 54, "50-54"), (55, 59, "55-59"), (60, 64, "60-64"), (65, 69, "65-69"),
             (70, 120, "70+")]
MIN_N = 200


def _find(cols, *cands):
    low = {c.lower(): c for c in cols}
    for cand in cands:
        for lc, c in low.items():
            if cand in lc:
                return c
    return None


def _frame() -> pd.DataFrame | None:
    files = glob.glob(str(RAW / SOURCE_ID / "*.csv"))
    if not files:
        return None
    df = pd.concat(pd.read_csv(f, low_memory=False) for f in files)
    g = _find(df.columns, "gender", "sex")
    a = _find(df.columns, "age")
    t = _find(df.columns, "finish_sec", "finish (sec", "finish_time_sec", "seconds", "finish", "time")
    if not (g and a and t):
        raise SystemExit(f"running: could not detect columns in {list(df.columns)}")
    out = pd.DataFrame({"sex": df[g].astype(str).str.strip().str.upper().str[0].map({"M": "m", "F": "f", "W": "f"}),
                        "age": pd.to_numeric(df[a], errors="coerce"),
                        "sec": pd.to_numeric(df[t], errors="coerce")})
    out = out.dropna()
    out = out[(out.sec > 2 * 3600) & (out.sec < 9 * 3600) & (out.age >= 18) & (out.age < 100)]
    return out


def _emit(rows, sub, sex, band):
    if len(sub) < MIN_N:
        return
    probs = [s for _, s in GRID]
    qs = weighted_quantiles(sub.sec.tolist(), [1.0] * len(sub), probs)
    for (pk, _), v in zip(GRID, qs):
        rows.append(Row("marathon_time", "country", "US", sex, band, "marathon_finishers", None, YEAR, pk,
                        float(v), "seconds", SOURCE_ID, n=len(sub), note=f"n={len(sub)} finishers in sample"))


def load(population_fn=None) -> list[Row]:
    df = _frame()
    if df is None:
        print("running: no Kaggle file present, skipping")
        return []
    write_meta(SOURCE_ID, [SOURCE["url"]], {"rows": int(len(df))})
    rows: list[Row] = []
    for sex in ("all", "m", "f"):
        s = df if sex == "all" else df[df.sex == sex]
        _emit(rows, s, sex, None)
        for lo, hi, band in AGE_BANDS:
            _emit(rows, s[(s.age >= lo) & (s.age <= hi)], sex, band)
    return rows


if __name__ == "__main__":
    rs = load()
    print(len(rs), "rows")
    for r in rs:
        if r.age_band is None and r.percentile in ("p1", "p50"):
            print(r.sex, r.percentile, r.value)
