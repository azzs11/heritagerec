# results

| Folder | Contents | Made by |
| --- | --- | --- |
| `audit/` | Audit and cleaning report of the conference-version corpus | `scripts/audit_corpus.py`, `scripts/cleaning_report.py` |
| `probes/` | Count-only probes run before collecting: sources, neighbours, expansion; scope samples for hand checks | `scripts/probe_counts.py`, `src/corpus/*_probe.py`, `src/corpus/neighbour_select.py`, `src/corpus/class_list.py` |
| `collection/` | One report per collector: records looked at, kept, and left out with the reason | `src/corpus/*_collector.py` |
| `linking/` | Gazetteer counts, object-linking counts by layer, and the 200-link sample for the hand check | `src/corpus/gazetteer.py`, `src/corpus/link_objects.py` |
| `graph/` | Core graph statistics: nodes and edges by kind, type and relation, degrees, components, hubs, build counts | `src/graph/core_graph.py` |
| `explorer/` | `images_v1.json`: objects with an open image per museum, and why the others have none. Explorer data counts: coordinates placed and why not, display hubs and their threshold, communities, input and output checksums; Commons photographs kept, left out and by licence (`entity_images_v1.json`) | `src/explorer/build.py` |
| `queries/` | Query generator trial (outputs, blind ratings, summary); benchmark generation outputs (`generation_v1/`); provisional coverage tiers; the curation and split report (`split_v1`) | `notebooks/`, `src/queries/` |
| `coverage_audit/` | Coverage audit (decisions 0031, 0032): the official lists checked against their own totals (`lists_v1`), the seeded sample (`sample_v1`), the author's matching sheet with Wikidata candidates, the coverage rates from the matches (`coverage_v1`), and the blind second pass on 10% of them (`recheck_v1`) | `src/coverage_audit/` |
| `judging/` | Pool reports (runs, depth, checksums), the judge's labels with rationales, and the pilot agreement with the author | `src/benchmark/judging.py`, `notebooks/relevance_judge.ipynb` |
| `interim/` | The 30 Nov interim checkpoint report, labelled interim, assembled from the files above | `src/benchmark/interim.py` |
| `features/` | Settings, counts and input checksums of each graph-feature table | `src/graph_retrieval/features.py` |
| `benchmark/` | One folder per evaluation: `summary.json` and `.md` (means, intervals, tests, unjudged counts, inputs with checksums) and `per_query.tsv` | `src/benchmark/evaluate.py` |
| `retrieval/` | Index statistics, dense encoding reports (`dense_<model>_v1.json`: model revision, truncation counts, chunk checksums), and TREC run files of each retrieval system on the dev queries | `src/retrieval/` |
| `evaluation_report.json` | Conference-version evaluation, superseded (see `legacy/`) | — |

Results of the benchmark will go in `paper_v1/`, each file recording its query count, date,
commit and configuration.
