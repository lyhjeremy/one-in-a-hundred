# One in a Hundred: writeup

_v0.3.1, 2026-10-15. Live at https://lyhjeremy.github.io/one-in-a-hundred/_

The project started with a sentence that gets passed around a lot: "Earning $30,000 a year puts you in the top 1% of earners worldwide." Depending on who repeats it, the number is $30k or $60k. Both versions are on the site now, with their sources, and neither one is the top 1%. The answer depends on which definition of income you pick:

| Definition | Source | Median | Top 10% | Top 1% | Where $30k lands |
|---|---|---|---|---|---|
| Pre-tax national income per adult (20+), PPP | WID.world, 2023 | $11,000 | $64,000 | $220,000 | 75th percentile |
| Post-tax disposable income per adult, PPP | WID.world, 2023 | $12,000 | $66,000 | $200,000 | 72nd |
| Household consumption or income per person, PPP | World Bank PIP, 2022 | $3,200 | $19,000 | $57,000 | 94th |

The "$60k" version is roughly right for the World Bank's per-person consumption measure, which counts children, uses survey data and is net of taxes. The "$30k" version fails under all three. The site keeps them as three separate measures, and the evidence column says which one you are looking at; averaging them would produce a number that belongs to no definition at all.

The history chart adds a second reading. Under WID's definition the world top-1% threshold was $131,000 in 1980 and $223,000 in 2023 in constant purchasing-power dollars, a real (inflation-adjusted) rise of 70%. Heights move too, more slowly: Dutch men at 19 went from 181.5 cm (1989 cohort) to 183.8 cm (2019), and have been flat since 2004.

Two more from the site. One in a hundred people alive is at least 84.6 years old (UN World Population Prospects 2024, reference year 2025; the median person is 31.9). And to be in the fastest 1% of the 778,747 people who finished a timed marathon in the 2013 research sample, you needed to run under 2:50, while the median finisher took 4:19.

## What is in it

There are 950 percentile facts across 20 countries and the world, drawn from 72 sources, each with a URL and an access date and graded A to D by how much independent sources agree. Three reach A (life expectancy across countries, where the UN and WHO agree within 3%). 906 are B, because for a given definition official statistics tend to have one producer. The other 41 are D: researched automatically from seed questions and not yet reviewed. 103 facts carry a time series back to 1980 (income and wealth) or 1989 (height cohorts). The rules parser that turns a typed question into (group, measure, percentile) scores 90.5% exact-triple accuracy on a frozen 200-question gold set (`eval/results.md`); the LLM parser's score gets filled in once the Worker is deployed.

## The screen

Version 0.1 was hard to use. It put a question box, a chip row with four dropdowns, two rows of measure chips and a percentile row above the answer, then compare, today's fact and three share buttons below it. Version 0.2 cut that to three controls above the sentence, and version 0.3 uses the width of a desktop screen for three columns with the modes made explicit.

The left rail holds the modes: Explore (measure, group, percentile), Ask (a question in words), Where do I land (your number on the curve, kept in a profile), Compare (a second group on the same curve) and Surprise me. The center has the narrowing chain ("All adults › Netherlands › Men › about 7.2 million people", where each step can be removed), then the sentence, the full distribution curve with the chosen percentile and your own value marked, and the threshold over time where history exists. The right column is the evidence: the grade and its reason, the range across sources, the group size and where it came from, the definition, the caveat, and the sources with the value each gives at this percentile.

The curve is what people remember, and it is also the part that keeps the sentence in proportion. It shows that the sentence is one point read off a published grid of eight or nine points joined by straight lines, and it shows how thin that grid is for a researched fact (the chess rating has two points).

## How the numbers are made

Each fact is one distribution: a measure, a population slice, a reference year, a grid of percentile points and its sources. The fetchers (`pipeline/fetch/`) read each source into the same row shape, now for every available year. `build_facts.py` makes the latest year the fact and earlier years its series, restricted to the same sources, and `verify.py` computes the spread across sources at each shown percentile and assigns the grade by fixed rules.

| Source | Gives | How the percentiles arise |
|---|---|---|
| UN World Population Prospects 2024 | Age of everyone alive, by country and sex; life expectancy; the population counts under every fact | Read straight off the single-year pyramid |
| WHO Global Health Observatory | Life expectancy by country | One value per country; second source for the A grades |
| WID.world | Pre-tax and post-tax income, net wealth, per adult, 1980 to 2023 | Published thresholds, local currency converted at WID's PPP factor |
| World Bank PIP | Consumption or income per person | `popshare` queries per country; bisection on the poverty line for the world aggregate |
| CDC NHANES 2021-2023 | US height, weight, BMI | Weighted quantiles of measured individuals; by sex, age band, and the survey's own race and Hispanic-origin categories |
| NCD-RisC height | Height at 19 by country, sex and cohort, 1989 to 2019 | Mean plus an assumed SD (NHANES-measured, same sex), normal quantiles; flagged derived |
| NCD-RisC BMI | BMI by country, sex, age | Interpolated inside published bands; bottom band skipped |
| Allen, Dechow, Pope and Wu (2017) | Marathon chip times, 9.8 million finisher records 1970 to 2013 | Plain quantiles of the 2013 finishers with a valid chip time and sex (778,747 in the all-finishers fact), by sex, age band and country |
| Research loop (grade D) | Anything a visitor or the seed list asks that the catalog lacks | `claude -p` with web search, a fixed prompt and a JSON schema; the model defines the measure, Python builds the fact, a person reviews it later |

## Questions outside the catalog

The original brief asked for an answer to whatever someone types, even outside the curated set. Instant answers need a server with a search-enabled model. That route is written (`worker/src/research.js`, a Cloudflare Worker calling Groq) and waits for accounts, so two things stand in for it today.

The first is a seed list of sixty popular questions (`pipeline/seeds/popular_questions.jsonl`: chess ratings, IQ, push-ups, typing speed, Instagram followers, VO2 max, savings by age, SAT scores and so on), which has been run through the offline loop. 42 questions produced a fact and 18 found nothing the model would stand behind (Wordle average guesses, for one, and how many marathons the top 1% have run). Each result ships as a grade D fact with an unreviewed stamp the moment it is built. One, the bench press, is held back because its grid ran backwards (the median was below the 25th percentile), which the build refuses. The second is for a question that still misses: the page offers "Request this fact", which files a GitHub issue the loop picks up.

The first researched fact showed what the loop can do and where it goes wrong. For "what chess rating is the top 1%" the model found four sources and wrote a careful caveat about FIDE's rating floor and the difference between the FIDE, US Chess and Lichess pools; then it averaged values from those different pools into one grid. The grade D and the stamp exist for this case, and `review.py` is where a person picks one definition. The prompt now tells the model to put other scales in the caveat and leave them out of the sources.

The full batch turned up two more. The NBA height came back as 86, in inches, under a centimeter measure, and went live as "at least 86 cm" until a read through the grids caught it. The student debt median came back as 25.1 because the Federal Reserve table is in thousands. I corrected both by hand, and the build now skips a researched fact whose values sit far outside the curated range of its measure, or a money grid entirely under 100.

## The parser

Two parsers return the same shape. The rules parser (`parser-rules.js`) runs in the browser, with regexes for percentiles, sex, age and value, a country alias table, and a phrasing match that accepts inflections (marathoners, earners) and falls back to a Dice coefficient for typos. Researched measures bring their own phrasings, so a new fact can be asked about as soon as it exists. The LLM parser runs in the Worker and asks Groq's Llama for JSON against the same catalog; the browser falls back to the rules parser on a 2.5 s timeout or any error.

The gold set is 200 questions in five buckets, frozen at sha1 `0b1dd183b3f8`. The rules parser scores 95% on canonical questions, 92% on paraphrases, 60% on value-bearing ones, 95% on ambiguous ones and 92% on out-of-scope ones, with 3 hallucinated ids. Value extraction is the weak bucket, because the time, the age and the distance compete for the same digits. I adjusted the rules parser twice after seeing failures (once on the gold set, once on a live question), so its number is optimistic by an unknown amount. The LLM parser will be scored cold.

## What it cannot show

- Almost everything is B. The A grade needs independent producers measuring the same definition, and for income, wealth, height and age there is usually one.
- Height outside the US is derived from means under a normal assumption. Measured height tails are slightly heavier than normal, so the Dutch 202 cm is probably a centimeter or two high.
- BMI percentiles are linear interpolations inside published bands.
- Marathon facts describe the 2013 research sample (61% US), which is a subset of the world's marathons; the "world" running group means finishers in that sample.
- Researched facts are only as good as what the web says. They are graded D, stamped, and can mix definitions until reviewed. Their group sizes are unknown, so they carry no "that's about N people" line.
- The history charts show the threshold for one definition over time. A definitional change inside the source (WID's 2024 rating compression, for example, or a survey redesign) shows up as a kink in the line with no note attached.
- Group counts for age bands and categories are survey shares applied to UN totals.
- The LLM parser, live research and the request queue need a Cloudflare account and a Groq API key before they run.

## Sources

UN DESA, World Population Prospects 2024 (CC BY 3.0 IGO). WHO Global Health Observatory, WHOSIS_000001 (CC BY-NC-SA 3.0 IGO). World Inequality Database, bulk download September 2026 (CC BY 4.0). World Bank Poverty and Inequality Platform, release 20260922, 2021 PPP (CC BY 4.0). CDC NHANES August 2021 to August 2023 (public domain). NCD Risk Factor Collaboration, height (Lancet 2020) and adult BMI (Nature 2026) (CC BY 4.0). Allen, Dechow, Pope and Wu (2017), Management Science, data at faculty.chicagobooth.edu/george.wu/research/marathon/. Researched facts cite their own sources on each fact page. The full table with access dates is at `/sources/`.
