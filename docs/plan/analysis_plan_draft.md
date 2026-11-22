# Analysis plan (draft for the author; not frozen)

- Status: **draft**. When the author approves it, it is copied unchanged to `docs/plan/analysis_plan.md`, dated
  and committed before any test-split run. The evaluation script refuses test-split runs until that file is
  committed.
- Drafted: 22 November 2026. Source of the rules: specification Sections 1, 6 and 10.
- Items marked **[author]** need the author's choice before freezing.

## 1. Questions and hypotheses

| RQ | Hypothesis tested | Primary comparison (test split) |
| --- | --- | --- |
| RQ1 | Graph evidence on the core Wikidata layer ranks better than text alone | PPR (core layer) vs BM25; PPR vs the best dense model; PPR vs entity-expanded BM25 (the control: knowing the entities without the structure) |
| RQ2 | Combining graph and text beats each alone | Best fusion or LambdaMART vs the best single text system |
| RQ3 | Graph evidence helps Hindi and Kannada queries find documents | On the Hindi and Kannada test queries only: PPR vs the best translate-then-search system |
| RQ4 | Path explanations are faithful | Not a significance test: share of explained results whose rank drops when the cited path is removed |

"Best dense model" and "best fusion" are chosen on the dev split, by NDCG@10, and named in this file before it is
frozen. **[author]**: confirm the three RQ1 comparisons and the single RQ2 and RQ3 comparisons as the primary family.

## 2. Queries and split

- 200 queries, 50 per type (simple keyword, entity, concept, complex natural language); 40 in Hindi or Kannada
  (20 each), as in the specification.
- Split 40 dev / 160 test, stratified by type and language (10 dev queries per type; 4 Hindi and 4 Kannada in
  dev), by a seeded shuffle recorded in the split file. The test split stays sealed until this plan is frozen.
- Queries with no document judged 2 or higher are left out and counted (decision 0021); the evaluation report
  lists them.

## 3. Measures

Computed by `src/benchmark/evaluate.py` with ir-measures (trec_eval's code); none hand-written.

- **Primary:** NDCG@10 with the judged grades 0-3 as gains.
- **Secondary:** P@5, MAP (over the 100 documents each run returns), Recall@100, reciprocal rank at 10; a document
  counts as relevant for these from grade 2.
- **Reported with every table:** the share of the top 10 that is judged, and the count of unjudged documents.
  Documents surfaced by later systems are judged too (re-pooling), so this count stays near zero.
- **Not yet decided [author]:** type coverage@10 and period or region match appear in the specification but no
  standard library computes them. Options: drop them, or define them in this plan and compute them with a small
  tested function whose definition is fixed here.

## 4. Statistics

- 95% percentile bootstrap intervals over queries, 10,000 resamples, seed 20261122.
- Paired two-sided randomization tests over queries on NDCG@10, 10,000 resamples, same seed.
- Holm's correction across the primary family (Section 1); alpha 0.05. Every other comparison is reported as
  descriptive, with its interval, and not tested.
- Results by query type and by language are descriptive (no tests), so the paper does not hunt for significant
  subgroups.

## 5. What may and may not be tuned

- Tuning (BM25 parameters, RM3, PPR damping, hub down-weighting, fusion k, the reranker depth) uses the dev split
  only; the untuned run is reported beside every tuned one.
- LambdaMART uses 5-fold cross-validation split by query on the test split, as in the specification; folds are
  fixed by seed and recorded.
- Nothing is changed after the first test-split run. Any later change is reported as a deviation, below.

## 6. Judging

- One LLM judge, fixed prompt, temperature 0 (decision 0022 **[author]**: the record still reads "waiting for the
  author"). The author's 15-query validation is reported with weighted kappa and raw agreement, overall, per
  language and per system.

## 7. Deviations

None yet. Every change after freezing is added here with its date and reason.
