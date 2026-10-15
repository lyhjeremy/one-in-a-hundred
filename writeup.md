# One in a Hundred: writeup

_v0.3.1, 2026-10-15. Live at https://lyhjeremy.github.io/one-in-a-hundred/_

## The result

950 percentile facts across 20 countries and the world, from 72 sources, each with a URL and an access date, graded A to D by how much independent sources agree. Three facts reach A (life expectancy across countries, where the UN and WHO agree within 3%); 906 are B, because for a given definition official statistics tend to have one producer; 41 are D, researched automatically from seed questions and not yet reviewed. 103 facts carry a time series back to 1980 (income and wealth) or 1989 (height cohorts). The rules parser that turns a typed question into (group, measure, percentile) scores 90.5% exact-triple accuracy on a frozen 200-question gold set (`eval/results.md`); the LLM parser's score is filled in once the Worker is deployed.

## The claim that started it

"Earning $30,000 a year puts you in the top 1% of earners worldwide." Depending on who repeats it, the number is $30k or $60k. Both are on the site now, with their sources, and neither is the top 1%. What differs is the definition:

| Definition | Source | Median | Top 10% | Top 1% | Where $30k lands |
|---|---|---|---|---|---|
| Pre-tax national income per adult (20+), PPP | WID.world, 2023 | $11,000 | $64,000 | $220,000 | 75th percentile |
| Post-tax disposable income per adult, PPP | WID.world, 2023 | $12,000 | $66,000 | $200,000 | 72nd |
| Household consumption or income per person, PPP | World Bank PIP, 2022 | $3,200 | $19,000 | $57,000 | 94th |

The "$60k" claim is roughly right for the World Bank's per-person consumption measure, which counts children, uses survey data, and is net of taxes. The "$30k" claim is not right under any of the three. The site keeps these as three separate measures rather than averaging them; the evidence column says which one you are looking at.

The history chart adds a second reading. The world top-1% threshold under WID's definition was $131,000 in 1980 and $223,000 in 2023 in constant purchasing-power dollars, a real rise of 70%. Dutch men's height at 19 went from 181.5 cm (1989 cohort) to 183.8 cm (2019), and has been flat since 2004.

Two more worth repeating. One in a hundred people alive is at least 84.6 years old (UN WPP 2025 pyramid; the median person is 31.9). To be in the fastest 1% of the 778,747 people who finished a timed marathon in the 2013 research sample, you needed to run under 2:50; the median finisher took 4:19.

## The screen

Version 0.1 put a question box, a chip row with four dropdowns, two rows of measure chips and a percentile row above the answer, and compare, today's fact and three share buttons below it. It was hard to use. Version 0.2 cut it to three controls above the sentence. Version 0.3 spends the width of a desktop screen on three columns with the modes made explicit:

- Left rail: Explore (measure, group, percentile), Ask (a question in words), Where do I land (your number on the curve, kept in a profile), Compare (a second group on the same curve), Surprise me.
- Centre: the narrowing chain ("All adults › Netherlands › Men › about 7.2 million people", each step removable), the sentence, the full distribution curve with the chosen percentile and your own value marked, and the threshold over time where history exists.
- Right: the grade and its reason, the range across sources, the group size and where it came from, the definition, the caveat, and the sources with the value each gives at this percentile.

The curve is the memorable element and the honest one: it shows that the sentence is one point read off a published grid of eight or nine, joined by straight lines, and it shows how thin the grid is for a researched fact (two points for the chess rating).

## How the numbers are made

Each fact is one distribution: a measure, a population slice, a reference year, a grid of percentile points, and its sources. The fetchers (`pipeline/fetch/`) read each source into the same row shape, now for every available year; `build_facts.py` makes the latest year the fact and earlier years its series, restricted to the same sources; `verify.py` computes the spread across sources at each shown percentile and assigns the grade by fixed rules.

| Source | Gives | How the percentiles arise |
|---|---|---|
| UN World Population Prospects 2024 | Age of everyone alive, by country and sex; life expectancy; the population counts under every fact | Read straight off the single-year pyramid |
| WHO Global Health Observatory | Life expectancy by country | One value per country; second source for the A grades |
| WID.world | Pre-tax and post-tax income, net wealth, per adult, 1980 to 2023 | Published thresholds, local currency converted at WID's PPP factor |
| World Bank PIP | Consumption or income per person | `popshare` queries per country; bisection on the poverty line for the world aggregate |
| CDC NHANES 2021-2023 | US height, weight, BMI | Weighted quantiles of measured individuals; by sex, age band, and the survey's own race and Hispanic-origin categories |
| NCD-RisC height | Height at 19 by country, sex and cohort, 1989 to 2019 | Mean plus an assumed SD (NHANES-measured, same sex), normal quantiles; flagged derived |
| NCD-RisC BMI | BMI by country, sex, age | Interpolated inside published bands; bottom band skipped |
| Allen, Dechow, Pope and Wu (2017) | Marathon chip times, 9.8 million finisher records 1970 to 2013 | Plain quantiles of the 897,204 finishers in 2013, by sex, age band and country |
| Research loop (grade D) | Anything a visitor or the seed list asks that the catalogue lacks | `claude -p` with web search, a fixed prompt and a JSON schema; the model defines the measure, Python builds the fact, a person reviews it later |

## Unexplored categories

The original brief asked for an answer to whatever someone types, even outside the curated set. Instant answers need a server with a search-enabled model; that route is written (`worker/src/research.js`, a Cloudflare Worker calling Groq) and waits for accounts. Two things work today. A seed list of sixty popular questions (`pipeline/seeds/popular_questions.jsonl`: chess ratings, IQ, push-ups, typing speed, Instagram followers, VO2 max, savings by age, SAT scores and so on) has been run through the offline loop. 42 questions produced a fact; 18 found nothing the model would stand behind (Wordle average guesses, how many marathons the top 1% have run). Each result ships as a grade D fact with an unreviewed stamp the moment it is built. One, the bench press, is held back because its grid ran backwards (the median was below the 25th percentile), which the build refuses. A question that still misses offers "Request this fact", which files a GitHub issue the loop picks up.

The first researched fact shows both the promise and the hazard. For "what chess rating is the top 1%" the model found four sources, wrote a careful caveat about FIDE's rating floor and the difference between FIDE, US Chess and Lichess pools, and then averaged values from those different pools into one grid. The grade D and the stamp are there for exactly this; `review.py` is where a person picks one definition. The prompt now tells the model to keep other scales in the caveat, not the sources.

## The parser

Two parsers return the same shape. The rules parser (`parser-rules.js`) runs in the browser: regexes for percentiles, sex, age and value, a country alias table, and a phrasing match that accepts inflections (marathoners, earners) with a Dice-coefficient fallback for typos. Researched measures bring their own phrasings, so a new fact becomes askable at once. The LLM parser runs in the Worker and asks Groq's Llama for JSON against the same catalogue; the browser falls back to the rules parser on a 2.5 s timeout or any error.

Gold set: 200 questions in five buckets, frozen at sha1 `0b1dd183b3f8`. Rules parser: 96% canonical, 92% paraphrase, 60% value-bearing, 90% ambiguous, 92% out-of-scope with 3 hallucinated ids. The weak bucket is value extraction, where the time, the age and the distance compete for the same digits. The rules parser was adjusted twice after seeing failures (once on the gold set, once on a live question), so its number is optimistic by an unknown amount; the LLM parser will be scored cold.

## What it cannot show

- Almost everything is B. The A grade needs independent producers measuring the same definition, and for income, wealth, height and age there is usually one.
- Height outside the US is derived, not measured, and real height tails are slightly heavier than normal: the Dutch 202 cm is probably a centimetre or two high.
- BMI percentiles are linear interpolations inside published bands.
- Marathon facts describe the 2013 research sample (61% US), not every marathon on earth; the "world" running group means finishers in that sample.
- Researched facts are only as good as what the web says. They are graded D, stamped, and can mix definitions until reviewed. Their group sizes are unknown, so no "that's about N people" line appears.
- The history charts show the threshold for one definition over time; a definitional change inside the source (WID's 2024 rating compression, for example, or a survey redesign) shows up as a kink, not a note.
- Group counts for age bands and categories are survey shares applied to UN totals.
- The LLM parser, live research and the request queue need a Cloudflare account and a Groq key before they run.

## Sources

UN DESA, World Population Prospects 2024 (CC BY 3.0 IGO). WHO Global Health Observatory, WHOSIS_000001 (CC BY-NC-SA 3.0 IGO). World Inequality Database, bulk download September 2026 (CC BY 4.0). World Bank Poverty and Inequality Platform, release 20260922, 2021 PPP (CC BY 4.0). CDC NHANES August 2021 to August 2023 (public domain). NCD Risk Factor Collaboration, height (Lancet 2020) and adult BMI (Nature 2026) (CC BY 4.0). Allen, Dechow, Pope and Wu (2017), Management Science, data at faculty.chicagobooth.edu/george.wu/research/marathon/. Researched facts cite their own sources on each fact page. Full table with access dates at `/sources/`.
