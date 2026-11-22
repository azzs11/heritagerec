"""Score TREC run files against TREC qrels, with intervals and paired tests (specification Section 6).

Metrics come from ir-measures (trec_eval's own code through pytrec_eval); nothing is hand-written:
    nDCG@10          primary; graded gains 0-3 as judged
    P(rel=2)@5       precision at 5, a document counts as relevant from grade 2 ("clearly related")
    AP(rel=2)@100    mean average precision over the 100 documents each run returns
    R(rel=2)@100     recall at 100
    RR(rel=2)@10     reciprocal rank of the first relevant document
    Judged@10        share of the top 10 that has a judgement (unjudged documents are counted too)

Two traps are closed here. trec_eval leaves out a query the run returns nothing for, which would raise the
mean, so every evaluated query gets a value, zero when the run has no answer. And a query whose qrels hold no
relevant document cannot be scored by these measures; it is reported and left out, as decision 0021 asks.

Intervals are 95% percentile bootstrap intervals over queries (scipy, fixed seed). Comparisons are paired
randomization tests over queries (scipy permutation_test, swapping each query's two scores; fixed seed), two
sided, with Holm's correction across the comparisons of one call (statsmodels). Which comparisons form the
primary family is set by `docs/plan/analysis_plan.md`; this script only computes them.

A run on the test split is refused until the analysis plan is committed.

Usage:
    uv run python -m src.benchmark.evaluate --name dev_v1 --split dev \
        --qrels data/qrels/dev_v1.qrels --queries data/queries/dev_v1.tsv \
        --runs results/retrieval/runs/bm25_dev_v1.trec results/retrieval/runs/bm25_rm3_dev_v1.trec \
        [--baseline bm25_dev_v1] [--groups data/queries/dev_v1_groups.tsv]

    --queries   TSV: query id, language, text (only the ids are used: they fix the evaluated set)
    --groups    TSV with a header: query id, then one column per grouping (for example type, language)

Output (results/benchmark/<name>/):
    summary.json, summary.md    means, intervals, judged share, comparisons, group means, inputs and checksums
    per_query.tsv               every system's value for every query and measure
"""

import argparse
import csv
import hashlib
import json
import subprocess
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import ir_measures
import numpy as np
from ir_measures import AP, RR, Judged, P, R, nDCG

from src.corpus.wikimedia import ROOT

OUT = ROOT / "results/benchmark"
PLAN = "docs/plan/analysis_plan.md"
PRIMARY = nDCG @ 10
MEASURES = [PRIMARY, P(rel=2) @ 5, AP(rel=2) @ 100, R(rel=2) @ 100, RR(rel=2) @ 10, Judged @ 10]
RELEVANT_FROM = 2
SEED = 20261122
RESAMPLES = 10_000


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_query_ids(path: Path) -> list[str]:
    return [row[0] for row in csv.reader(open(path, encoding="utf-8"), delimiter="\t") if row]


def read_groups(path: Path) -> dict[str, dict[str, str]]:
    rows = list(csv.DictReader(open(path, encoding="utf-8"), delimiter="\t"))
    key = next(iter(rows[0])) if rows else "query_id"
    return {r[key]: {k: v for k, v in r.items() if k != key} for r in rows}


def run_name(path: Path) -> str:
    return path.name.removesuffix(".trec")


def plan_committed(root: Path = ROOT) -> bool:
    out = subprocess.run(["git", "log", "-1", "--format=%H", "--", PLAN], cwd=root, capture_output=True, text=True)
    return bool(out.stdout.strip())


def scorable(qrels: list, query_ids: list[str]) -> tuple[list[str], list[str]]:
    """Queries with at least one relevant judgement, and those without (reported, not scored)."""
    relevant = {q.query_id for q in qrels if q.relevance >= RELEVANT_FROM}
    return [q for q in query_ids if q in relevant], [q for q in query_ids if q not in relevant]


def per_query(qrels: list, run: list, query_ids: list[str]) -> dict[str, dict[str, float]]:
    """Every measure for every query, zero where the run returned nothing for it."""
    wanted = set(query_ids)
    values = {str(m): dict.fromkeys(query_ids, 0.0) for m in MEASURES}
    for m in ir_measures.iter_calc(MEASURES, [q for q in qrels if q.query_id in wanted], run):
        if m.query_id in wanted:
            values[str(m.measure)][m.query_id] = float(m.value)
    return values


def unjudged_in_top10(qrels: list, run: list, query_ids: list[str]) -> int:
    judged = {(q.query_id, q.doc_id) for q in qrels}
    ranked = defaultdict(list)
    for d in run:
        ranked[d.query_id].append(d)
    total = 0
    for q in query_ids:
        top = sorted(ranked[q], key=lambda d: (-d.score, d.doc_id))[:10]  # trec_eval's order: score, then id
        total += sum(1 for d in top if (q, d.doc_id) not in judged)
    return total


def interval(values: np.ndarray) -> tuple[float, float]:
    from scipy.stats import bootstrap

    if len(values) < 2 or np.all(values == values[0]):
        return float(values.mean()), float(values.mean())
    res = bootstrap((values,), np.mean, n_resamples=RESAMPLES, confidence_level=0.95, method="percentile", rng=SEED)
    return float(res.confidence_interval.low), float(res.confidence_interval.high)


def paired_test(a: np.ndarray, b: np.ndarray) -> float:
    """Two-sided paired randomization test on the mean difference (each query's two scores swapped at random)."""
    from scipy.stats import permutation_test

    if np.allclose(a, b):
        return 1.0
    res = permutation_test(
        (a, b),
        lambda x, y: np.mean(x - y),
        permutation_type="samples",
        n_resamples=RESAMPLES,
        alternative="two-sided",
        rng=SEED,
    )
    return float(res.pvalue)


def holm(pvalues: list[float]) -> list[float]:
    from statsmodels.stats.multitest import multipletests

    if not pvalues:
        return []
    return [float(p) for p in multipletests(pvalues, method="holm")[1]]


def evaluate(
    name: str,
    split: str,
    qrels_path: Path,
    queries_path: Path,
    run_paths: list[Path],
    baseline: str | None = None,
    groups_path: Path | None = None,
    root: Path = ROOT,
    out_dir: Path = OUT,
) -> dict:
    if split == "test" and not plan_committed(root):
        raise SystemExit(f"Refusing a test-split evaluation: {PLAN} is not committed yet.")
    qrels = list(ir_measures.read_trec_qrels(str(qrels_path)))
    query_ids, dropped = scorable(qrels, read_query_ids(queries_path))
    if not query_ids:
        raise SystemExit("No query has a relevant judgement; nothing can be scored.")
    groups = read_groups(groups_path) if groups_path else {}

    systems, table = {}, {}
    for path in run_paths:
        run = list(ir_measures.read_trec_run(str(path)))
        values = per_query(qrels, run, query_ids)
        table[run_name(path)] = values
        means = {}
        for m, by_q in values.items():
            arr = np.array([by_q[q] for q in query_ids])
            low, high = interval(arr)
            means[m] = {"mean": float(arr.mean()), "ci95": [low, high]}
        systems[run_name(path)] = {
            "file": str(path.relative_to(root)) if path.is_relative_to(root) else str(path),
            "sha256": sha256(path),
            "queries_answered": len({d.query_id for d in run} & set(query_ids)),
            "unjudged_in_top10": unjudged_in_top10(qrels, run, query_ids),
            "measures": means,
        }

    comparisons = []
    if baseline:
        if baseline not in table:
            raise SystemExit(f"--baseline {baseline} is not one of the runs")
        base = np.array([table[baseline][str(PRIMARY)][q] for q in query_ids])
        for sysname in table:
            if sysname == baseline:
                continue
            arr = np.array([table[sysname][str(PRIMARY)][q] for q in query_ids])
            comparisons.append(
                {
                    "system": sysname,
                    "baseline": baseline,
                    "measure": str(PRIMARY),
                    "difference": float((arr - base).mean()),
                    "p": paired_test(arr, base),
                }
            )
        for c, adj in zip(comparisons, holm([c["p"] for c in comparisons]), strict=True):
            c["p_holm"] = adj

    by_group = {}
    for field in sorted({k for g in groups.values() for k in g}):
        by_group[field] = {}
        for value in sorted({g.get(field, "") for g in groups.values()}):
            members = [q for q in query_ids if groups.get(q, {}).get(field) == value]
            if members:
                by_group[field][value] = {
                    "queries": len(members),
                    "systems": {s: float(np.mean([table[s][str(PRIMARY)][q] for q in members])) for s in table},
                }

    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True).stdout.strip()
    summary = {
        "name": name,
        "split": split,
        "built": datetime.now(UTC).date().isoformat(),
        "commit": commit,
        "ir_measures": ir_measures.__version__,
        "settings": {
            "primary": str(PRIMARY),
            "measures": [str(m) for m in MEASURES],
            "relevant_from_grade": RELEVANT_FROM,
            "bootstrap": {"method": "percentile", "resamples": RESAMPLES, "seed": SEED},
            "test": {"kind": "paired randomization, two-sided", "resamples": RESAMPLES, "seed": SEED},
            "correction": "Holm, across the comparisons in this file",
        },
        "inputs": {
            "qrels": {"file": str(qrels_path), "sha256": sha256(qrels_path)},
            "queries": {"file": str(queries_path), "sha256": sha256(queries_path)},
        },
        "queries_scored": len(query_ids),
        "queries_without_relevant_judgement": dropped,
        "systems": systems,
        "comparisons": comparisons,
        "groups": by_group,
    }

    target = out_dir / name
    target.mkdir(parents=True, exist_ok=True)
    (target / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (target / "summary.md").write_text(markdown(summary), encoding="utf-8")
    with open(target / "per_query.tsv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(["system", "query_id", *[str(m) for m in MEASURES]])
        for s, values in table.items():
            for q in query_ids:
                w.writerow([s, q, *[f"{values[str(m)][q]:.6f}" for m in MEASURES]])
    return summary


def markdown(s: dict) -> str:
    measures = s["settings"]["measures"]
    lines = [
        f"# Evaluation: {s['name']} ({s['split']})",
        "",
        f"Built {s['built']} at commit `{s['commit'][:7]}` with ir-measures {s['ir_measures']}. "
        f"{s['queries_scored']} queries scored; {len(s['queries_without_relevant_judgement'])} left out because "
        "no document was judged relevant. Generated by `src/benchmark/evaluate.py`; do not edit by hand.",
        "",
        "| System | " + " | ".join(measures) + " | Unjudged in top 10 |",
        "| --- | " + " | ".join("---" for _ in measures) + " | --- |",
    ]
    for name, sys in s["systems"].items():
        cells = []
        for m in measures:
            v = sys["measures"][m]
            cells.append(f"{v['mean']:.3f} [{v['ci95'][0]:.3f}, {v['ci95'][1]:.3f}]")
        lines.append(f"| {name} | " + " | ".join(cells) + f" | {sys['unjudged_in_top10']} |")
    if s["comparisons"]:
        lines += ["", f"Paired randomization tests on {s['settings']['primary']}, Holm-corrected:", ""]
        lines += ["| System | Baseline | Difference | p | p (Holm) |", "| --- | --- | --- | --- | --- |"]
        for c in s["comparisons"]:
            lines.append(
                f"| {c['system']} | {c['baseline']} | {c['difference']:+.3f} | {c['p']:.4f} | {c['p_holm']:.4f} |"
            )
    for field, values in s["groups"].items():
        names = list(s["systems"])
        lines += ["", f"{s['settings']['primary']} by {field}:", ""]
        lines += [
            "| " + field + " | Queries | " + " | ".join(names) + " |",
            "| --- | --- | " + " | ".join("---" for _ in names) + " |",
        ]
        for value, g in values.items():
            lines.append(f"| {value} | {g['queries']} | " + " | ".join(f"{g['systems'][n]:.3f}" for n in names) + " |")
    return "\n".join(lines) + "\n"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--name", required=True)
    p.add_argument("--split", choices=["dev", "test"], required=True)
    p.add_argument("--qrels", type=Path, required=True)
    p.add_argument("--queries", type=Path, required=True)
    p.add_argument("--runs", type=Path, nargs="+", required=True)
    p.add_argument("--baseline")
    p.add_argument("--groups", type=Path)
    a = p.parse_args()
    s = evaluate(a.name, a.split, a.qrels, a.queries, a.runs, a.baseline, a.groups)
    print(markdown(s))


if __name__ == "__main__":
    main()
