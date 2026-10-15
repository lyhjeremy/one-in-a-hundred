# One in a Hundred

What does it take to be in the top 1% (or top 10%, or the median) of some group, on income, wealth, height, weight, BMI, age or life expectancy? Pick a measure, a group and a percentile from three controls and get one sentence back with a confidence grade, the spread across sources, and the sources themselves. Type your own number to see where you land, or type the question in words.

> Overview: https://lyhjeremy.github.io/one-in-a-hundred/overview/ · Live: https://lyhjeremy.github.io/one-in-a-hundred/

Design and copy follow [these standards](https://github.com/lyhjeremy/lyhjeremy/blob/main/design-standards.md).

## Headline numbers

818 facts across 20 countries and the world, from 7 official or open sources, every one with a URL and an access date. 3 facts reach grade A (two independent official sources within 10%); 815 are grade B (one official source, or a percentile derived from a published mean). The rules parser that understands typed questions scores 90.0% exact-triple accuracy on a frozen 200-question gold set; the LLM parser is scored in `eval/results.md` once the Worker is deployed.

The fact that started the project, "earning $30,000 a year puts you in the global top 1%", is false under every definition on the site, but not by the same margin. By WID's pre-tax income per adult, $30k sits at the 75th percentile of adults worldwide and the top 1% starts at about $220,000. By the World Bank's consumption per person, $30k is the 94th percentile and the top 1% starts at about $57,000, which is where the "$60k" version of the claim comes from. See the overview for the full comparison.

## How it works

```
chips or typed question -> (Worker parse via Groq | rules parser in the browser) -> triple
  -> static index lookup -> fact -> punchline + grade + sources -> share card
```

The site is static files on GitHub Pages. A Cloudflare Worker (`worker/`) parses typed questions with Groq's free tier and queues questions the site cannot answer; until it is deployed, the browser's rules parser (`parser-rules.js`) answers alone. Queued questions are researched offline by `pipeline/research_queue.py` (one `claude -p` call per question group, with web search) and ship as grade D facts marked "unreviewed" until `pipeline/review.py` promotes them.

## Files

| Path | What |
|---|---|
| `index.html`, `app.js`, `format.js`, `parser-rules.js` | The site: three controls, the answer, a where-do-I-land line, a question box. No framework. |
| `data/metrics.json` | Metric catalogue: ids, units, direction, punchline templates, phrasings. |
| `data/facts/<family>.json`, `data/index.json` | The facts and the lookup index, generated. |
| `f/<id>/`, `cards/<id>.png` | One static page and one share image per fact, generated. |
| `pipeline/fetch/*.py` | One fetcher per source. Raw downloads are git-ignored. |
| `pipeline/build_facts.py`, `verify.py`, `render_cards.py`, `build_site.py` | Build, grade, render. `verify.py` refuses a fact with no source. |
| `pipeline/research_queue.py`, `review.py`, `prompts/`, `schemas/` | The offline research loop and the review CLI. |
| `worker/` | Cloudflare Worker: `/parse`, `/request`, `/health`. |
| `eval/gold.jsonl`, `eval/eval_parser.py`, `eval/results.md` | Parser evaluation. |
| `writeup.md`, `overview/` | The story and the reader-facing page. |

## Rebuild

```bash
pip install -r requirements.txt          # pandas, requests, Pillow, fonttools
# downloads (about 1 GB, git-ignored): see the URL lists at the top of each pipeline/fetch/*.py
python3 pipeline/build_facts.py          # fetch -> facts -> verify -> index
python3 pipeline/render_cards.py         # cards/ and f/
python3 pipeline/build_site.py           # sources/ and data/meta.json
python3 pipeline/build_catalogue.py      # worker/src/catalogue.json
python3 pipeline/test_format.py          # Python and JS formatters agree
python3 eval/eval_parser.py              # WORKER_URL=... to score the LLM parser too
```

## Grades

A: two or more independent sources, at least one official, within 10% at every shown percentile. B: one official source, or a derived percentile. C: sources disagree by more than 10%, or a definitional mismatch. D: automated research, unreviewed. Review can lower a grade but never raise one; the way up is another source.

## What it cannot show

Almost everything is grade B because, for a given definition, official statistics have one producer. Height percentiles outside the US are derived from NCD-RisC means under a normal assumption. BMI percentiles are interpolated inside published bands. The running family is empty until a licensed finisher-level dataset is in hand. Sensitive breakdowns (race and Hispanic origin) appear only for US body measures, exactly as NHANES publishes them. Full list in `writeup.md`.

[MIT](LICENSE) © 2026 Jeremy Lee
