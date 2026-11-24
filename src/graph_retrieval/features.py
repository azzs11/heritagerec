"""Graph features of (query, document) pairs, for learning to rank (decision 0036).

For each query, its seed entities (the linker's, as the graph lens uses) and each candidate document:

- `overlap`: how many of the document's entities are seed entities;
- `horn`: Horn's index between the neighbour counts of the document's entities and of the seeds;
- `mp_<family>` for place, site, style, tradition, dynasty, period: the nodes the document's entities and the seeds
  both reach in one step of that family's relations, each counted 1 / log(1 + degree), so sharing a hub counts little;
- `simrank`: the candidate's highest SimRank to any seed document, exact on the query's own subgraph (C = 0.8, five
  iterations): candidates, up to 25 documents about the seeds, their entities, and the non-hub nodes that join two
  or more of those.

A query with no seed entity gets zeros. Hubs are the explorer's display hubs (decision 0025).

Usage:
    uv run python -m src.graph_retrieval.features --seeds data/queries/dev_v1_seeds.tsv \
        --candidates results/retrieval/runs/rrf_dev_v1.trec --name dev
Output:
    data/features/<name>_graph_v1.tsv     query id, document id, then one column per feature
    results/features/<name>_graph_v1.json settings, counts, input checksums
"""

import argparse
import csv
import gzip
import hashlib
import json
import math
import subprocess
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from src.corpus.wikimedia import ROOT
from src.graph_retrieval.ppr import parse_seeds

EDGES = ROOT / "data/graph/core_v1/edges.tsv.gz"
NODES = ROOT / "data/graph/core_v1/nodes.jsonl.gz"
EXPLORER = ROOT / "data/explorer/v1/nodes.jsonl.gz"
DEPTH = 100
SIMRANK_C = 0.8
SIMRANK_ITERATIONS = 5
SEED_DOCUMENTS = 25

FAMILIES = {
    "place": {"P131", "P276"},
    "site": {"P361", "P527"},
    "style": {"P149", "P135"},
    "tradition": {"P136"},
    "dynasty": {"P53", "P88", "P112", "P170", "P84", "P36", "P1365", "P1366"},
    "period": {"in_period"},
}
COLUMNS = ["overlap", "horn", *[f"mp_{f}" for f in FAMILIES], "simrank"]


class GraphIndex:
    def __init__(self, edges: list[tuple[str, str, str]], documents: set[str], hubs: set[str]):
        self.adj: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for s, r, t in edges:
            if s != t:
                self.adj[s].append((t, r))
                self.adj[t].append((s, r))
        self.degree = {n: len(v) for n, v in self.adj.items()}
        self.documents = documents
        self.hubs = hubs

    @classmethod
    def load(cls) -> "GraphIndex":
        with gzip.open(EDGES, "rt", encoding="utf-8") as f:
            next(f)
            edges = [tuple(line.split("\t")[:3]) for line in f]
        docs = {json.loads(line)["id"] for line in gzip.open(NODES, "rt", encoding="utf-8") if '"document"' in line}
        hubs = {m["id"] for m in map(json.loads, gzip.open(EXPLORER, "rt", encoding="utf-8")) if m.get("hub")}
        return cls(edges, docs, hubs)

    def about(self, doc: str) -> set[str]:
        return {o for o, r in self.adj.get(doc, []) if r == "about" and o not in self.documents}

    def reach(self, node: str, relations: set[str]) -> set[str]:
        return {o for o, r in self.adj.get(node, []) if r in relations}

    def weight(self, node: str) -> float:
        return 1.0 / math.log(1 + max(self.degree.get(node, 1), 1))


def horn(x: Counter, y: Counter) -> float:
    """Horn's (1966) overlap index of two abundance distributions: 1 when proportional, 0 when disjoint."""
    if not x or not y:
        return 0.0
    xlogx = lambda v: v * math.log(v) if v > 0 else 0.0  # noqa: E731
    sx, sy = sum(x.values()), sum(y.values())
    keys = set(x) | set(y)
    top = sum(xlogx(x[k] + y[k]) for k in keys) - sum(xlogx(v) for v in x.values()) - sum(xlogx(v) for v in y.values())
    bottom = xlogx(sx + sy) - xlogx(sx) - xlogx(sy)
    return top / bottom if bottom > 0 else 0.0


def pair_features(g: GraphIndex, doc: str, seeds: set[str]) -> dict[str, float]:
    ents = g.about(doc)
    out = {"overlap": float(len(ents & seeds))}
    # Horn's index over the entities' neighbours (every relation but "about"), as counts.
    near = lambda nodes: Counter(o for n in nodes for o, r in g.adj.get(n, []) if r != "about")  # noqa: E731
    out["horn"] = horn(near(ents), near(seeds))
    direct = ents & seeds
    for family, relations in FAMILIES.items():
        a = set(ents).union(*[g.reach(e, relations) for e in ents]) if ents else set()
        b = set(seeds).union(*[g.reach(s, relations) for s in seeds]) if seeds else set()
        # Shared through the family, not the direct overlap already counted above.
        out[f"mp_{family}"] = sum(g.weight(n) for n in (a & b) - direct)
    return out


def seed_documents(g: GraphIndex, seeds: set[str], limit: int = SEED_DOCUMENTS) -> list[str]:
    """Documents about the seeds, the most specific first (fewest entities), then by id."""
    docs = {o for s in seeds for o, r in g.adj.get(s, []) if r == "about" and o in g.documents}
    return sorted(docs, key=lambda d: (len(g.about(d)), d))[:limit]


def simrank(g: GraphIndex, candidates: list[str], seeds: set[str]) -> dict[str, float]:
    """Each candidate's highest SimRank to a seed document, on the query's subgraph (decision 0036)."""
    anchors = seed_documents(g, seeds)
    if not anchors or not candidates:
        return dict.fromkeys(candidates, 0.0)
    core = set(candidates) | set(anchors)
    core |= {e for d in list(core) for e in g.about(d)}
    # Bridges: non-hub nodes next to two or more core nodes; a node touching one core node joins nothing.
    touch = Counter(o for n in core for o, _ in g.adj.get(n, []) if o not in core and o not in g.hubs)
    nodes = sorted(core | {n for n, k in touch.items() if k >= 2})
    index = {n: i for i, n in enumerate(nodes)}
    a = np.zeros((len(nodes), len(nodes)))
    for n in nodes:
        for o, _ in g.adj.get(n, []):
            if o in index:
                a[index[n], index[o]] = 1.0
    deg = a.sum(axis=0)
    w = np.divide(a, deg, out=np.zeros_like(a), where=deg > 0)  # column-normalised
    s = np.eye(len(nodes))
    for _ in range(SIMRANK_ITERATIONS):
        s = SIMRANK_C * (w.T @ s @ w)
        np.fill_diagonal(s, 1.0)
    out = {}
    for d in candidates:
        if d in anchors:
            out[d] = 1.0  # a seed document is as similar to the seeds' documents as anything can be
        else:
            out[d] = float(max(s[index[d], index[a]] for a in anchors))
    return out


def read_candidates(path: Path, depth: int) -> dict[str, list[str]]:
    hits: dict[str, list[tuple[float, str]]] = defaultdict(list)
    for line in path.open(encoding="utf-8"):
        qid, _, doc, _, score, _ = line.split()
        hits[qid].append((float(score), doc))
    return {q: [d for _, d in sorted(v, key=lambda x: (-x[0], x[1]))[:depth]] for q, v in hits.items()}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--seeds", type=Path, required=True, help="TSV: query id, seeds (query_seeds output)")
    p.add_argument("--candidates", type=Path, required=True, help="a TREC run; its top --depth documents per query")
    p.add_argument("--depth", type=int, default=DEPTH)
    p.add_argument("--name", required=True)
    a = p.parse_args()
    g = GraphIndex.load()
    seeds = {}
    for line in a.seeds.open(encoding="utf-8"):
        qid, _, cell = line.rstrip("\n").partition("\t")
        seeds[qid] = set(parse_seeds(cell))
    candidates = read_candidates(a.candidates, a.depth)
    out = ROOT / "data/features" / f"{a.name}_graph_v1.tsv"
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = 0
    with open(out, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(["qid", "doc_id", *COLUMNS])
        for qid in sorted(candidates):
            docs, s = candidates[qid], seeds.get(qid, set())
            sr = simrank(g, docs, s) if s else dict.fromkeys(docs, 0.0)
            for d in docs:
                feats = pair_features(g, d, s) if s else dict.fromkeys(COLUMNS, 0.0)
                feats["simrank"] = sr[d]
                w.writerow([qid, d, *[f"{feats[c]:.6f}" for c in COLUMNS]])
                rows += 1
    report = {
        "generated": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "commit": subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip(),
        "settings": {
            "depth": a.depth,
            "simrank_c": SIMRANK_C,
            "simrank_iterations": SIMRANK_ITERATIONS,
            "seed_documents": SEED_DOCUMENTS,
            "families": {k: sorted(v) for k, v in FAMILIES.items()},
        },
        "inputs": {str(x): hashlib.sha256(x.read_bytes()).hexdigest() for x in (a.seeds, a.candidates)},
        "queries": len(candidates),
        "queries_with_seeds": sum(1 for q in candidates if seeds.get(q)),
        "pairs": rows,
    }
    rep = ROOT / "results/features" / f"{a.name}_graph_v1.json"
    rep.parent.mkdir(parents=True, exist_ok=True)
    rep.write_text(json.dumps(report, indent=2) + "\n")
    print(
        f"wrote {out.relative_to(ROOT)}: {rows} pairs, {report['queries_with_seeds']} of {len(candidates)} queries with seeds"
    )


if __name__ == "__main__":
    main()
