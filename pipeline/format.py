"""Shared number and sentence formatting for One in a Hundred.

Used by build_facts.py, render_cards.py and the eval. app.js mirrors these
rules for client-side rendering; pipeline/test_format.py checks that both
agree on the fixtures in eval/format_fixtures.json.
"""
from __future__ import annotations

import json
import math
import sys
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from pipeline.catalog import CATALOG as METRICS  # noqa: E402

COUNTRY_NAMES = {
    "US": "the United States", "GB": "the United Kingdom", "CA": "Canada", "AU": "Australia",
    "HK": "Hong Kong", "SG": "Singapore", "JP": "Japan", "KR": "South Korea", "DE": "Germany",
    "FR": "France", "NL": "the Netherlands", "CH": "Switzerland", "CN": "China", "IN": "India",
    "ID": "Indonesia", "BR": "Brazil", "NG": "Nigeria", "MX": "Mexico", "KE": "Kenya", "ET": "Ethiopia",
}

# "men in Kenya" reads better than "Kenyan men" for a generated sentence, and it
# never needs a demonym table, so the group name always uses "in <country>".


def round_half_up(x: float, ndigits: int = 0) -> float:
    """Round half away from zero, matching JavaScript's Math.round and
    toFixed, so the Python and JS formatters agree (Python's round() is
    half-to-even)."""
    q = Decimal(1).scaleb(-ndigits)
    return float(Decimal(repr(x)).quantize(q, rounding=ROUND_HALF_UP))


def sig2(x: float) -> float:
    """Round to two significant figures."""
    if x == 0:
        return 0.0
    digits = 2 - int(math.floor(math.log10(abs(x)))) - 1
    return round_half_up(x, digits)


def format_count(n: float) -> str:
    """'about 82 million', 'about 2,900'. Two significant figures, always 'about'."""
    n = sig2(n)
    if n >= 1e9:
        return f"about {n / 1e9:g} billion"
    if n >= 1e6:
        return f"about {n / 1e6:g} million"
    return f"about {int(n):,}"


def format_money(v: float) -> str:
    if v >= 1_000_000:
        return f"${sig2(v) / 1e6:g} million"
    return f"${int(sig2(v)):,}"


def format_time_hm(seconds: float) -> str:
    """Marathon and half marathon: h:mm, rounded to the minute."""
    m = int(round_half_up(seconds / 60))
    return f"{m // 60}:{m % 60:02d}"


def format_time_ms(seconds: float) -> str:
    """10 km and 5 km: mm:ss, rounded to 15 seconds."""
    s = int(round_half_up(seconds / 15) * 15)
    return f"{s // 60}:{s % 60:02d}"


def format_height(cm: float) -> str:
    cm_i = int(round_half_up(cm))
    total_in = cm / 2.54
    ft = int(total_in // 12)
    inch = int(round_half_up(total_in - ft * 12))
    if inch == 12:
        ft, inch = ft + 1, 0
    return f"{cm_i} cm ({ft} ft {inch} in)"


def format_weight(kg: float) -> str:
    return f"{int(round_half_up(kg))} kg ({int(round_half_up(kg * 2.20462))} lb)"


FORMATTERS = {
    "money": format_money,
    "time_hm": format_time_hm,
    "time_ms": format_time_ms,
    "height": format_height,
    "weight": format_weight,
    "bmi": lambda v: f"{round_half_up(v, 1):.1f}",
    "years": lambda v: f"{int(round_half_up(v))}",
    "years_1dp": lambda v: f"{round_half_up(v, 1):.1f} years",
    "hours": lambda v: f"{int(sig2(v)):,} hours",
    "number": lambda v: f"{int(round_half_up(v)):,}",
    "number_1dp": lambda v: f"{round_half_up(v, 1):.1f}",
    "percent": lambda v: f"{round_half_up(v, 1):g}%",
    "count": lambda v: f"{int(sig2(v)):,}",
}


def format_value(metric_id: str, v: float) -> str:
    return FORMATTERS[METRICS["metrics"][metric_id]["format"]](v)


def age_band_phrase(band: str | None) -> str:
    if not band:
        return ""
    if band.endswith("+"):
        return f"aged {band[:-1]} and over"
    if "-" not in band:
        return f"aged {band}"
    lo, hi = band.split("-")
    return f"aged {lo} to {hi}"


def group_name(population: dict, metric_id: str, year: int) -> str:
    """Build the '{group}' phrase: country, sex, age, activity, year, in that order.

    Examples: 'everyone alive', 'adults in Switzerland', 'men aged 30 to 34
    who finished a marathon in 2024', 'women in Japan'.
    """
    m = METRICS["metrics"][metric_id]
    sex = population.get("sex", "all")
    base_noun = m.get("base_noun", "people")
    activity = population.get("activity")
    country = population.get("country")
    band = population.get("age_band")
    cat = population.get("source_category")

    if sex == "m":
        noun = "men"
    elif sex == "f":
        noun = "women"
    else:
        # An activity already says what people did, so "people who finished a
        # marathon", not "finishers who finished a marathon".
        noun = ("people" if activity else base_noun) if (country or band or activity or cat) else None

    parts: list[str] = []
    if noun is None:
        # Nothing narrows the population: the world baseline.
        if metric_id == "age_years":
            return "everyone alive"
        return f"all {base_noun} worldwide"
    parts.append(noun)
    if cat:
        parts.append(f"({cat})")
    if band:
        parts.append(age_band_phrase(band))
    if country:
        parts.append(f"in {COUNTRY_NAMES.get(country, country)}")
    if activity:
        parts.append(METRICS["activities"][activity]["label"])
        parts.append(f"in {year}")
    return " ".join(parts)


def punchline(fact: dict, pct_key: str) -> str:
    """One sentence for a fact at a grid key such as 'p99' or 'p50'.

    pct_key is the visitor's percentile in 'top X%' terms (p50, p90, p99,
    p99.9). For direction 'low' metrics the matching grid value is read from
    the mirrored key (p10, p1, p0.1).
    """
    m = METRICS["metrics"][fact["metric"]]
    pct = pct_key[1:]
    grid_key = grid_key_for(fact["direction"], pct_key)
    value = format_value(fact["metric"], fact["grid"][grid_key])
    group = group_name(fact["population"], fact["metric"], fact["year"])
    tpl_key = f"{fact['direction']}_{'median' if pct == '50' else 'top'}"
    tpl = METRICS["templates"][tpl_key]
    top = METRICS["percentiles"][pct]["top"]
    phrase = m["metric_phrase"]
    if pct == "50":
        # "The median finish time", not "The median a finish time".
        phrase = strip_article(phrase)
    return tpl.format(top=f"{top:g}" if top is not None else "", group=group,
                      metric_phrase=phrase, value=value)


def strip_article(phrase: str) -> str:
    for art in ("an ", "a "):
        if phrase.startswith(art):
            return phrase[len(art):]
    return phrase


def grid_key_for(direction: str, pct_key: str) -> str:
    """Map a visitor percentile key to the grid key holding the value."""
    if direction == "high" or pct_key == "p50":
        return pct_key
    mirror = {"p90": "p10", "p99": "p1", "p99.9": "p0.1"}
    return mirror[pct_key]


if __name__ == "__main__":
    # Smoke test on the shape of the worked example in SPEC.md section 6.
    example = {
        "metric": "marathon_time", "direction": "low", "year": 2024,
        "population": {"base": "world", "country": None, "sex": "m", "age_band": "30-34",
                        "activity": "marathon_finishers", "source_category": None},
        "grid": {"p1": 9540, "p10": 11100, "p50": 14280},
    }
    print(punchline(example, "p99"))
    print(punchline(example, "p50"))
    print(format_count(82_000_000), format_count(2850), format_money(31234), format_money(1_234_567))
    print(format_height(193.2), format_weight(80.4), format_time_ms(1312))
