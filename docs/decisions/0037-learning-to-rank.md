# 0037: Learning to rank: LambdaMART on the fused candidates, fixed settings, exact SHAP

- Status: decided under the author's delegation (24 Nov 2026); the author may overrule before any test run
- Date: 2026-11-24

## Context

Decision 0008 fixes the fourth stage: LightGBM LambdaMART, 5-fold cross-validation split by query, over text, graph
and query-match features, with SHAP showing which signals carry the ranking (RQ2). With 160 test queries (40 on dev),
there are few queries to learn from, so how the model is trained matters as much as which model it is.

Comparable work: LambdaMART (Burges, 2010) remains the standard feature-based ranker in IR benchmarks (the LETOR and
MSLR-WEB30K baselines); LightGBM's implementation is the one most papers report. TreeSHAP (Lundberg et al., Nature
Machine Intelligence 2020) gives exact SHAP values for tree models, built into LightGBM (`pred_contrib`).

## Options considered

| Choice | Options | Decision and why |
| --- | --- | --- |
| Library | A. LightGBM `lambdarank`; B. XGBoost `rank:ndcg`; C. a neural ranker (allRank) | A: the specification's choice and the field's reference implementation; a neural ranker needs far more queries than 160 |
| Candidates | A. every document any run returned; B. the fused run's top 100 (reciprocal rank fusion, 0008) | B: the stage reranks what fusion hands it, as the pipeline says; Recall@100 of fusion bounds it and is reported |
| Settings | A. tuned per fold by inner cross-validation; B. fixed, stated in advance | B: with 32-128 training queries per fold, tuning mostly fits noise. Fixed: 300 trees, learning rate 0.05, 15 leaves, at least 10 pairs per leaf, 80% of features per tree, labels 0-3 as gains 2^l - 1, NDCG truncation 20, seed 20261124, deterministic mode |
| Missing scores | A. fill with 0; B. leave missing (LightGBM learns a direction for missing values) | B: "this system did not return the document" is information; 0 would be a fake score |
| Run features | Per run: its score scaled 0-1 within the query, and 1 / rank (0 when absent) | Raw scores differ in scale between queries; both forms are standard |
| Unjudged candidates | Grade 0 for training | Standard; the share of unjudged candidates is reported, and re-pooling (specification Section 9) keeps it low |
| Folds | 5 folds by query, seeded, the same folds for every variant | Variants (the ablation) are then compared on identical splits |
| Importance | Mean absolute SHAP value per feature and per group (text, graph, query match), on out-of-fold predictions | Out-of-fold, so the importance is of the model as it ranks unseen queries |
| Ablation | Retrain without one group at a time, same folds; report the NDCG@10 drop | The specification's ablation table (RQ2) |

## Consequences

- `src/retrieval/ltr.py`: assembles the feature table from the runs, the graph features (0036), the documents'
  length and language, and the qrels; trains out of fold; writes `ltr_<split>_v1.trec` (and `ltr_no<group>_...` for
  the ablation) and a report with the settings, the folds, SHAP importance and the unjudged share.
- LightGBM needs OpenMP on macOS (`brew install libomp`); Linux, CI and Kaggle need nothing extra.
- Query-match features that need the query analysis of specification Section 5 (period and region cues, the query's
  intended document type) are added when that analysis exists; language match and document length are in now.
