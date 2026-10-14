"""Shared scaffolding for fetchers.

Every fetcher exposes `load() -> list[Row]` and a `SOURCE` dict. A Row is one
percentile value for one population slice. build_facts.py groups Rows into
facts. Raw downloads live under pipeline/raw/<source-id>/ (git-ignored) and
each fetcher records the access date in meta.json there.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, asdict
from datetime import date
from pathlib import Path

PIPELINE = Path(__file__).resolve().parent.parent
ROOT = PIPELINE.parent
RAW = PIPELINE / "raw"

LAUNCH_COUNTRIES = ["US", "GB", "CA", "AU", "HK", "SG", "JP", "KR", "DE", "FR",
                    "NL", "CH", "CN", "IN", "ID", "BR", "NG", "MX", "KE", "ET"]

ISO3_TO_2 = {
    "USA": "US", "GBR": "GB", "CAN": "CA", "AUS": "AU", "HKG": "HK", "SGP": "SG", "JPN": "JP",
    "KOR": "KR", "DEU": "DE", "FRA": "FR", "NLD": "NL", "CHE": "CH", "CHN": "CN", "IND": "IN",
    "IDN": "ID", "BRA": "BR", "NGA": "NG", "MEX": "MX", "KEN": "KE", "ETH": "ET",
}

# Grid keys the fact model accepts, as (key, cumulative share from the bottom).
GRID = [("p0.1", 0.001), ("p1", 0.01), ("p10", 0.10), ("p25", 0.25), ("p50", 0.50),
        ("p75", 0.75), ("p90", 0.90), ("p99", 0.99), ("p99.9", 0.999)]


@dataclass
class Row:
    metric: str
    base: str                # "world" | "country"
    country: str | None      # ISO alpha-2
    sex: str                 # "all" | "m" | "f"
    age_band: str | None     # source's own band, e.g. "30-34", "65+"
    activity: str | None
    source_category: str | None
    year: int
    percentile: str          # grid key, e.g. "p99"
    value: float             # in the metric's base unit
    unit: str
    source_id: str
    n: float | None = None   # population size of the slice, if this source gives it
    derived: bool = False    # True when the percentile was derived, not measured
    note: str | None = None
    n_source: str | None = None  # source id for n when it is not this source (usually UN WPP)


WPP_ID = "src-un-wpp-2024"


def write_meta(source_id: str, urls: list[str], extra: dict | None = None) -> None:
    d = RAW / source_id
    d.mkdir(parents=True, exist_ok=True)
    meta = {"accessed": date.today().isoformat(), "urls": urls}
    if extra:
        meta.update(extra)
    (d / "meta.json").write_text(json.dumps(meta, indent=1) + "\n")


def read_meta(source_id: str) -> dict:
    p = RAW / source_id / "meta.json"
    return json.loads(p.read_text()) if p.exists() else {}


def weighted_quantiles(values, weights, probs) -> list[float]:
    """Weighted quantiles by cumulative weight, linear between observations."""
    pairs = sorted(zip(values, weights))
    v = [p[0] for p in pairs]
    w = [p[1] for p in pairs]
    total = sum(w)
    cum = []
    c = 0.0
    for x in w:
        c += x
        cum.append(c / total)
    out = []
    for p in probs:
        # first index where cum >= p
        lo = 0
        hi = len(cum) - 1
        while lo < hi:
            mid = (lo + hi) // 2
            if cum[mid] < p:
                lo = mid + 1
            else:
                hi = mid
        out.append(v[lo])
    return out


def normal_quantile(mean: float, sd: float, p: float) -> float:
    """Inverse normal CDF via the Acklam approximation (no scipy dependency)."""
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    plow = 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        z = (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    elif p > 1 - plow:
        q = math.sqrt(-2 * math.log(1 - p))
        z = -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    else:
        q = p - 0.5
        r = q * q
        z = (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)
    return mean + sd * z
