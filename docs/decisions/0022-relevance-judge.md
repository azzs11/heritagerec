# 0022: Which LLM judges relevance

- Status: proposed (options for the author; nothing run yet)
- Date: 2026-11-21

## Context

The benchmark rules (specification Section 9) fix how relevance is judged: one LLM judge with a fixed
UMBRELA-style prompt, a 0–3 scale (3 directly about the query, 2 clearly related, 1 loosely related, 0 not
relevant), temperature 0, seeing only the query, title and text. The judge must not be a model used inside any
compared system, and must come from a different model family from the query generator (decision 0021). A free
open-weight multilingual model is tried first; a paid API is used only if weighted kappa with the author's labels
is below about 0.4, and then both runs are reported.

The judge reads queries and documents in English, Hindi and Kannada. A rough count of the work: the 30 Nov
interim needs the dev pools (40 queries, five baselines, top 10 each), and the full benchmark later needs the test
pools of every system plus re-pooling. Both counts are measured when the pools exist, not estimated here.

What the literature reports, so expectations are set before any run:

- UMBRELA (Upadhyay et al., 2024) reproduces Bing's LLM assessor with an open prompt; agreement with TREC
  assessors is fair at the label level, and system rankings correlate well.
- "Does UMBRELA work on other LLMs?" (Farzi et al., SIGIR-ICTIR 2025) ran UMBRELA on other LLMs: system-ranking correlations stay stable across
  models, per-label agreement varies more.
- A CIKM 2025 case study found open-weight 70B judges (Llama-3.1-70B, Qwen-2.5-72B) weak as a replacement
  for manual judging, with median per-topic kappa about 0.37 and 0.27.
- A 2026 study of backbone versions found no consistent gain from newer versions of the same family.

So a kappa near or below 0.4 is a real possibility, and the paid-API fallback in the rules may be needed.

## Options considered

All candidates below have Apache-2.0 licences (to be confirmed on each model card before use). Models with
NonCommercial licences (for example Cohere's Aya Expanse, CC BY-NC) are left out under the licence rule.

| Option | Size | Languages | Free hardware | For | Against |
| --- | --- | --- | --- | --- | --- |
| A. Gemma 4 31B (Google, April 2026) | 31B dense | Broad multilingual | Kaggle (2 × T4) in 4-bit; too large for one Colab T4 | Strongest dense candidate that runs free | Slow; Kaggle's weekly GPU quota |
| B. Gemma 4 26B-A4B | 26B mixture of experts, about 4B active | Broad multilingual | Kaggle; tight on one Colab T4 | Fast for its size | Unclear on Colab memory |
| C. Qwen3-14B (Alibaba) | 14B dense | About 119 languages | One Colab T4 in 4-bit | Easiest to run; well-tested as a judge family | Qwen judges were weakest in the CIKM 2025 study (an older version) |
| D. Sarvam-30B (Sarvam AI, 2026) | 30B | Built for Indian languages | Kaggle, to check | Likely best Hindi and Kannada reading | Newer, little evidence as a relevance judge |
| E. Paid API model | — | Strong | — | Highest agreement in most studies | Costs money; allowed only as the fallback in the rules |

## Proposed method of choice

1. **Shortlist two or three** of A–D, leaving out the generator's family.
2. **Pilot on dev only.** About 100 (query, document) pairs drawn from the dev pools once the baselines have
   run, stratified by language and by baseline rank. The author labels them on the same 0–3 scale, blind to
   systems and to any LLM label. The test set stays sealed, and these pilot labels are separate from the
   15-query validation on test.
3. **Each shortlisted model labels the same pairs** with the fixed prompt, saving model name, revision, prompt,
   date, and every label with its rationale.
4. **Choose by weighted kappa** (scikit-learn `cohen_kappa_score`, linear weights) with the author's labels,
   overall and per language, and report raw agreement too. Below about 0.4 for every candidate, the paid-API
   fallback runs as the rules say.

## Decision

Waiting for the author.
