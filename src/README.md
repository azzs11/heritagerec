# src

| Folder | Contents |
| --- | --- |
| `corpus/` | Corpus v1: seed selection, probes, entity lists, collectors, shared matching rules, gazetteer, object linking, snapshot and data card. Run modules with `uv run python -m src.corpus.<module>`; the order is in `scripts/build_corpus.sh` |
| `graph/` | Knowledge graph v1: the core Wikidata layer (decision 0020); later edge layers (decision 0006). Run with `uv run python -m src.graph.core_graph` |
| `explorer/` | Files the interface's atlas and graph views read (decision 0025): coordinates from the raw Wikidata responses, degrees, display hubs, communities. Run with `uv run python -m src.explorer.build` |
| `queries/` | Benchmark queries (decision 0021): the grid of information needs, the fixed generation prompts, and the generator trial's blind rating sheet and summary |
| `benchmark/` | Scores TREC runs against qrels with ir-measures: NDCG@10 and the secondary measures, bootstrap intervals, paired randomization tests with Holm's correction, results by group; refuses test-split runs until the analysis plan is committed. `uv run python -m src.benchmark.evaluate --help` |
| `graph_retrieval/` | Graph systems: personalised PageRank from linked entities over the core graph, hubs down-weighted (decisions 0007, 0027). `uv run python -m src.graph_retrieval.ppr --seeds Q466581` |
| `retrieval/` | Retrieval systems on corpus v1: the shared passage file and BM25 / BM25+RM3 over per-language Lucene indexes (decision 0023); dense baselines (two MiniLMs, multilingual-e5-large, BGE-M3), encoded on a GPU notebook (decision 0024) |
| `2_preprocessing/` … `7_evaluation/`, `fallback/` | Pipeline of the conference version (preprocessing, representation, knowledge graph, ranking, query system, evaluation), to be replaced by the corpus v1 systems |

The numbered folders are inherited; new code goes in folders with descriptive names.
