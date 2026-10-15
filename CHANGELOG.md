# Changelog

All three versions shipped on 2026-10-14. Dates below are the same day; the order is what matters.

## v0.3: three columns, five modes, the curve, researched measures

Why: the v0.2 screen was clear but narrow and flat, the modes were implicit, and questions outside the four families had no answer at all.

Screen
- Three-column layout on wide screens (`index.html`, `assets/app.css`): mode rail on the left, the answer in the centre, evidence on the right. Two breakpoints (1140 px, 760 px) stack it.
- Five explicit modes: Explore, Ask, Where do I land, Compare, Surprise me. Mode is part of the URL (`mode=`).
- Narrowing chain above the sentence ("All adults › Netherlands › Men › about 7.2 million people"), each step removable, with a hint naming the dimensions still available.
- Distribution curve under every sentence (`chart.js`): value against share of the group at or below it, log scale for money, the chosen percentile marked in oxide, the visitor's own value in pine, hover tooltip, a legend when two groups are drawn.
- History chart where the source has it: the chosen threshold over the years, with a caption stating the change.
- Compare returned (second group dashed on the same curve, one-line comparison). The profile returned as "Your profile" in Where do I land: every placed value across measures, browser storage only.
- Enter submits the question box; Shift+Enter makes a new line. Four example questions.
- Empty state offers "Request this fact" (prefilled GitHub issue) and, once the Worker is deployed, "Research it now".

Data
- Fetchers emit every available year; `build_facts.py` keeps the latest year as the fact and earlier years as `fact.series`, from the same sources only. 103 facts carry history (WID from 1980, NCD-RisC cohorts from 1989).
- `pipeline/catalog.py`: one loader merging `data/metrics.json` with `data/metrics_extra.json`; every script imports from it.
- Research loop can define a new measure: `new_metric` in `pipeline/schemas/research.json`, written to `pipeline/inbox/metrics/`, merged into `data/metrics_extra.json` (family "more") by `build_facts.py`; `app.js` merges the same file at load, so a researched measure is askable with its own phrasings.
- Research prompt tightened: sources must share one definition; other scales go in the caveat.
- Seed list `pipeline/seeds/popular_questions.jsonl` (60 questions outside the four families) run through `research_queue.py --from-file`. First results ship as grade D with the unreviewed stamp.
- New number formats on both sides (`number`, `number_1dp`, `percent`, `count`), parity-tested.

Worker
- `/research` route (`worker/src/research.js`): Groq's search-enabled model, result returned as a D-grade fact in the site's shape, question queued for the offline loop. Waits for deployment.

Docs
- README, writeup, overview rewritten. Known gap: phone-width layout written but not screenshot-verified.

## v0.2: answer-first, three controls

Why: the v0.1 screen was too hard to use. A visitor scrolled past a question box, a chip row with four dropdowns, two rows of measure chips and a percentile row before the answer, then found compare, today's fact and three share buttons below it.

- One grouped Measure select; Group selects that appear only when they offer a choice; Median / Top 10% / Top 1%.
- Answer in large type with grade, group size and "Why this grade?", one where-do-I-land line, the question box demoted, three buttons.
- Cut: comparison view, Theme of the Day, top 0.1%, Web Share sheet, client-rendered custom card (`cards.js`, `data/themes.json` removed).
- When a selection makes the current combination unavailable, the page keeps what was just changed and drops other dimensions until a fact exists.
- Parser: phrasings match their inflections ("marathoners"); honest message when a measure is known but has no data; no unrelated "nearest groups".
- Running family added: 93 marathon facts from the Allen, Dechow, Pope and Wu (2017) finisher records (897,204 finishers in 2013). Fixed the grid monotonicity check, which had assumed lower-is-better grids run the other way.

## v0.1: first public version

- 818 facts from 7 sources (UN WPP, WHO GHO, WID, World Bank PIP, NHANES, NCD-RisC height and BMI) across 20 countries and the world; grades A 3 / B 815.
- Static site on GitHub Pages: chips, percentile buttons, punchline, sources panel, where-do-I-land, compare, surprise, today's fact, share cards, typed questions through a rules parser.
- 818 per-fact pages with OpenGraph tags and palette-PNG share cards.
- Frozen 200-question gold set and eval (rules parser 90.0%, later 90.5% after two recorded adjustments).
- Worker (`/parse`, `/request`, `/health`), research loop, review CLI and health workflow written; not deployed.
- Privacy, terms, about, overview and sources pages.
