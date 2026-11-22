"""HTTP routes of the HeritageRec interface server (decisions 0012, 0025).

Every route reads the real corpus, graph and indexes. A route whose part is missing answers 503 with the reason
and the fix (see `server/components.py`); bad input answers 400, 404 or 422; nothing should answer 500, and the
fuzz tests in `tests/test_server.py` try to make it.

Run: uv run python -m server  (then open http://127.0.0.1:8000/docs for the route list)
"""

import hashlib
import json
import re
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query, Response
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

    def linked(text: str) -> dict:
        """The query's linked entities as cards, with the seed weights PageRank starts from (decisions 0026, 0027)."""
        g = optional("graph")
        if g is None:
            return {"mentions": [], "seeds": {}}
        from src.graph_retrieval.linker import link

        out = link(text)
        for m in out["mentions"]:
            m["candidates"] = [g.card(q) for q in m["candidates"] if q in g.nodes]
        out["seeds"] = {q: w for q, w in out["seeds"].items() if q in g.nodes}
        return out

    @app.get("/api/suggest")
    def suggest_route(q: Annotated[str, Query(max_length=500)]) -> list[dict]:
        g: Graph = need("graph")
        from src.graph_retrieval.linker import suggest

        return [dict(g.card(qid), closeness=score) for qid, score in suggest(clean_query(q)) if qid in g.nodes]

    @app.get("/api/link")
    def link_route(q: Annotated[str, Query(max_length=500)]) -> dict:
        need("graph")
        return linked(clean_query(q))

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
        # Built and running, but not yet measured: they need the dev queries and their judgements.
        if not isinstance(parts["graph"], Missing):
            out["graph_lens"] = {
                "status": "ok",
                "parts": "query linker (0026) and personalised PageRank (0027)",
                "evaluated": False,
            }
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

    @app.get("/api/documents/{doc_id:path}/download")
    def document_download(doc_id: str, format: Annotated[str, Query(pattern="^(txt|json)$")] = "txt") -> Response:
        """The record as a file, with its source, licence and attribution written in (CC BY-SA asks for it)."""
        corpus: Corpus = need("corpus")
        record = corpus.records.get(doc_id)
        if record is None:
            raise HTTPException(404, detail=f"{doc_id} is not in corpus v1")
        credit = attribution(record)
        stem = re.sub(r"[^A-Za-z0-9._-]+", "_", doc_id)[:80]
        if format == "json":
            body = json.dumps({"attribution": credit, "record": record}, ensure_ascii=False, indent=2) + "\n"
            media, name = "application/json", f"{stem}.json"
        else:
            head = "\n".join(f"{k}: {v}" for k, v in credit.items())
            body = f"{record['title']}\n\n{head}\n\n{'-' * 72}\n\n{record['text']}\n"
            media, name = "text/plain; charset=utf-8", f"{stem}.txt"
        return Response(
            body.encode("utf-8"),
            media_type=media,
            headers={"Content-Disposition": f'attachment; filename="{name}"'},
        )

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
        meta["get_it"] = sources_for(record, g.images.get(doc_id) if g else None)
        if g and doc_id in g.images:
            meta["image"] = g.images[doc_id]
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
        depth: Annotated[int, Query(ge=1, le=2)] = 1,
    ) -> dict:
        g: Graph = need("graph")

        def split(v: str | None) -> set[str] | None:
            return {x for x in v.split(",") if x} if v else None

        if depth == 2:
            return graph_views.ego2(g, node(g, node_id), budget, split(relations))
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
        from src.graph_retrieval.ppr import parse_seeds

        try:
            weighted = parse_seeds(seeds)
        except ValueError:
            raise HTTPException(400, detail="seeds are ids separated by ;, each optionally with :weight") from None
        chosen = list(weighted)
        unknown = [x for x in chosen if x not in g.nodes]
        if not chosen or unknown:
            raise HTTPException(400, detail=f"not nodes of the graph: {', '.join(unknown) or 'no seed given'}")
        if hub_power not in (0.0, 0.5, 1.0):
            raise HTTPException(400, detail="hub_power must be 0, 0.5 or 1 (decision 0027)")
        if any(w <= 0 or w != w for w in weighted.values()):
            raise HTTPException(400, detail="seed weights must be positive")
        return graph_rank_module.rank(g, paths, {q: weighted[q] for q in chosen[:10]}, k, restart, hub_power)

    @app.get("/api/graph/find")
    def graph_find(q: Annotated[str, Query(max_length=200)], limit: Annotated[int, Query(ge=1, le=100)] = 20) -> list:
        return graph_views.find(need("graph"), q, limit)

    @app.get("/api/collection")
    def collection(
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=60)] = 24,
    ) -> dict:
        """Museum objects with an open image, in a fixed shuffled order (by a hash of the id, so it is the same
        for everyone and every visit, and does not favour one museum or one collection batch)."""
        g: Graph = need("graph")
        order = sorted(g.images, key=lambda d: hashlib.sha1(d.encode()).hexdigest())
        corpus = optional("corpus")
        items = []
        for doc in order[offset : offset + limit]:
            card = g.card(doc) if doc in g.nodes else {"id": doc, "labels": {}, "image": g.images[doc]}
            if corpus and doc in corpus.records:
                r = corpus.records[doc]
                card["period"] = [r.get("period_start"), r.get("period_end")]
                card["source"] = r["source"]
            items.append(card)
        return {"total": len(order), "offset": offset, "items": items}

    # ---------- hexagons (decision 0030) ----------

    @app.get("/api/atlas/hexes")
    def atlas_hexes(res: Annotated[int, Query(ge=2, le=7)] = 4) -> list[dict]:
        return graph_views.hexes(need("graph"), res)

    @app.get("/api/atlas/rings")
    def atlas_rings(
        lat: Annotated[float, Query(ge=-90, le=90)],
        lon: Annotated[float, Query(ge=-180, le=180)],
        k: Annotated[int, Query(ge=0, le=graph_views.RING_MAX)] = 2,
    ) -> dict:
        return graph_views.rings(need("graph"), lat, lon, k)

    @app.get("/api/graph/rings/{doc_id:path}")
    def document_rings(doc_id: str, k: Annotated[int, Query(ge=0, le=graph_views.RING_MAX)] = 2) -> dict:
        g: Graph = need("graph")
        return graph_views.document_rings(g, node(g, doc_id), k)

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
            "entities": linked(text),
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
        g = optional("graph")
        for r in out["results"]:
            if g and r["doc_id"] in g.images:
                r["image"] = g.images[r["doc_id"]]
        out["query"], out["detected"] = text, detected
        out["linked"] = linked(text)
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


# How each source's text was made, so the attribution states the changes truthfully.
CHANGES = {
    "wikipedia": "plain-text extract from the TextExtracts API; the trailing reference and link sections removed "
    "(decision 0003)",
    "internet_archive": "the OCR text the Internet Archive publishes for the book, unchanged (decision 0016)",
    "met": "text joined by HeritageRec from the fields of the museum's open-access record (decision 0017)",
    "cleveland": "text joined by HeritageRec from the fields of the museum's open-access record (decision 0017)",
    "artic": "text joined by HeritageRec from the fields of the museum's open-access record (decision 0017)",
    "wellcome": "text joined by HeritageRec from the fields of the catalogue record (decision 0013)",
}


def attribution(record: dict) -> dict:
    """What a reuser must keep with the text: where it came from and under which licence."""
    authors = {
        "wikipedia": "Wikipedia contributors",
        "met": "The Metropolitan Museum of Art",
        "cleveland": "The Cleveland Museum of Art",
        "artic": "The Art Institute of Chicago",
        "wellcome": "Wellcome Collection",
        "internet_archive": "Internet Archive (digitised public-domain book)",
    }
    return {
        "source": authors.get(record["source"], record["source"]),
        "original": record["url"],
        "licence": record["licence"],
        "retrieved": record["fetched_at"][:10],
        "changes": CHANGES.get(record["source"], "text assembled by HeritageRec from the source's record"),
        "record id": record["id"],
        "checksum (sha256)": record["sha256"],
    }


def sources_for(record: dict, image: dict | None) -> list[dict]:
    """Where to get the original, by source: links only, nothing is fetched."""
    url, source = record["url"], record["source"]
    out = [{"label": "Original page", "url": url}]
    if source == "wikipedia" and "/wiki/" in url:
        site, title = url.split("/wiki/", 1)
        out.append({"label": "PDF from Wikipedia", "url": f"{site}/api/rest_v1/page/pdf/{title}"})
    if source == "internet_archive" and "/details/" in url:
        out.append(
            {"label": "Scans and files at the Internet Archive", "url": url.replace("/details/", "/download/", 1)}
        )
    if image:
        out.append({"label": "Full image (CC0)", "url": image["full"]})
    return out


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
