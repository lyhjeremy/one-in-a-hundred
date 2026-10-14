"""WHO Global Health Observatory: life expectancy at birth by country and sex.

Indicator WHOSIS_000001 via the GHO OData API. An independent second source
for `life_expectancy_at_birth` next to UN WPP: both are official, and WHO's
Global Health Estimates are produced separately from the UN Population
Division's projections, so this is the first place an A grade can appear.

Cached in raw/src-who-ghe/who_le.json. Licence: CC BY-NC-SA 3.0 IGO.
"""
from __future__ import annotations

import json
import urllib.request

from .common import RAW, Row, GRID, write_meta

SOURCE_ID = "src-who-ghe"
URL = "https://ghoapi.azureedge.net/api/WHOSIS_000001"
SOURCE = {
    "id": SOURCE_ID,
    "name": "WHO Global Health Observatory, life expectancy at birth",
    "url": "https://www.who.int/data/gho/data/indicators/indicator-details/GHO/life-expectancy-at-birth-(years)",
    "measures": "period life expectancy at birth by country and sex, WHO Global Health Estimates",
    "independent_of": ["src-un-wpp-2024"],
}
SEX = {"SEX_BTSX": "all", "SEX_MLE": "m", "SEX_FMLE": "f"}
CACHE = RAW / SOURCE_ID / "who_le.json"


def _data() -> list[dict]:
    if CACHE.exists():
        return json.loads(CACHE.read_text())
    out = []
    url = URL + "?$filter=SpatialDimType%20eq%20%27COUNTRY%27"
    while url:
        with urllib.request.urlopen(url, timeout=120) as r:
            j = json.loads(r.read().decode())
        out += j.get("value", [])
        url = j.get("@odata.nextLink")
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(out))
    return out


def load(population_fn=None) -> list[Row]:
    write_meta(SOURCE_ID, [URL])
    data = _data()
    year = max(d["TimeDim"] for d in data)
    rows: list[Row] = []
    for code, sex in SEX.items():
        vals = sorted(float(d["NumericValue"]) for d in data if d["TimeDim"] == year and d["Dim1"] == code and d.get("NumericValue") is not None)
        n = len(vals)
        if n < 100:
            continue
        for pk, share in GRID:
            i = min(n - 1, max(0, int(round(share * (n - 1)))))
            rows.append(Row("life_expectancy_at_birth", "world", None, sex, None, None, None, year, pk,
                            round(vals[i], 1), "years", SOURCE_ID, n=n,
                            note="distribution across countries, one value per country"))
    return rows


if __name__ == "__main__":
    rs = load()
    print(len(rs), "rows; year", rs[0].year if rs else None)
    for r in rs:
        if r.sex == "all":
            print(r.percentile, r.value, "n", r.n)
