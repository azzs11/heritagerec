#!/usr/bin/env bash
# The dev-split runs that run on the laptop: BM25, BM25+RM3 and Personalised PageRank (decisions 0023, 0026, 0027).
#
# Needs data/queries/dev_v1.tsv (written by `src.queries.curation finalize`) and the BM25 indexes
# (`src.retrieval.bm25 index`). The dense runs come from notebooks/dense_baselines.ipynb on Kaggle. PageRank runs at
# the three hub powers of decision 0027 (1 is the default; 0.5 and 0 are reported beside it, chosen on dev only).
# Never point this at test queries before docs/plan/analysis_plan.md is committed.
#
# Usage: bash scripts/run_dev_runs.sh
set -euo pipefail
cd "$(dirname "$0")/.."

QUERIES=data/queries/dev_v1.tsv
run() { echo "== $*"; uv run python -m "$@"; }

run src.retrieval.bm25 search --queries "$QUERIES"
run src.retrieval.bm25 search --queries "$QUERIES" --rm3
run src.graph_retrieval.query_seeds --queries "$QUERIES"
run src.graph_retrieval.ppr --queries data/queries/dev_v1_seeds.tsv --name ppr_dev_v1 --hub-power 1
run src.graph_retrieval.ppr --queries data/queries/dev_v1_seeds.tsv --name ppr_hub05_dev_v1 --hub-power 0.5
run src.graph_retrieval.ppr --queries data/queries/dev_v1_seeds.tsv --name ppr_hub0_dev_v1 --hub-power 0
# The entity-expanded BM25 control (decision 0033), at the three weights chosen among on dev.
for alpha in 0.25 0.5 1.0; do
  run src.retrieval.entity_bm25 --queries "$QUERIES" --alpha "$alpha"
done

# The translate-then-search control (decision 0019): once the Hindi and Kannada dev queries are translated
# (`src.queries.translate runs`), BM25 and BM25+RM3 search the English index with them.
TRANSLATED=data/queries/translate_dev_v1.tsv
if [ -f "$TRANSLATED" ]; then
  run src.retrieval.bm25 search --queries "$TRANSLATED"
  run src.retrieval.bm25 search --queries "$TRANSLATED" --rm3
fi

# Stage 2 and the inputs of stages 3 and 4, once the dense runs are back from Kaggle (notebooks/dense_baselines.ipynb):
# reciprocal rank fusion of the text, dense and graph lists (decision 0008), the graph features of the fused top 100
# (decision 0036), and the reranker's candidate list for notebooks/reranker.ipynb. LambdaMART (decision 0037) runs
# after judging: it needs the qrels.
RUNS=results/retrieval/runs
if [ -f "$RUNS/bge_m3_all_dev_v1.trec" ]; then
  run src.retrieval.fusion --name rrf_dev_v1 --runs "$RUNS/bm25_dev_v1.trec" "$RUNS/bge_m3_all_dev_v1.trec" "$RUNS/ppr_dev_v1.trec"
  run src.graph_retrieval.features --seeds data/queries/dev_v1_seeds.tsv --candidates "$RUNS/rrf_dev_v1.trec" --name dev
  run src.retrieval.rerank prepare --candidates "$RUNS/rrf_dev_v1.trec" --split dev
else
  echo "== dense runs not back yet: fusion, graph features and the reranker's candidates wait for them"
fi
