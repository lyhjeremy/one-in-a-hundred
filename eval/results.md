# Parser evaluation

Run 2026-10-14. Gold set: 200 questions, sha1 0b1dd183b3f8.

## Rules parser (browser fallback, baseline)

Exact-triple accuracy: **180/200 = 90.0%**

| Bucket | Exact | n | Accuracy |
|---|---|---|---|
| canonical | 76 | 80 | 95% |
| paraphrase | 37 | 40 | 92% |
| value | 12 | 20 | 60% |
| ambiguous | 18 | 20 | 90% |
| out_of_scope | 37 | 40 | 92% |

Per-field accuracy (in-scope questions): metric 151/160, country 160/160, sex 160/160, age_band 156/160, percentile 159/160, value 15/20
Hallucinated catalogue ids on out-of-scope questions: 3/40
Latency: p50 0 ms, p95 1 ms

Example failures:

- [canonical] "oldest 0.1% of people alive in Brazil": expected {"metric": "age_years", "country": "BR", "sex": "all", "age_band": null, "percentile": 99.9, "value": null}, got metric=None country=BR sex=all age=None pct=99.9 value=None
- [canonical] "99th percentile BMI for women who are 55 in Brazil": expected {"metric": "bmi_adult", "country": "BR", "sex": "f", "age_band": "55", "percentile": 99, "value": null}, got metric=bmi_adult country=BR sex=f age=None pct=99 value=None
- [canonical] "oldest 0.1% of people alive in Kenya": expected {"metric": "age_years", "country": "KE", "sex": "all", "age_band": null, "percentile": 99.9, "value": null}, got metric=None country=KE sex=all age=None pct=99.9 value=None
- [canonical] "how fast is a top 10% marathon for Korean women who are 55": expected {"metric": "marathon_time", "country": "KR", "sex": "f", "age_band": "55", "percentile": 90, "value": null}, got metric=marathon_time country=KR sex=f age=None pct=90 value=None
- [paraphrase] "tallest 10 percent of japanese women": expected {"metric": "height_adult_cm", "country": "JP", "sex": "f", "age_band": null, "percentile": 90, "value": null}, got metric=None country=JP sex=f age=None pct=90 value=None
- [paraphrase] "how old do you have to be to be older than 99% of people": expected {"metric": "age_years", "country": null, "sex": "all", "age_band": null, "percentile": 99, "value": null}, got metric=age_years country=None sex=all age=99+ pct=99 value=None
- [paraphrase] "oldest 1% of japanese women": expected {"metric": "age_years", "country": "JP", "sex": "f", "age_band": null, "percentile": 99, "value": null}, got metric=None country=JP sex=f age=None pct=99 value=None
- [value] "I make $250,000 a year in the US, what percentile is that": expected {"metric": "income_pretax_adult_ppp", "country": "US", "sex": "all", "age_band": null, "percentile": 99, "value": 250000}, got metric=income_pretax_adult_ppp country=US sex=all age=None pct=99 value=250
- [value] "I'm 190 cm, how do I compare to Dutch men": expected {"metric": "height_adult_cm", "country": "NL", "sex": "m", "age_band": null, "percentile": 99, "value": 190}, got metric=None country=NL sex=m age=None pct=99 value=190
- [value] "I am 6 ft 2 where do I rank among american men": expected {"metric": "height_adult_cm", "country": "US", "sex": "m", "age_band": null, "percentile": 99, "value": 187.96}, got metric=None country=US sex=m age=None pct=99 value=188
- [value] "I'm 72, how old is that compared to everyone alive": expected {"metric": "age_years", "country": null, "sex": "all", "age_band": null, "percentile": 99, "value": 72}, got metric=age_years country=None sex=all age=72 pct=99 value=None
- [value] "my bmi is 31 as a 30 year old woman in the uk, what percentile": expected {"metric": "bmi_adult", "country": "GB", "sex": "f", "age_band": "30", "percentile": 99, "value": 31}, got metric=bmi_adult country=GB sex=f age=30 pct=99 value=None

## LLM parser

Not run: WORKER_URL not set. Deploy the Worker and rerun with WORKER_URL to fill this section.

## Notes

- The rules parser was adjusted once after seeing its failures on this set (superlative percentiles such as "oldest 10%", decade ages like "in their 30s", the "avg" synonym, and two metric phrasings), and two gold labels that were generation bugs were corrected at the same time. Its number is therefore optimistic by an unknown amount. The LLM parser is scored without any tuning on this set.
- Latency for the rules parser is in-process Node; for the LLM parser it is a round trip from this machine to the Worker.
