"""Cross-encoder reranking: bge-reranker-v2-m3 over the fused top 50 (decision 0008, specification Section 6, stage 3).

A cross-encoder reads the query and a text together and scores how well they match. bge-reranker-v2-m3 (BAAI,
Apache-2.0, multilingual) reads up to 512 tokens, so a document is scored as its best passage (MaxP, Dai and Callan,
SIGIR 2019), as the BM25 and dense runs score documents; to keep one GPU session in minutes, only a document's first
16 passages (about 2,400 words) are read, which for an article covers its lead and main sections.

Steps:
    prepare   on the laptop: the fused run's top 50 per query, as a small committed list the notebook reads
              (data/rerank/<split>_candidates_v1.tsv); run files themselves are not in git
    score     in notebooks/reranker.ipynb (GPU): every candidate's passages scored, MaxP per document, written as a
              TREC run with the model revision and settings

Usage:
    uv run python -m src.retrieval.rerank prepare --candidates results/retrieval/runs/rrf_dev_v1.trec --split dev
    python -m src.retrieval.rerank score --split dev --queries data/queries/dev_v1.tsv --passages <passages_v1.jsonl.gz>
"""

import argparse
import csv
import gzip
import hashlib
import json
import subprocess
import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODEL = "BAAI/bge-reranker-v2-m3"  # Apache-2.0
DEPTH = 50
PASSAGES_PER_DOC = 16
MAX_LENGTH = 512
BATCH = 64


def read_run(path: Path, depth: int) -> dict[str, list[str]]:
    hits: dict[str, list[tuple[float, str]]] = defaultdict(list)
    for line in path.open(encoding="utf-8"):
        qid, _, doc, _, score, _ = line.split()
        hits[qid].append((float(score), doc))
    return {q: [d for _, d in sorted(v, key=lambda x: (-x[0], x[1]))[:depth]] for q, v in hits.items()}


def passage_number(pid: str) -> int:
    return int(pid.rsplit("#", 1)[1])


def first_passages(passages: list[tuple[str, str]], k: int = PASSAGES_PER_DOC) -> list[tuple[str, str]]:
    """A document's first k passages, in reading order ("doc#0", "doc#1", ...)."""
    return sorted(passages, key=lambda p: passage_number(p[0]))[:k]


def max_passage(scores: dict[str, list[float]]) -> list[tuple[str, float]]:
    """Each document's best passage score; best first, ties by document id."""
    best = {d: max(s) for d, s in scores.items() if s}
    return sorted(best.items(), key=lambda x: (-x[1], x[0]))


def prepare(candidates: Path, split: str) -> None:
    run = read_run(candidates, DEPTH)
    out = ROOT / "data/rerank" / f"{split}_candidates_v1.tsv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        for qid in sorted(run):
            for rank, doc in enumerate(run[qid], 1):
                w.writerow([qid, doc, rank])
    meta = {"from": str(candidates), "sha256": hashlib.sha256(candidates.read_bytes()).hexdigest(), "depth": DEPTH}
    out.with_suffix(".json").write_text(json.dumps(meta, indent=2) + "\n")
    print(f"wrote {out.relative_to(ROOT)} ({sum(len(v) for v in run.values())} candidates, {len(run)} queries)")


def score(split: str, queries: Path, passages_path: Path, device: str, out_dir: Path) -> None:
    from huggingface_hub import HfApi
    from sentence_transformers import CrossEncoder

    cands: dict[str, list[str]] = defaultdict(list)
    for qid, doc, _ in csv.reader(
        open(ROOT / "data/rerank" / f"{split}_candidates_v1.tsv", encoding="utf-8"), delimiter="\t"
    ):
        cands[qid].append(doc)
    wanted = {d for ds in cands.values() for d in ds}
    by_doc: dict[str, list[tuple[str, str]]] = defaultdict(list)
    with gzip.open(passages_path, "rt", encoding="utf-8") as f:
        for line in f:
            p = json.loads(line)
            if p["doc_id"] in wanted:
                by_doc[p["doc_id"]].append((p["id"], p["contents"]))
    texts = {qid: text for qid, _, text in csv.reader(open(queries, encoding="utf-8"), delimiter="\t")}
    revision = HfApi().model_info(MODEL).sha
    model = CrossEncoder(MODEL, revision=revision, max_length=MAX_LENGTH, device=device)
    name = f"bge_reranker_{split}_v1"
    started = time.time()
    pairs_scored = 0
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / f"{name}.trec", "w", encoding="utf-8") as f:
        for qid in sorted(cands):
            items = [(d, pid, text) for d in cands[qid] for pid, text in first_passages(by_doc.get(d, []))]
            raw = model.predict([(texts[qid], t) for _, _, t in items], batch_size=BATCH, show_progress_bar=False)
            pairs_scored += len(items)
            per_doc: dict[str, list[float]] = defaultdict(list)
            for (d, _, _), s in zip(items, raw, strict=True):
                per_doc[d].append(float(s))
            for rank, (d, s) in enumerate(max_passage(per_doc), 1):
                f.write(f"{qid} Q0 {d} {rank} {s:.6f} {name}\n")
            print(f"{qid}: {len(items)} passages", flush=True)
    report = {
        "generated": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "model": MODEL,
        "revision": revision,
        "settings": {
            "depth": DEPTH,
            "passages_per_doc": PASSAGES_PER_DOC,
            "max_length": MAX_LENGTH,
            "aggregate": "MaxP",
        },
        "passages_sha256": hashlib.sha256(passages_path.read_bytes()).hexdigest(),
        "repo_commit": subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True
        ).stdout.strip(),
        "queries": len(cands),
        "pairs_scored": pairs_scored,
        "documents_without_passages": sorted(wanted - set(by_doc)),
        "seconds": round(time.time() - started, 1),
    }
    (out_dir / f"{name}.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"wrote {name}: {pairs_scored} passages in {report['seconds']} s")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("step", choices=["prepare", "score"])
    p.add_argument("--split", default="dev")
    p.add_argument("--candidates", type=Path)
    p.add_argument("--queries", type=Path)
    p.add_argument("--passages", type=Path)
    p.add_argument("--device", default="cuda")
    p.add_argument("--out", type=Path, default=ROOT / "results/retrieval/runs")
    a = p.parse_args()
    if a.step == "prepare":
        prepare(a.candidates, a.split)
    else:
        score(a.split, a.queries, a.passages, a.device, a.out)


if __name__ == "__main__":
    main()
