#!/usr/bin/env bash
# One command that rebuilds every result from the saved raw responses and the committed author inputs
# (specification Section 10: "one command reproduces every number").
#
# Order: the corpus, graph and interface data (scripts/build_corpus.sh, replaying saved responses, so no requests);
# the coverage audit from the author's matches; the dev runs on the laptop; then, when the inputs exist, judging,
# evaluation and the reports. A step whose input is not there yet is skipped with the reason, never faked. Runs that
# need a GPU (query generation, dense encoding, translation, reranking, judging) come from the notebooks; their
# outputs are inputs here.
#
# Usage: bash scripts/reproduce.sh
set -euo pipefail
cd "$(dirname "$0")/.."

run() { echo "== $*"; uv run python -m "$@"; }
skip() { echo "-- skipped: $*"; }

bash scripts/build_corpus.sh
run src.graph.proximity_layer

# Coverage audit (decisions 0031, 0032): lists, then the rates from the author's matches.
run src.coverage_audit.sources
run src.coverage_audit.lists
if [ -f results/coverage_audit/match_sheet_v1.csv ]; then run src.coverage_audit.fill; else skip "coverage rates: no match sheet"; fi
filled() {  # true when the CSV's `match` column has any answer
  [ -f "$1" ] && uv run python -c "import csv,sys; sys.exit(0 if any(r['match'].strip() for r in csv.DictReader(open('$1', encoding='utf-8-sig'))) else 1)"
}
if filled results/coverage_audit/recheck_sheet_v1.csv; then
  run src.coverage_audit.recheck agreement
else
  skip "second-pass agreement: the second pass is not done"
fi
run src.corpus.data_card

# Queries and the dev runs (decisions 0021, 0023, 0026, 0027, 0033).
if [ -f data/queries/curation_v1.csv ]; then run src.queries.curation finalize; else skip "query split: not curated yet"; fi
if [ -f data/queries/dev_v1.tsv ]; then bash scripts/run_dev_runs.sh; else skip "dev runs: no dev queries"; fi

# Judging, evaluation, the tier analysis and the interim report (decisions 0022, 0031, 0037).
if [ -f results/judging/dev_judgements_v1.jsonl ]; then
  run src.benchmark.judging qrels --split dev
  labelled() { [ -f "$1" ] && uv run python -c "import csv,sys; sys.exit(0 if all(r['label'].strip() for r in csv.DictReader(open('$1', encoding='utf-8-sig'))) else 1)"; }
  if labelled data/judging/dev_pilot_sheet_v1.csv; then run src.benchmark.judging agreement --split dev; else skip "pilot agreement: the pilot sheet is not fully labelled"; fi
  runs=$(ls results/retrieval/runs/*_dev_v1.trec)
  # shellcheck disable=SC2086
  run src.benchmark.evaluate --name dev_v1 --split dev --qrels data/qrels/dev_v1.qrels --queries data/queries/dev_v1.tsv \
    --runs $runs --baseline bm25_dev_v1 --groups data/queries/dev_v1_groups.tsv
  # shellcheck disable=SC2086
  run src.benchmark.type_coverage --runs $runs
else
  skip "evaluation: the dev pool is not judged yet"
fi
run src.benchmark.interim
