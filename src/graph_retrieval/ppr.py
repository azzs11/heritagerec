"""Personalised PageRank over the core graph, the graph lens's ranking (decisions 0007, 0008, 0027).

A walk starts at the query's entities (the seeds), follows the graph's edges in either direction, and jumps back
to the seeds with probability `restart` at every step. A document's score is the share of time the walk spends on
it. Hubs are down-weighted by inverse frequency: a step from a node to a neighbour of degree d is weighted by
d ** -hub_power, so a century or "India" is not an easy road between everything (hub_power 0 turns this off).

The graph is undirected for the walk: "Hampi is in Karnataka" also joins Karnataka to Hampi. Each pair of nodes
counts once, however many relations join them. A node with no edges sends its walk back to the seeds.

Solved by power iteration on a scipy sparse matrix, to a fixed tolerance; ties are broken by document id, so the
same seeds always give the same ranking.

Usage:
    uv run python -m src.graph_retrieval.ppr --seeds Q466581 Q1061          # top documents for these seeds
    uv run python -m src.graph_retrieval.ppr --queries <tsv> --name <run>   # TSV: query id, seed;seed;...
"""

import argparse
import gzip
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy import sparse

from src.corpus.wikimedia import ROOT

NODES = ROOT / "data/graph/core_v1/nodes.jsonl.gz"
EDGES = ROOT / "data/graph/core_v1/edges.tsv.gz"
RUNS = ROOT / "results/retrieval/runs"
RESTART = 0.15  # the usual teleport probability (Page et al. 1999; Haveliwala 2002); tuned on dev only
HUB_POWER = 1.0  # inverse frequency, as decision 0007 says; 0 and 0.5 are reported beside it on dev
TOLERANCE = 1e-10
MAX_ITERATIONS = 200
DOC_DEPTH = 100


@dataclass
class Walk:
    ids: list[str]
    index: dict[str, int]
    kinds: np.ndarray  # True for documents
    step: sparse.csr_matrix  # row-stochastic: step[u, v] = probability of moving from u to v
    dangling: np.ndarray  # rows with no edges
    hub_power: float


def load_graph(
    nodes_path: Path = NODES, edges_path: Path = EDGES
) -> tuple[list[str], list[bool], set[tuple[str, str]]]:
    ids, is_doc = [], []
    for line in gzip.open(nodes_path, "rt", encoding="utf-8"):
        n = json.loads(line)
        ids.append(n["id"])
        is_doc.append(n["kind"] == "document")
    order = sorted(range(len(ids)), key=lambda i: ids[i])
    ids, is_doc = [ids[i] for i in order], [is_doc[i] for i in order]
    pairs = set()
    with gzip.open(edges_path, "rt", encoding="utf-8") as f:
        next(f)  # header
        for line in f:
            s, _, t, *_ = line.rstrip("\n").split("\t")
            if s != t:
                pairs.add((min(s, t), max(s, t)))
    return ids, is_doc, pairs


def build(ids: list[str], is_doc: list[bool], pairs: set[tuple[str, str]], hub_power: float = HUB_POWER) -> Walk:
    index = {n: i for i, n in enumerate(ids)}
    rows, cols = [], []
    for a, b in sorted(pairs):
        i, j = index[a], index[b]
        rows += [i, j]
        cols += [j, i]
    n = len(ids)
    adjacency = sparse.csr_matrix((np.ones(len(rows)), (rows, cols)), shape=(n, n))
    degree = np.asarray(adjacency.sum(axis=1)).ravel()
    # Weight each step by the target's degree ** -hub_power, then make every row sum to one.
    target_weight = np.where(degree > 0, np.power(np.maximum(degree, 1), -hub_power), 0.0)
    weighted = adjacency @ sparse.diags(target_weight)
    row_sum = np.asarray(weighted.sum(axis=1)).ravel()
    dangling = row_sum == 0
    inverse = np.where(dangling, 0.0, 1.0 / np.where(dangling, 1.0, row_sum))
    step = sparse.diags(inverse) @ weighted
    return Walk(ids, index, np.array(is_doc), step.tocsr(), dangling, hub_power)


def scores(walk: Walk, seeds: dict[str, float], restart: float = RESTART) -> np.ndarray:
    """Stationary visit share of every node for a walk that restarts at the seeds (weights need not sum to 1)."""
    known = {s: w for s, w in seeds.items() if s in walk.index and w > 0}
    if not known:
        return np.zeros(len(walk.ids))
    start = np.zeros(len(walk.ids))
    for s, w in known.items():
        start[walk.index[s]] += w
    start /= start.sum()
    x = start.copy()
    transpose = walk.step.T.tocsr()
    for _ in range(MAX_ITERATIONS):
        lost = x[walk.dangling].sum()  # walks at a node with no edges go back to the seeds
        nxt = restart * start + (1 - restart) * (transpose @ x + lost * start)
        if np.abs(nxt - x).sum() < TOLERANCE:
            return nxt
        x = nxt
    return x


def rank_documents(walk: Walk, x: np.ndarray, depth: int = DOC_DEPTH) -> list[tuple[str, float]]:
    docs = [(walk.ids[i], float(x[i])) for i in np.flatnonzero(walk.kinds & (x > 0))]
    return sorted(docs, key=lambda d: (-d[1], d[0]))[:depth]


def parse_seeds(text: str) -> dict[str, float]:
    """`Q1;Q2` or `Q1:0.5;Q2:0.5` (weights split equally when absent)."""
    out: dict[str, float] = {}
    for part in filter(None, (p.strip() for p in text.split(";"))):
        node, _, w = part.partition(":")
        out[node] = out.get(node, 0.0) + (float(w) if w else 1.0)
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--seeds", nargs="*")
    p.add_argument("--queries", type=Path, help="TSV: query id, seeds as Q1;Q2 or Q1:weight;Q2:weight")
    p.add_argument("--name", help="run name for --queries")
    p.add_argument("--restart", type=float, default=RESTART)
    p.add_argument("--hub-power", type=float, default=HUB_POWER)
    a = p.parse_args()
    walk = build(*load_graph(), hub_power=a.hub_power)
    if a.seeds:
        for rank, (doc, s) in enumerate(
            rank_documents(walk, scores(walk, dict.fromkeys(a.seeds, 1.0), a.restart))[:20], 1
        ):
            print(f"{rank:3d}  {s:.6f}  {doc}")
        return
    if not (a.queries and a.name):
        raise SystemExit("give --seeds, or --queries with --name")
    RUNS.mkdir(parents=True, exist_ok=True)
    out = RUNS / f"{a.name}.trec"
    with open(out, "w", encoding="utf-8") as f:
        for line in open(a.queries, encoding="utf-8"):
            qid, _, seeds = line.rstrip("\n").partition("\t")
            ranked = rank_documents(walk, scores(walk, parse_seeds(seeds), a.restart))
            for rank, (doc, s) in enumerate(ranked, 1):
                f.write(f"{qid} Q0 {doc} {rank} {s:.10f} {a.name}\n")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
