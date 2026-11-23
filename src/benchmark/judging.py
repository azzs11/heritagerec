"""Pools, the author's pilot check of the judge, agreement, and qrels (specification Section 9, decision 0022).

Steps:
    pool       The union of every run's top DEPTH documents per query, with the query and the document's
               title and text: the judge's input. A pair keeps a stable id, so re-pooling later systems adds
               only new pairs and never re-judges old ones. Runs, depth and checksums go in the report.
    pilot      About 100 pairs for the author to label 0-3, blind to systems and to any LLM label: stratified
               by language (50 English, 25 Hindi, 25 Kannada) and, inside each, half from ranks 1-3 and half
               from ranks 4-10 (a pair's best rank over the runs). Dev only; separate from the 15-query
               validation on test.
    agreement  The judge's labels against the author's pilot labels: weighted kappa (linear weights, scikit-
               learn) and raw agreement, overall and per language, with the confusion table. Below about 0.4
               the paid-API fallback of the benchmark rules applies.
    qrels      The judge's labels as TREC qrels. A pair whose output has no valid score line is listed and left
               out for a rerun; it is never filled in.

Usage:
    uv run python -m src.benchmark.judging pool --split dev [--depth 10] [--runs <run files>]
    uv run python -m src.benchmark.judging pilot --split dev
    uv run python -m src.benchmark.judging agreement --split dev
    uv run python -m src.benchmark.judging qrels --split dev
Files:
    data/judging/<split>_pool_v1.jsonl             judge input, one pair per line
    data/judging/<split>_pilot_sheet_v1.csv        for the author: fill in `label` (0-3)
    results/judging/<split>_judgements_v1.jsonl    from notebooks/relevance_judge.ipynb
    data/qrels/<split>_v1.qrels                    TREC qrels from the judge
    results/judging/<split>_pool_v1.json, <split>_pilot_agreement_v1.json and .md
"""

import argparse
import csv
import gzip
import hashlib
import json
import random
import subprocess
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

from src.benchmark.judge_prompt import cut
from src.corpus.wikimedia import ROOT

DATA = ROOT / "data/judging"
RESULTS = ROOT / "results/judging"
QRELS = ROOT / "data/qrels"
RUNS = ROOT / "results/retrieval/runs"
RECORDS = ROOT / "data/corpus_v1/records.jsonl.gz"
QUERIES = ROOT / "data/queries"
DEPTH = 10
PILOT = {"en": 50, "hi": 25, "kn": 25}
PILOT_SEED = 20261123
LABELS = (0, 1, 2, 3)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def commit() -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip()


def pair_id(qid: str, doc: str) -> str:
    return hashlib.sha1(f"{qid}\t{doc}".encode()).hexdigest()[:12]


def read_run(path: Path, depth: int) -> dict[str, list[str]]:
    ranked: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for line in path.open(encoding="utf-8"):
        qid, _, doc, rank, *_ = line.split()
        ranked[qid].append((int(rank), doc))
    return {q: [d for _, d in sorted(hits)[:depth]] for q, hits in ranked.items()}


def read_queries(split: str) -> list[dict]:
    path = QUERIES / f"{split}_v1.jsonl"
    return [json.loads(line) for line in path.open(encoding="utf-8")]


def documents(ids: set[str]) -> dict[str, dict]:
    out = {}
    with gzip.open(RECORDS, "rt", encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            if rec["id"] in ids:
                out[rec["id"]] = {"title": rec["title"], "text": rec["text"], "language": rec["language"]}
    return out


def pool(split: str, depth: int, runs: list[Path]) -> None:
    if split != "dev":
        # Test pools come in phase 2, after the analysis plan is committed (src.benchmark.evaluate guards runs).
        raise SystemExit("only the dev pool is built now")
    queries = {q["qid"]: q for q in read_queries(split)}
    runs = runs or sorted(RUNS.glob(f"*_{split}_v1.trec"))
    if not runs:
        raise SystemExit(f"no run files for {split} in {RUNS}")
    best: dict[tuple[str, str], dict] = {}
    for path in runs:
        for qid, docs in read_run(path, depth).items():
            if qid not in queries:
                raise SystemExit(f"{path.name}: query {qid} is not a {split} query")
            for rank, doc in enumerate(docs, 1):
                entry = best.setdefault((qid, doc), {"best_rank": rank, "runs": {}})
                entry["best_rank"] = min(entry["best_rank"], rank)
                entry["runs"][path.stem] = rank
    docs = documents({d for _, d in best})
    missing = sorted({d for _, d in best} - set(docs))
    if missing:
        raise SystemExit(f"{len(missing)} pooled documents are not in the snapshot, e.g. {missing[:3]}")
    out = DATA / f"{split}_pool_v1.jsonl"
    old = {}
    if out.exists():
        old = {r["pair_id"]: r for r in map(json.loads, out.open(encoding="utf-8"))}
    rows = []
    for (qid, doc), entry in sorted(best.items()):
        q, d = queries[qid], docs[doc]
        rows.append(
            {
                "pair_id": pair_id(qid, doc),
                "qid": qid,
                "query": q["text"],
                "query_language": q["language"],
                "doc_id": doc,
                "doc_language": d["language"],
                "title": d["title"],
                "text": cut(d["text"]),
                "best_rank": entry["best_rank"],
                "runs": entry["runs"],
            }
        )
    DATA.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    per_query = Counter(r["qid"] for r in rows)
    report = {
        "generated": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "commit": commit(),
        "split": split,
        "depth": depth,
        "runs": {p.stem: sha256(p) for p in runs},
        "pairs": len(rows),
        "new_pairs": sum(1 for r in rows if r["pair_id"] not in old),
        "queries": len(per_query),
        "pairs_per_query": {"min": min(per_query.values()), "max": max(per_query.values())},
        "pairs_by_query_language": dict(Counter(r["query_language"] for r in rows)),
        "pool_sha256": sha256(out),
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / f"{split}_pool_v1.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"{out.relative_to(ROOT)}: {len(rows)} pairs for {len(per_query)} queries from {len(runs)} runs")


def pilot(split: str) -> None:
    rows = [json.loads(line) for line in (DATA / f"{split}_pool_v1.jsonl").open(encoding="utf-8")]
    rng = random.Random(PILOT_SEED)
    picked = []
    for lang, n in PILOT.items():
        top = sorted(
            (r for r in rows if r["query_language"] == lang and r["best_rank"] <= 3), key=lambda r: r["pair_id"]
        )
        rest = sorted(
            (r for r in rows if r["query_language"] == lang and r["best_rank"] > 3), key=lambda r: r["pair_id"]
        )
        half = n // 2
        take_top = min(len(top), n - min(len(rest), half))
        take_rest = min(len(rest), n - take_top)
        picked += rng.sample(top, take_top) + rng.sample(rest, take_rest)
    rng.shuffle(picked)  # no order by system, rank or language
    out = DATA / f"{split}_pilot_sheet_v1.csv"
    if out.exists() and any(r.get("label", "").strip() for r in csv.DictReader(out.open(encoding="utf-8-sig"))):
        raise SystemExit(f"{out.name} already has the author's labels; it is never rewritten")
    with open(out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["pair_id", "query", "title", "text", "label", "notes"])
        writer.writeheader()
        for r in picked:
            writer.writerow(
                {
                    "pair_id": r["pair_id"],
                    "query": r["query"],
                    "title": r["title"],
                    "text": r["text"],
                    "label": "",
                    "notes": "",
                }
            )
    print(f"{out.relative_to(ROOT)}: {len(picked)} pairs ({Counter(r['query_language'] for r in picked)})")


def judgements(split: str) -> dict[str, dict]:
    path = RESULTS / f"{split}_judgements_v1.jsonl"
    out = {}
    for line in path.open(encoding="utf-8"):
        r = json.loads(line)
        out[r["pair_id"]] = r  # a rerun of a pair replaces its earlier line
    return out


def agreement(split: str) -> None:
    from sklearn.metrics import cohen_kappa_score

    pool_rows = {r["pair_id"]: r for r in map(json.loads, (DATA / f"{split}_pool_v1.jsonl").open(encoding="utf-8"))}
    sheet = list(csv.DictReader((DATA / f"{split}_pilot_sheet_v1.csv").open(encoding="utf-8-sig")))
    bad = [r["pair_id"] for r in sheet if r["label"].strip() not in {"0", "1", "2", "3"}]
    if bad:
        raise SystemExit(f"label must be 0, 1, 2 or 3; missing or wrong for {len(bad)} pairs, e.g. {bad[:3]}")
    judged = judgements(split)
    pairs = [(r["pair_id"], int(r["label"]), judged.get(r["pair_id"], {}).get("label")) for r in sheet]
    unjudged = [p for p, _, j in pairs if j is None]
    pairs = [(p, a, j) for p, a, j in pairs if j is not None]

    def stats(group):
        author = [a for _, a, _ in group]
        judge = [j for _, _, j in group]
        if not group:
            return {"n": 0}
        return {
            "n": len(group),
            # Every label is passed, so a label nobody used still counts in the weights.
            "weighted_kappa_linear": round(
                float(cohen_kappa_score(author, judge, weights="linear", labels=list(LABELS))), 3
            ),
            "raw_agreement": round(sum(a == j for a, j in zip(author, judge, strict=True)) / len(group), 3),
            "confusion_author_by_judge": [
                [sum(1 for a, j in zip(author, judge, strict=True) if a == x and j == y) for y in LABELS]
                for x in LABELS
            ],
        }

    by_lang = defaultdict(list)
    for p in pairs:
        by_lang[pool_rows[p[0]]["query_language"]].append(p)
    sample = next(iter(judged.values()), {})
    report = {
        "generated": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "commit": commit(),
        "judge": {k: sample.get(k) for k in ("model", "revision", "prompt_version", "prompt_sha256")},
        "overall": stats(pairs),
        "by_query_language": {lang: stats(g) for lang, g in sorted(by_lang.items())},
        "pairs_without_a_judge_label": unjudged,
        "fallback_rule": "below about 0.4 weighted kappa, the paid-API judge runs too and both are reported",
    }
    out = RESULTS / f"{split}_pilot_agreement_v1"
    out.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n")
    lines = [
        "# Relevance judge: pilot agreement with the author",
        "",
        f"Generated by `src/benchmark/judging.py` on {report['generated'][:10]} at commit `{report['commit']}` "
        f"(decision 0022). Judge: {report['judge']['model']} at `{report['judge']['revision']}`, prompt "
        f"{report['judge']['prompt_version']}. Weighted kappa uses linear weights over labels 0-3.",
        "",
        "| Group | Pairs | Weighted kappa | Raw agreement |",
        "| --- | --- | --- | --- |",
    ]
    for name, s in [("overall", report["overall"]), *report["by_query_language"].items()]:
        if s["n"]:
            lines.append(f"| {name} | {s['n']} | {s['weighted_kappa_linear']} | {s['raw_agreement']} |")
    lines += ["", "Confusion, overall (rows: author 0-3, columns: judge 0-3):", ""]
    lines += ["| | 0 | 1 | 2 | 3 |", "| --- | --- | --- | --- | --- |"]
    for x, counts in zip(LABELS, report["overall"].get("confusion_author_by_judge", []), strict=False):
        lines.append(f"| {x} | " + " | ".join(map(str, counts)) + " |")
    if unjudged:
        lines += ["", f"{len(unjudged)} pilot pairs have no judge label yet."]
    out.with_suffix(".md").write_text("\n".join(lines) + "\n")
    print(
        json.dumps(
            report["overall"]
            | {"by_language": {k: v.get("weighted_kappa_linear") for k, v in report["by_query_language"].items()}}
        )
    )


def qrels(split: str) -> None:
    pool_rows = [json.loads(line) for line in (DATA / f"{split}_pool_v1.jsonl").open(encoding="utf-8")]
    judged = judgements(split)
    QRELS.mkdir(parents=True, exist_ok=True)
    out = QRELS / f"{split}_v1.qrels"
    missing, unparsed = [], []
    with open(out, "w", encoding="utf-8") as f:
        for r in pool_rows:
            j = judged.get(r["pair_id"])
            if j is None:
                missing.append(r["pair_id"])
            elif j.get("label") is None:
                unparsed.append(r["pair_id"])
            else:
                f.write(f"{r['qid']} 0 {r['doc_id']} {j['label']}\n")
    print(f"{out.relative_to(ROOT)}: {len(pool_rows) - len(missing) - len(unparsed)} judged pairs")
    if missing or unparsed:
        print(
            f"not in the qrels: {len(missing)} pairs not judged yet, {len(unparsed)} with no valid score line (rerun)"
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("step", choices=["pool", "pilot", "agreement", "qrels"])
    parser.add_argument("--split", default="dev")
    parser.add_argument("--depth", type=int, default=DEPTH)
    parser.add_argument("--runs", type=Path, nargs="*", default=[])
    args = parser.parse_args()
    if args.step == "pool":
        pool(args.split, args.depth, args.runs)
    else:
        {"pilot": pilot, "agreement": agreement, "qrels": qrels}[args.step](args.split)


if __name__ == "__main__":
    main()
