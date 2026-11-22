# results

| Folder | Contents | Made by |
| --- | --- | --- |
| `audit/` | Audit and cleaning report of the conference-version corpus | `scripts/audit_corpus.py`, `scripts/cleaning_report.py` |
| `probes/` | Count-only probes run before collecting: sources, neighbours, expansion; scope samples for hand checks | `scripts/probe_counts.py`, `src/corpus/*_probe.py`, `src/corpus/neighbour_select.py`, `src/corpus/class_list.py` |
| `collection/` | One report per collector: records looked at, kept, and left out with the reason | `src/corpus/*_collector.py` |
| `linking/` | Gazetteer counts, object-linking counts by layer, and the 200-link sample for the hand check | `src/corpus/gazetteer.py`, `src/corpus/link_objects.py` |
| `graph/` | Core graph statistics: nodes and edges by kind, type and relation, degrees, components, hubs, build counts | `src/graph/core_graph.py` |
| `queries/` | Query generator trial: model outputs, the author's blind ratings and the summary per model and language | `notebooks/query_generator_trial.ipynb`, `src/queries/generator_trial.py` |
| `retrieval/` | Index statistics, and TREC run files of each retrieval system on the dev queries | `src/retrieval/` |
| `evaluation_report.json` | Conference-version evaluation, superseded (see `legacy/`) | — |

Results of the benchmark will go in `paper_v1/`, each file recording its query count, date,
commit and configuration.
