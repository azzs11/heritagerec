# server

The HeritageRec interface server (decisions 0012, 0025): FastAPI over corpus v1, the core graph, the explorer
files and the BM25 indexes. The web app in `web/` reads only these routes; every number it shows comes from them
or from a result file listed by `/api/ledger`.

Run it from the repository root:

    uv run python -m server               # http://127.0.0.1:8000, route list at /docs
    uv run python -m server --no-keyword  # without Java and the BM25 indexes

| File | What it holds |
| --- | --- |
| `components.py` | Loads each part on its own (corpus, graph with explorer data, keyword search); a part that cannot load is kept with the reason and the fix |
| `graph_views.py` | Overview of communities, ego views under a node budget with bundles, paths that avoid hubs first, nearest places for the atlas, label search |
| `keyword.py` | BM25 and BM25+RM3 search; the explanation by term, with a check that the terms add up to Lucene's score |
| `app.py` | The routes |

| Route | Answers |
| --- | --- |
| `/api/health` | Every part: loaded, missing (with reason and fix), or not built yet (with its decision record) |
| `/api/corpus/stats` | Counts from the snapshot manifest |
| `/api/ledger` | Every result file with its build date and commit |
| `/api/documents/{id}`, `/api/documents/{id}/passages` | A record's metadata, linked entities and passages |
| `/api/graph/overview`, `/api/graph/ego/{id}`, `/api/graph/path`, `/api/graph/find`, `/api/graph/node/{id}` | Graph views |
| `/api/atlas/places`, `/api/atlas/near` | Placed entities; the nearest places to a point and how the graph ties them |
| `/api/analyse`, `/api/search`, `/api/explain` | Query analysis, keyword search, and the stage-by-stage explanation |

What it needs, and what happens without it:

| Part | Needs | Without it |
| --- | --- | --- |
| Graph | `data/graph/core_v1/`, `data/explorer/v1/` (in git) | Graph and atlas routes answer 503 |
| Corpus | `data/corpus_v1/records.jsonl.gz` (not in git; rebuilt or downloaded) | Document routes answer 503; search still works but shows no titles or snippets |
| Keyword search | Java 21 with `JAVA_HOME` in `.env`, and `data/indexes/bm25_v1/` | Search routes answer 503 with the fix |

Tests: `uv run --group dev pytest tests/test_server.py` (graph views, degraded starts, explanation checks on the
real indexes when present, and fuzzing that fails on any 500).
