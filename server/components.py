"""The parts the server is made of, each loaded on its own so that one missing part never takes the rest down.

A part that cannot load is kept as a `Missing` with the reason and the command that fixes it; the endpoints that
need it answer 503 with that text, and `/api/health` lists every part. The interface shows the same text, so a
reader always learns what is absent and why, instead of seeing an empty page.
"""

import gzip
import json
import os
import threading
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from src.corpus.wikimedia import ROOT
from src.graph.core_graph import RELATIONS

LANGS = ("en", "hi", "kn")
RELATION_LABELS = {**RELATIONS, "about": "document is about", "in_period": "in the century"}


@dataclass(frozen=True)
class Paths:
    """Every file the server reads; tests point these elsewhere to start the server with parts missing."""

    root: Path = ROOT
    records: Path = ROOT / "data/corpus_v1/records.jsonl.gz"
    manifest: Path = ROOT / "data/corpus_v1/manifest.json"
    nodes: Path = ROOT / "data/graph/core_v1/nodes.jsonl.gz"
    edges: Path = ROOT / "data/graph/core_v1/edges.tsv.gz"
    explorer_nodes: Path = ROOT / "data/explorer/v1/nodes.jsonl.gz"
    communities: Path = ROOT / "data/explorer/v1/communities.json.gz"
    indexes: Path = ROOT / "data/indexes/bm25_v1"
    results: Path = ROOT / "results"


@dataclass
class Missing:
    name: str
    reason: str
    fix: str

    def status(self) -> dict:
        return {"status": "missing", "reason": self.reason, "fix": self.fix}


class Corpus:
    """Corpus v1 records in memory (about 330 MB), by id."""

    def __init__(self, paths: Paths):
        if not paths.records.exists():
            raise FileNotFoundError(paths.records)
        self.records: dict[str, dict] = {}
        for line in gzip.open(paths.records, "rt", encoding="utf-8"):
            r = json.loads(line)
            self.records[r["id"]] = r

    def status(self) -> dict:
        return {"status": "ok", "records": len(self.records)}


@dataclass
class Edge:
    other: str
    relation: str
    direction: str  # "out" when this node is the statement's subject
    layer: str
    revision: str


@dataclass
class Graph:
    """The core graph with the explorer's degrees, display hubs, communities and coordinates joined on."""

    nodes: dict[str, dict] = field(default_factory=dict)
    adjacency: dict[str, list[Edge]] = field(default_factory=lambda: defaultdict(list))
    meta: dict[str, dict] = field(default_factory=dict)
    communities: dict = field(default_factory=dict)
    documents_about: Counter = field(default_factory=Counter)

    @classmethod
    def load(cls, paths: Paths) -> "Graph":
        for p in (paths.nodes, paths.edges, paths.explorer_nodes, paths.communities):
            if not p.exists():
                raise FileNotFoundError(p)
        g = cls()
        for line in gzip.open(paths.nodes, "rt", encoding="utf-8"):
            n = json.loads(line)
            g.nodes[n["id"]] = n
        with gzip.open(paths.edges, "rt", encoding="utf-8") as f:
            next(f)  # header
            for line in f:
                s, r, t, layer, _origin, rev = line.rstrip("\n").split("\t")
                g.adjacency[s].append(Edge(t, r, "out", layer, rev))
                g.adjacency[t].append(Edge(s, r, "in", layer, rev))
                if r == "about":
                    g.documents_about[t] += 1
        for line in gzip.open(paths.explorer_nodes, "rt", encoding="utf-8"):
            m = json.loads(line)
            g.meta[m["id"]] = m
        g.communities = json.loads(gzip.open(paths.communities, "rt", encoding="utf-8").read())
        # Neighbour lists in a fixed order, so every view of the same node is the same.
        for edges in g.adjacency.values():
            edges.sort(key=lambda e: (e.relation, e.direction, e.other))
        return g

    def label(self, node_id: str) -> dict:
        return self.nodes.get(node_id, {}).get("labels") or {}

    def card(self, node_id: str) -> dict:
        """What the interface draws for a node."""
        n, m = self.nodes[node_id], self.meta.get(node_id, {})
        out = {
            "id": node_id,
            "kind": n["kind"],
            "type": n.get("type"),
            "labels": n.get("labels") or {},
            "degree": m.get("degree", 0),
            "hub": m.get("hub", False),
            "community": m.get("community"),
            "documents": self.documents_about.get(node_id, 0),
        }
        if "lat" in m:
            out["lat"], out["lon"] = m["lat"], m["lon"]
        return out

    def status(self) -> dict:
        return {
            "status": "ok",
            "nodes": len(self.nodes),
            "edges": sum(len(e) for e in self.adjacency.values()) // 2,
            "placed": sum(1 for m in self.meta.values() if "lat" in m),
        }


class Keyword:
    """BM25 and BM25+RM3 over the per-language Lucene indexes, with the settings of `src/retrieval/bm25.py`.

    Lucene runs inside one Java virtual machine reached through pyjnius; calls are serialised with a lock,
    because the searchers are not safe to share between threads.
    """

    def __init__(self, paths: Paths):
        from dotenv import load_dotenv

        load_dotenv(paths.root / ".env")
        if not os.environ.get("JAVA_HOME"):
            raise RuntimeError("JAVA_HOME is not set")
        for lang in LANGS:
            if not (paths.indexes / lang).exists():
                raise FileNotFoundError(paths.indexes / lang)
        from pyserini.analysis import Analyzer, get_lucene_analyzer
        from pyserini.index.lucene import LuceneIndexReader
        from pyserini.search.lucene import LuceneSearcher

        from src.retrieval.bm25 import BM25, QUERY_ANALYZER, RM3

        self.lock = threading.Lock()
        self.bm25, self.rm3 = BM25, RM3
        self.searchers, self.expanders, self.readers, self.analyzers = {}, {}, {}, {}
        for lang in LANGS:
            path = str(paths.indexes / lang)
            lucene_analyzer = get_lucene_analyzer(**QUERY_ANALYZER[lang])
            plain = LuceneSearcher(path)
            plain.set_analyzer(lucene_analyzer)
            plain.set_bm25(**BM25)
            expanded = LuceneSearcher(path)
            expanded.set_analyzer(lucene_analyzer)
            expanded.set_bm25(**BM25)
            expanded.set_rm3(**RM3)
            self.searchers[lang], self.expanders[lang] = plain, expanded
            self.readers[lang] = LuceneIndexReader(path)
            self.analyzers[lang] = Analyzer(lucene_analyzer)

    def status(self) -> dict:
        return {"status": "ok", "languages": list(LANGS), "bm25": self.bm25, "rm3": self.rm3}


def load(paths: Paths, keyword: bool = True) -> dict:
    """Every part, loaded or replaced by a `Missing` that says why and how to fix it."""
    parts: dict = {}
    try:
        parts["corpus"] = Corpus(paths)
    except FileNotFoundError:
        parts["corpus"] = Missing(
            "corpus",
            f"{paths.records.relative_to(paths.root)} is not on this machine (it is not kept in git)",
            "uv run python -m src.corpus.build_snapshot (needs the raw responses), or download the snapshot at release",
        )
    try:
        parts["graph"] = Graph.load(paths)
    except FileNotFoundError as e:
        parts["graph"] = Missing(
            "graph", f"{Path(e.args[0]).name} is missing", "uv run python -m src.explorer.build (after the core graph)"
        )
    if not keyword:
        parts["keyword"] = Missing(
            "keyword", "keyword search was switched off for this run", "start without --no-keyword"
        )
    else:
        try:
            parts["keyword"] = Keyword(paths)
        except RuntimeError:
            parts["keyword"] = Missing(
                "keyword",
                "Java is not configured",
                "install a Java 21 JDK and set JAVA_HOME in .env (see .env.example)",
            )
        except FileNotFoundError as e:
            parts["keyword"] = Missing(
                "keyword",
                f"the BM25 index {Path(e.args[0]).name} is missing",
                "uv run python -m src.retrieval.bm25 index",
            )
    # Systems that are planned but not built: named so the interface can say so, with their decision record.
    parts["planned"] = {
        "query_linker": "decision 0025; the linker and its evaluation come in phase 1, week 7",
        "dense": "decision 0024; runs arrive from the Kaggle notebook",
        "ppr": "decisions 0007 and 0008",
        "fusion": "decision 0008",
        "reranker": "decision 0008",
        "lambdamart": "decision 0008",
        "recommender": "decision 0009",
    }
    return parts
