"""Reciprocal rank fusion of run files (decision 0008, specification Section 6, stage 2).

A document's fused score is the sum over the input runs of 1 / (k + rank), with rank counted from 1 in each run and
k = 60, the constant of Cormack, Clarke and Buettcher (SIGIR 2009); nothing is tuned. A run that does not return a
document adds nothing for it. Ties are broken by document id, so the same inputs always give the same ranking. Each
input run is read to its first DEPTH documents, as every run file holds.

Usage:
    uv run python -m src.retrieval.fusion --name rrf_dev_v1 --runs results/retrieval/runs/bm25_dev_v1.trec \
        results/retrieval/runs/e5_large_dev_v1.trec results/retrieval/runs/ppr_dev_v1.trec
Output:
    results/retrieval/runs/<name>.trec, and results/retrieval/<name>.json (inputs with their SHA-256)
"""

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

from src.corpus.wikimedia import ROOT
from src.retrieval.bm25 import DOC_DEPTH, RUNS

K = 60


def read_ranks(path: Path, depth: int = DOC_DEPTH) -> dict[str, dict[str, int]]:
    """Query id -> document -> rank, ranks re-read from the scores as trec_eval orders them (score, then id)."""
    hits: dict[str, list[tuple[float, str]]] = defaultdict(list)
    for line in path.open(encoding="utf-8"):
        qid, _, doc, _, score, _ = line.split()
        hits[qid].append((float(score), doc))
    out = {}
    for qid, pairs in hits.items():
        ordered = sorted(pairs, key=lambda p: (-p[0], p[1]))[:depth]
        out[qid] = {doc: rank for rank, (_, doc) in enumerate(ordered, 1)}
    return out


def fuse(
    runs: list[dict[str, dict[str, int]]], k: int = K, depth: int = DOC_DEPTH
) -> dict[str, list[tuple[str, float]]]:
    queries = sorted({q for run in runs for q in run})
    fused = {}
    for q in queries:
        scores: dict[str, float] = defaultdict(float)
        for run in runs:
            for doc, rank in run.get(q, {}).items():
                scores[doc] += 1.0 / (k + rank)
        fused[q] = sorted(scores.items(), key=lambda d: (-d[1], d[0]))[:depth]
    return fused


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--name", required=True)
    p.add_argument("--runs", type=Path, nargs="+", required=True)
    a = p.parse_args()
    if len(a.runs) < 2:
        raise SystemExit("fusion needs at least two runs")
    fused = fuse([read_ranks(path) for path in a.runs])
    RUNS.mkdir(parents=True, exist_ok=True)
    out = RUNS / f"{a.name}.trec"
    with open(out, "w", encoding="utf-8") as f:
        for q, ranked in fused.items():
            for rank, (doc, score) in enumerate(ranked, 1):
                f.write(f"{q} Q0 {doc} {rank} {score:.8f} {a.name}\n")
    meta = {
        "k": K,
        "depth": DOC_DEPTH,
        "runs": {
            str(r.relative_to(ROOT)) if r.is_relative_to(ROOT) else str(r): hashlib.sha256(r.read_bytes()).hexdigest()
            for r in a.runs
        },
    }
    (ROOT / "results/retrieval" / f"{a.name}.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(f"wrote {out.relative_to(ROOT)} ({len(fused)} queries from {len(a.runs)} runs)")


if __name__ == "__main__":
    main()
