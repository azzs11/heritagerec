"""Type coverage@10: how many of the six document types a run's top 10 holds, divided by six (analysis plan, 3).

Reported descriptively beside the relevance measures, never tested: it says whether a system shows more than one
kind of heritage (sites, objects, manuscripts and texts, inscriptions, culture, people and dynasties), which
specification Section 6 asks to keep visible so that a diversity step can never hide relevance.

Usage:
    uv run python -m src.benchmark.type_coverage --runs results/retrieval/runs/*_dev_v1.trec
Output: printed per run; results/benchmark/type_coverage_<stem>.json for each run.
"""

import argparse
import gzip
import json
from collections import defaultdict
from pathlib import Path

from src.corpus.wikimedia import ROOT

RECORDS = ROOT / "data/corpus_v1/records.jsonl.gz"
TYPES = ("site", "object", "manuscript_text", "inscription", "culture", "person_dynasty_style")
K = 10


def coverage(top: list[str], doc_type: dict[str, str], k: int = K) -> float:
    """Distinct known types among the first k documents, over the six types."""
    return len({doc_type[d] for d in top[:k] if doc_type.get(d) in TYPES}) / len(TYPES)


def read_run(path: Path) -> dict[str, list[str]]:
    hits: dict[str, list[tuple[float, str]]] = defaultdict(list)
    for line in path.open(encoding="utf-8"):
        qid, _, doc, _, score, _ = line.split()
        hits[qid].append((float(score), doc))
    return {q: [d for _, d in sorted(v, key=lambda x: (-x[0], x[1]))] for q, v in hits.items()}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--runs", type=Path, nargs="+", required=True)
    a = p.parse_args()
    runs = {path: read_run(path) for path in a.runs}
    wanted = {d for r in runs.values() for docs in r.values() for d in docs[:K]}
    doc_type = {}
    with gzip.open(RECORDS, "rt", encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            if rec["id"] in wanted:
                doc_type[rec["id"]] = rec["doc_type"]
    out_dir = ROOT / "results/benchmark"
    out_dir.mkdir(parents=True, exist_ok=True)
    for path, run in runs.items():
        per_query = {q: coverage(docs, doc_type) for q, docs in run.items()}
        mean = sum(per_query.values()) / len(per_query) if per_query else None
        (out_dir / f"type_coverage_{path.stem}.json").write_text(
            json.dumps({"run": str(path), "k": K, "types": TYPES, "mean": mean, "per_query": per_query}, indent=2)
            + "\n"
        )
        print(f"{path.stem}: type coverage@{K} = {mean:.3f}" if mean is not None else f"{path.stem}: no queries")


if __name__ == "__main__":
    main()
