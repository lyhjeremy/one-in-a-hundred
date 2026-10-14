# One in a Hundred: writeup

_2026-10-14. Live at https://lyhjeremy.github.io/one-in-a-hundred/_

## The result

818 percentile facts across 20 countries and the world, from 7 official or open sources, each with a URL and an access date, graded A to D by how much independent sources agree. Three facts reach A (life expectancy across countries, where the UN and WHO agree within 3%); 815 are B, because for a given definition official statistics tend to have one producer. The rules parser that turns a typed question into (group, measure, percentile) scores 90.0% exact-triple accuracy on a frozen 200-question gold set (`eval/results.md`); the LLM parser's score is filled in once the Worker is deployed.

## The claim that started it

"Earning $30,000 a year puts you in the top 1% of earners worldwide." Depending on who repeats it, the number is $30k or $60k. Both numbers are on the site now, with their sources, and neither is the top 1%. What differs is the definition:

| Definition | Source | Median | Top 10% | Top 1% | Where $30k lands |
|---|---|---|---|---|---|
| Pre-tax national income per adult (20+), PPP | WID.world, 2023 | $11,000 | $64,000 | $220,000 | 75th percentile |
| Post-tax disposable income per adult, PPP | WID.world, 2023 | $12,000 | $66,000 | $200,000 | 72nd |
| Household consumption or income per person, PPP | World Bank PIP, 2022 | $3,200 | $19,000 | $57,000 | 94th |

The "$60k" claim is roughly right for the World Bank's per-person consumption measure, which counts children, uses survey data, and is net of taxes. The "$30k" claim is not right under any of the three. The site keeps these as three separate measures rather than averaging them, because they measure different things; the panel under each punchline says which.

Two more facts worth repeating. One in a hundred people alive is at least 84.6 years old (UN WPP 2025 pyramid; the median person is 31.9). The tallest 1% of Dutch men stand at least 202 cm, and that number is derived from a published mean and an assumed spread, which is why it is grade B and says so.

## How the numbers are made

Each fact is one distribution: a metric, a population slice, a reference year, and a grid of percentile points. The fetchers (`pipeline/fetch/`) read each source into the same row shape; `build_facts.py` merges rows into facts; `verify.py` computes the spread across sources at each shown percentile and assigns the grade by fixed rules. Nothing is typed in by hand except the WID variable codes and the band edges NCD-RisC publishes.

| Source | Gives | How the percentiles arise |
|---|---|---|
| UN World Population Prospects 2024 | Age of everyone alive, by country and sex; life expectancy; the population counts under every fact | Read straight off the single-year pyramid |
| WHO Global Health Observatory | Life expectancy by country | One value per country; second source for the A grades |
| WID.world | Pre-tax and post-tax income, net wealth, per adult | Published thresholds (p50, p90, p99, p99.9), local currency converted at WID's PPP factor |
| World Bank PIP | Consumption or income per person | `popshare` queries per country; bisection on the poverty line for the world aggregate |
| CDC NHANES 2021-2023 | US height, weight, BMI | Weighted quantiles of measured individuals; by sex, age band, and the survey's own race and Hispanic-origin categories |
| NCD-RisC height | Height at 19 by country and sex | Mean plus an assumed SD (NHANES-measured, same sex), normal quantiles; flagged derived |
| NCD-RisC BMI | BMI by country, sex, age | Interpolated inside published bands (18.5, 20, 25, 30, 35, 40); bottom band skipped |

Grading rules, in full: A needs two or more mutually independent sources, at least one official, agreeing within 10% at every exposed percentile. B is one official source, or a derived point without a measured confirmation. C is disagreement above 10% or a definitional mismatch. D is a queued, unreviewed fact. Review can lower a grade with a reason and never raise one.

## The parser

Two parsers return the same shape. The rules parser (`parser-rules.js`, about 200 lines) runs in the browser: regexes for percentiles, sex, age and value, a country alias table, and a phrasing match with a Dice-coefficient fallback for typos. The LLM parser runs in a Cloudflare Worker and asks Groq's Llama for JSON against the same catalogue; the browser falls back to the rules parser on a 2.5 s timeout or any error, and says so.

Gold set: 200 questions in five buckets, frozen at sha1 `0b1dd183b3f8` after one correction pass. Rules parser: 95% canonical, 92% paraphrase, 60% value-bearing, 90% ambiguous, 92% out-of-scope with 3 hallucinated ids. The weak bucket is value extraction ("I ran a 1:45 half marathon as a 45 year old woman"), where the time, the age and the distance compete for the same digits. The rules parser was adjusted once after seeing its failures, so its number is optimistic by an unknown amount; the LLM parser will be scored cold.

## What it cannot show

- Almost everything is B. The A grade needs genuinely independent producers measuring the same definition, and for income, wealth, height and age there is usually one. The honest reading is "one official source, no second to compare", and that is what the panel says.
- Height outside the US is derived, not measured: NCD-RisC publishes means, the SD is borrowed from NHANES, and the tails of real height distributions are a little heavier than normal. The Dutch 202 cm is probably a centimetre or two high.
- BMI percentiles are linear interpolations inside bands, so a p99 that falls in the 35 to 40 band is placed by proportion, not measured.
- The running family is empty. The best candidate (429,000 US finishers across 641 races in 2023) sits on Kaggle behind an account token; single-race files are either qualification-gated (Boston) or of unclear licence. `pipeline/fetch/running.py` is written and waits for the file.
- Population counts for age bands and categories are weighted shares of a survey sample applied to the UN count, so "that's about 2,900 people" lines are estimates.
- Sensitive dimensions appear only where the source publishes them (NHANES race and Hispanic origin), with the source's category names, and are never combined across sources.
- The LLM parser, the request queue and the research loop are built but not deployed: they need a Cloudflare account and a Groq key.

## Sources

UN DESA, World Population Prospects 2024 (CC BY 3.0 IGO). WHO Global Health Observatory, indicator WHOSIS_000001 (CC BY-NC-SA 3.0 IGO). World Inequality Database, bulk download September 2026 (CC BY 4.0). World Bank Poverty and Inequality Platform, API release 20260922, 2021 PPP (CC BY 4.0). CDC NHANES August 2021 to August 2023, BMX_L and DEMO_L (public domain). NCD Risk Factor Collaboration, height (Lancet 2020) and adult BMI (Nature 2026) (CC BY 4.0). Full table with access dates at `/sources/`.
