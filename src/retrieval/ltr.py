"""Learning to rank: LambdaMART over the fused candidates, out of fold, with exact SHAP (decision 0037).

The candidates are each query's top 100 in the fused run (reciprocal rank fusion, decision 0008). Every candidate gets:

- from each input run: its score scaled 0-1 within the query (missing when the run did not return it, so the model
  learns what absence means) and 1 / rank (0 when absent);
- the graph features of decision 0036 (`data/features/<split>_graph_v1.tsv`);
- the document's length (log of its words) and whether its language is the query's.

Labels are the qrels' grades 0-3; an unjudged candidate is 0, and the unjudged share is reported. Five folds split by
query, seeded and the same for every variant; each fold's model ranks only the queries it never saw, so the run file
and the SHAP importance are out of fold. `--drop` retrains without one feature group (text, graph, query) for the
ablation, on the same folds.

Usage:
    uv run python -m src.retrieval.ltr --split dev --candidates results/retrieval/runs/rrf_dev_v1.trec \
        --runs results/retrieval/runs/bm25_dev_v1.trec ... --qrels data/qrels/dev_v1.qrels [--drop graph]
Output:
    results/retrieval/runs/ltr[_no<group>]_<split>_v1.trec
    results/retrieval/ltr[_no<group>]_<split>_v1.json   settings, folds, SHAP importance by feature and group
"""

import argparse
import csv
import gzip
import hashlib
import itertools
import json
import math
import random
import subprocess
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from src.corpus.wikimedia import ROOT
from src.retrieval.bm25 import RUNS

RECORDS = ROOT / "data/corpus_v1/records.jsonl.gz"
DEPTH = 100
FOLDS = 5
SEED = 20261124
PARAMS = {
    "objective": "lambdarank",
    "n_estimators": 300,
    "learning_rate": 0.05,
    "num_leaves": 15,
    "min_child_samples": 10,
    "colsample_bytree": 0.8,
    "lambdarank_truncation_level": 20,
    "label_gain": [0, 1, 3, 7],
    "random_state": SEED,
    "deterministic": True,
    "force_row_wise": True,
    "verbose": -1,
}
NAN = float("nan")


def read_run(path: Path, depth: int | None = None) -> dict[str, list[tuple[str, float]]]:
    hits: dict[str, list[tuple[float, str]]] = defaultdict(list)
    for line in path.open(encoding="utf-8"):
        qid, _, doc, _, score, _ = line.split()
        hits[qid].append((float(score), doc))
    return {q: [(d, s) for s, d in sorted(v, key=lambda x: (-x[0], x[1]))[:depth]] for q, v in hits.items()}


def run_features(name: str, ranked: list[tuple[str, float]]) -> dict[str, dict[str, float]]:
    """Per document: the run's score scaled 0-1 within the query, and 1 / rank."""
    if not ranked:
        return {}
    hi, lo = ranked[0][1], ranked[-1][1]
    span = hi - lo
    return {
        d: {f"norm_{name}": (s - lo) / span if span > 0 else 1.0, f"rr_{name}": 1.0 / r}
        for r, (d, s) in enumerate(ranked, 1)
    }


def assemble(
    candidates: dict[str, list[str]],
    runs: dict[str, dict[str, list[tuple[str, float]]]],
    graph: dict[tuple[str, str], dict[str, float]],
    docs: dict[str, dict],
    query_language: dict[str, str],
) -> tuple[list[str], list[dict], dict[str, str]]:
    """The feature table: one row per (query, candidate); missing run scores stay missing (NaN)."""
    groups: dict[str, str] = {}
    for name in runs:
        groups[f"norm_{name}"] = "graph" if name.startswith("ppr") else "text"
        groups[f"rr_{name}"] = groups[f"norm_{name}"]
    graph_cols = sorted({k for v in graph.values() for k in v})
    groups.update(dict.fromkeys(graph_cols, "graph"))
    groups.update({"log_length": "text", "language_match": "query"})
    columns = list(groups)
    rows = []
    per_run = {name: {q: run_features(name, r) for q, r in run.items()} for name, run in runs.items()}
    for qid in sorted(candidates):
        for doc in candidates[qid]:
            row = {"qid": qid, "doc_id": doc}
            for name in runs:
                f = per_run[name].get(qid, {}).get(doc)
                row[f"norm_{name}"] = f[f"norm_{name}"] if f else NAN
                row[f"rr_{name}"] = f[f"rr_{name}"] if f else 0.0
            g = graph.get((qid, doc), {})
            for c in graph_cols:
                row[c] = g.get(c, 0.0)
            meta = docs.get(doc, {})
            row["log_length"] = math.log1p(meta.get("words", 0))
            row["language_match"] = 1.0 if meta.get("language") == query_language.get(qid) else 0.0
            rows.append(row)
    return columns, rows, groups


def folds_by_query(qids: list[str], k: int = FOLDS, seed: int = SEED) -> dict[str, int]:
    order = sorted(set(qids))
    random.Random(seed).shuffle(order)
    return {q: i % k for i, q in enumerate(order)}


def train_out_of_fold(columns, rows, labels, fold_of):
    """Each fold's model ranks only its held-out queries; returns scores and per-row SHAP contributions."""
    import lightgbm as lgb
    import numpy as np

    x = np.array([[r[c] for c in columns] for r in rows], dtype=float)
    y = np.array([labels.get((r["qid"], r["doc_id"]), 0) for r in rows])
    qids = [r["qid"] for r in rows]
    scores = np.zeros(len(rows))
    shap = np.zeros((len(rows), len(columns)))
    for fold in sorted(set(fold_of.values())):
        test = np.array([fold_of[q] == fold for q in qids])
        train = ~test
        # LightGBM wants each training query's rows contiguous, with their counts as groups.
        idx = np.where(train)[0]
        idx = idx[np.argsort([qids[i] for i in idx], kind="stable")]
        sizes = [sum(1 for _ in g) for _, g in itertools.groupby(qids[i] for i in idx)]
        model = lgb.LGBMRanker(**PARAMS)
        model.fit(x[idx], y[idx], group=sizes)
        scores[test] = model.predict(x[test])
        shap[test] = model.predict(x[test], pred_contrib=True)[:, : len(columns)]
    return scores, shap


def load_qrels(path: Path) -> dict[tuple[str, str], int]:
    out = {}
    for line in path.open(encoding="utf-8"):
        qid, _, doc, grade = line.split()
        out[(qid, doc)] = int(grade)
    return out


def load_docs(ids: set[str]) -> dict[str, dict]:
    out = {}
    with gzip.open(RECORDS, "rt", encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            if rec["id"] in ids:
                out[rec["id"]] = {"words": len(rec["text"].split()), "language": rec["language"]}
    return out


def load_graph_features(path: Path) -> dict[tuple[str, str], dict[str, float]]:
    out = {}
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            out[(row.pop("qid"), row.pop("doc_id"))] = {k: float(v) for k, v in row.items()}
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--split", required=True)
    p.add_argument("--candidates", type=Path, required=True)
    p.add_argument("--runs", type=Path, nargs="+", required=True)
    p.add_argument("--qrels", type=Path, required=True)
    p.add_argument("--graph-features", type=Path)
    p.add_argument("--queries", type=Path, help="JSONL with qid and language (default data/queries/<split>_v1.jsonl)")
    p.add_argument("--drop", choices=["text", "graph", "query"])
    a = p.parse_args()

    candidates = {q: [d for d, _ in r] for q, r in read_run(a.candidates, DEPTH).items()}
    runs = {path.stem.removesuffix(f"_{a.split}_v1"): read_run(path) for path in a.runs}
    graph_path = a.graph_features or ROOT / "data/features" / f"{a.split}_graph_v1.tsv"
    graph = load_graph_features(graph_path) if graph_path.exists() else {}
    queries_path = a.queries or ROOT / "data/queries" / f"{a.split}_v1.jsonl"
    query_language = {q["qid"]: q["language"] for q in map(json.loads, queries_path.open(encoding="utf-8"))}
    docs = load_docs({d for ds in candidates.values() for d in ds})
    columns, rows, groups = assemble(candidates, runs, graph, docs, query_language)
    if a.drop:
        columns = [c for c in columns if groups[c] != a.drop]
    labels = load_qrels(a.qrels)
    fold_of = folds_by_query(list(candidates))
    scores, shap = train_out_of_fold(columns, rows, labels, fold_of)

    name = f"ltr{'_no' + a.drop if a.drop else ''}_{a.split}_v1"
    by_query: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for r, s in zip(rows, scores, strict=True):
        by_query[r["qid"]].append((r["doc_id"], float(s)))
    with open(RUNS / f"{name}.trec", "w", encoding="utf-8") as f:
        for qid in sorted(by_query):
            for rank, (doc, s) in enumerate(sorted(by_query[qid], key=lambda x: (-x[1], x[0])), 1):
                f.write(f"{qid} Q0 {doc} {rank} {s:.6f} {name}\n")
    mean_abs = {c: float(abs(shap[:, i]).mean()) for i, c in enumerate(columns)}
    by_group = defaultdict(float)
    for c, v in mean_abs.items():
        by_group[groups[c]] += v
    judged = sum(1 for r in rows if (r["qid"], r["doc_id"]) in labels)
    report = {
        "generated": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "commit": subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip(),
        "settings": PARAMS | {"folds": FOLDS, "fold_seed": SEED, "depth": DEPTH, "dropped_group": a.drop},
        "inputs": {
            str(x): hashlib.sha256(x.read_bytes()).hexdigest()
            for x in [a.candidates, a.qrels, *a.runs] + ([graph_path] if graph else [])
        },
        "queries": len(candidates),
        "rows": len(rows),
        "unjudged_share": round(1 - judged / len(rows), 4) if rows else None,
        "folds": {str(k): sorted(q for q, f in fold_of.items() if f == k) for k in range(FOLDS)},
        "shap_mean_abs": dict(sorted(mean_abs.items(), key=lambda x: -x[1])),
        "shap_mean_abs_by_group": dict(sorted(by_group.items(), key=lambda x: -x[1])),
    }
    (ROOT / "results/retrieval" / f"{name}.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"wrote {name}: {len(candidates)} queries, unjudged share {report['unjudged_share']}")


if __name__ == "__main__":
    main()
