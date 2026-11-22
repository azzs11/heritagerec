"""HTTP routes of the HeritageRec interface server (decisions 0012, 0025).

Every route reads the real corpus, graph and indexes. A route whose part is missing answers 503 with the reason
and the fix (see `server/components.py`); bad input answers 400, 404 or 422; nothing should answer 500, and the
fuzz tests in `tests/test_server.py` try to make it.

Run: uv run python -m server  (then open http://127.0.0.1:8000/docs for the route list)
"""

import json
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from server import graph_rank as graph_rank_module
from server import graph_views, keyword
from server.components import LANGS, Corpus, Graph, Keyword, Missing, Paths, load
from src.retrieval.passages import passages

PAGE_MAX = 50
QUERY_MAX_CHARS = 500


def create_app(paths: Paths = Paths(), use_keyword: bool = True) -> FastAPI:
    parts = load(paths, keyword=use_keyword)
    app = FastAPI(title="HeritageRec", version="0.1", docs_url="/docs", redoc_url=None)
    # The web app's development server runs on another port; the release serves both from one origin.
    app.add_middleware(
        CORSMiddleware, allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"], allow_methods=["GET"]
    )
    app.state.parts = parts

    def need(name: str):
        part = parts[name]
        if isinstance(part, Missing):
            raise HTTPException(503, detail={"part": name, "reason": part.reason, "fix": part.fix})
        return part

    def optional(name: str):
        part = parts[name]
        return None if isinstance(part, Missing) else part

    def language(q: str, lang: str | None) -> tuple[str, dict]:
        detected = keyword.detect_language(q)
        if lang is None:
            return detected["language"], detected
        if lang not in LANGS:
            raise HTTPException(400, detail=f"language must be one of {', '.join(LANGS)}")
        return lang, detected

    def clean_query(q: str) -> str:
        text = keyword.safe_query(q)
        if not text:
            raise HTTPException(400, detail="the query is empty")
        if len(text) > QUERY_MAX_CHARS:
            raise HTTPException(400, detail=f"the query is longer than {QUERY_MAX_CHARS} characters")
        return text

    def searchable(kw: Keyword, text: str, lang: str) -> None:
        if not keyword.analyse(kw, text, lang):
            raise HTTPException(
                400, detail="no searchable words are left after analysis (only stop words, punctuation or symbols)"
            )

    def node(g: Graph, node_id: str) -> str:
        if node_id not in g.nodes:
            raise HTTPException(404, detail=f"{node_id} is not a node of the graph")
        return node_id

    # ---------- health and provenance ----------

    @app.get("/api/health")
    def health() -> dict:
        out = {}
        for name in ("corpus", "graph", "keyword"):
            out[name] = parts[name].status()
        out["planned"] = {k: {"status": "not built yet", "see": v} for k, v in parts["planned"].items()}
        return out

    @app.get("/api/corpus/stats")
    def corpus_stats() -> dict:
        """Counts from the snapshot manifest written by `src/corpus/build_snapshot.py` (in git, so always there)."""
        if not paths.manifest.exists():
            raise HTTPException(503, detail={"part": "manifest", "reason": "the snapshot manifest is missing"})
        m = json.loads(paths.manifest.read_text(encoding="utf-8"))
        return {
            "source_file": str(paths.manifest.relative_to(paths.root)),
            "built": m["built"],
            "commit": m["commit"],
            "snapshot": m["snapshot"],
            "by_source": m["records_by_source"],
            "by_language": m["records_by_language"],
            "by_doc_type": m["records_by_doc_type"],
            "duplicates_merged": m["duplicates_merged"],
        }

    @app.get("/api/ledger")
    def ledger() -> list[dict]:
        """Every result file: where a number on screen comes from, when it was built and at which commit."""
        rows = []
        for p in sorted(paths.results.rglob("*.json")):
            row = {"file": str(p.relative_to(paths.root)), "bytes": p.stat().st_size}
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                row["readable"] = False
                rows.append(row)
                continue
            if isinstance(data, dict):
                row.update({k: data[k] for k in ("built", "commit") if k in data and isinstance(data[k], str)})
            rows.append(row)
        return rows

    # ---------- documents ----------

    @app.get("/api/documents/{doc_id:path}/passages")
    def document_passages(
        doc_id: str, offset: Annotated[int, Query(ge=0)] = 0, limit: Annotated[int, Query(ge=1, le=PAGE_MAX)] = 10
    ) -> dict:
        corpus: Corpus = need("corpus")
        record = corpus.records.get(doc_id)
        if record is None:
            raise HTTPException(404, detail=f"{doc_id} is not in corpus v1")
        parts_ = passages(record)
        return {"doc_id": doc_id, "total": len(parts_), "offset": offset, "passages": parts_[offset : offset + limit]}

    @app.get("/api/documents/{doc_id:path}")
    def document(doc_id: str) -> dict:
        corpus: Corpus = need("corpus")
        record = corpus.records.get(doc_id)
        if record is None:
            raise HTTPException(404, detail=f"{doc_id} is not in corpus v1")
        g = optional("graph")
        meta = {k: v for k, v in record.items() if k != "text"}
        meta["words"] = len(record["text"].split())
        meta["passages"] = len(passages(record))
        meta["entities"] = [
            g.card(q) if g and q in g.nodes else {"id": q, "labels": {}} for q in record.get("entity_ids") or []
        ]
        meta["in_graph"] = bool(g and doc_id in g.nodes)
        return meta

    # ---------- graph ----------

    @app.get("/api/graph/overview")
    def graph_overview(min_size: Annotated[int, Query(ge=2, le=1000)] = 10) -> dict:
        return graph_views.overview(need("graph"), min_size)

    @app.get("/api/graph/node/{node_id:path}")
    def graph_node(node_id: str) -> dict:
        g: Graph = need("graph")
        return g.card(node(g, node_id))

    @app.get("/api/graph/ego/{node_id:path}")
    def graph_ego(
        node_id: str,
        budget: Annotated[int, Query(ge=2, le=graph_views.MAX_BUDGET)] = graph_views.DEFAULT_BUDGET,
        relations: str | None = None,
        layers: str | None = None,
        kinds: str | None = None,
    ) -> dict:
        g: Graph = need("graph")

        def split(v: str | None) -> set[str] | None:
            return {x for x in v.split(",") if x} if v else None

        return graph_views.ego(g, node(g, node_id), budget, split(relations), split(layers), split(kinds))

    @app.get("/api/graph/path")
    def graph_path(
        source: str,
        target: str,
        max_len: Annotated[int, Query(ge=1, le=6)] = 4,
        k: Annotated[int, Query(ge=1, le=10)] = 3,
    ) -> dict:
        g: Graph = need("graph")
        return graph_views.path(g, node(g, source), node(g, target), max_len, k)

    @app.get("/api/graph/rank")
    def graph_rank(
        seeds: Annotated[str, Query(max_length=2000, description="entity ids separated by ;")],
        k: Annotated[int, Query(ge=1, le=100)] = 10,
        restart: Annotated[float, Query(gt=0, lt=1)] = 0.15,
        hub_power: Annotated[float, Query(ge=0, le=1)] = 1.0,
    ) -> dict:
        g: Graph = need("graph")
        chosen = list(dict.fromkeys(x.strip() for x in seeds.split(";") if x.strip()))
        unknown = [x for x in chosen if x not in g.nodes]
        if not chosen or unknown:
            raise HTTPException(400, detail=f"not nodes of the graph: {', '.join(unknown) or 'no seed given'}")
        if hub_power not in (0.0, 0.5, 1.0):
            raise HTTPException(400, detail="hub_power must be 0, 0.5 or 1 (decision 0027)")
        return graph_rank_module.rank(g, paths, chosen[:10], k, restart, hub_power)

    @app.get("/api/graph/find")
    def graph_find(q: Annotated[str, Query(max_length=200)], limit: Annotated[int, Query(ge=1, le=100)] = 20) -> list:
        return graph_views.find(need("graph"), q, limit)

    # ---------- atlas ----------

    @app.get("/api/atlas/places")
    def atlas_places() -> list[dict]:
        return graph_views.places(need("graph"))

    @app.get("/api/atlas/near")
    def atlas_near(
        lat: Annotated[float, Query(ge=-90, le=90)],
        lon: Annotated[float, Query(ge=-180, le=180)],
        k: Annotated[int, Query(ge=1, le=graph_views.NEAR_MAX)] = graph_views.NEAR_DEFAULT,
    ) -> dict:
        return graph_views.near(need("graph"), lat, lon, k)

    # ---------- search ----------

    @app.get("/api/analyse")
    def analyse(q: str, lang: str | None = None) -> dict:
        kw: Keyword = need("keyword")
        text = clean_query(q)
        chosen, detected = language(text, lang)
        return {
            "query": text,
            "language": chosen,
            "detected": detected,
            "tokens": keyword.analyse(kw, text, chosen),
            "entities": {"status": "not built yet", "see": parts["planned"]["query_linker"]},
        }

    @app.get("/api/search")
    def search(
        q: str,
        lang: str | None = None,
        system: str = "bm25",
        k: Annotated[int, Query(ge=1, le=100)] = 10,
    ) -> dict:
        if system not in ("bm25", "bm25_rm3"):
            planned = parts["planned"].get(system.split("_")[0])
            if planned:
                raise HTTPException(503, detail={"part": system, "reason": "not built yet", "fix": planned})
            raise HTTPException(400, detail="system must be bm25 or bm25_rm3")
        kw: Keyword = need("keyword")
        text = clean_query(q)
        chosen, detected = language(text, lang)
        searchable(kw, text, chosen)
        out = keyword.search(kw, optional("corpus"), text, chosen, system == "bm25_rm3", k)
        out["query"], out["detected"] = text, detected
        return out

    @app.get("/api/explain")
    def explain(q: str, doc: str, lang: str | None = None, system: str = "bm25") -> dict:
        if system not in ("bm25", "bm25_rm3"):
            raise HTTPException(400, detail="system must be bm25 or bm25_rm3")
        kw: Keyword = need("keyword")
        text = clean_query(q)
        chosen, _ = language(text, lang)
        searchable(kw, text, chosen)
        corpus = optional("corpus")
        if corpus is not None and doc not in corpus.records:
            raise HTTPException(404, detail=f"{doc} is not in corpus v1")
        return keyword.explain(kw, optional("corpus"), text, chosen, doc, system == "bm25_rm3")

    return app


def main() -> None:
    import argparse

    import uvicorn

    parser = argparse.ArgumentParser(description="Run the HeritageRec interface server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-keyword", action="store_true", help="start without Java and the BM25 indexes")
    args = parser.parse_args()
    uvicorn.run(create_app(use_keyword=not args.no_keyword), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
