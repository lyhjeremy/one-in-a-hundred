# Semantic parser evaluation

Run 2026-11-13 on Apple M4, Darwin 25.5.0, Chromium 147.0.7727.15 (Playwright, new headless). Gold set: 200 questions, sha1 0b1dd183b3f8 (frozen in commit b31ff53). Settings tuned on the dev split only: 104 questions, sha1 2d39248d0114.

## Frozen gold set

| Parser | Exact | Accuracy | canonical | paraphrase | value | ambiguous | out of scope | OOS ids returned | Abstain rate |
|---|---|---|---|---|---|---|---|---|---|
| Rules (baseline) | 181/200 | 90.5% | 76/80 | 37/40 | 12/20 | 19/20 | 37/40 | 3/40 | 26.5% |
| Embeddings alone | 166/200 | 83.0% | 70/80 | 33/40 | 11/20 | 15/20 | 37/40 | 3/40 | 27.5% |
| Hybrid | 172/200 | 86.0% | 73/80 | 34/40 | 12/20 | 16/20 | 37/40 | 3/40 | 25.0% |

## Dev split (used for tuning)

Rules 58/104, embeddings alone 69/104, hybrid 66/104.
Chosen hybrid settings: `{"input": "residual", "tauEmbed": 0.525, "tauHybrid": 0.525, "margin": 0, "trustRules": 1, "keepFuzzy": false, "override": 0.6}`. Embeddings-alone threshold: 0.525 on `residual` text. Grid size 1224.

## Cost of running it

- Download on first use: 53.1 MB (files listed in results.json), cached by the browser afterwards.
- Cold model load from localhost: 498 ms.
- Embedding one question, WASM: p50 4.9 ms, p95 8.2 ms (n=199).
- Hybrid ran the embedding on 61 of 200 gold questions (the rest were rules phrasing hits) and took the embedding's answer on 11.
- WebGPU: failed (Page.evaluate: Error: no available backend found. ERR: [webgpu] TypeError: je(...).webgpuInit is not a function
    at yT (http://127.0.0.1:8850/assets/ai/vendor/transformers.min.js:11:31033)
    at a).
- Origins requested: http://127.0.0.1:8850, blob://. Third-party origins: 0.

## Run history

The gold set was scored twice. The first run used a hybrid that always kept a rules phrasing hit; it scored 180/200 on gold and 64/104 on dev, below embeddings alone on dev (69/104). Prompted by that dev result, the `override` option (an embedding can replace a rules hit above a cosine) was added to the grid; the dev split picked override 0.6, which raised dev to 66/104 and lowered gold to 172/200. This page reports the second run, the one chosen by the stated protocol. Nothing was changed after seeing the second gold score.

## Python and browser parity

Cosine between the browser's q8 vector and sentence-transformers fp32 for the same text (n=40): min 0.9823, mean 0.9912. Stored int8 index vs fp32: min 0.9989.
