"""The human validation of the LLM judge on 15 test queries (specification Section 9; decisions 0022, 0031).

Steps (phase 2, once the test runs exist, which needs the committed analysis plan):
    select     15 test queries, seeded: 2 Hindi and 2 Kannada, the rest English, spread over the four types, with at
               least 4 in the sparse coverage tier (0031). Written once; never redrawn after a sheet exists.
    sheet      One sheet per judge (`--judge author`, `--judge second`): every document in any system's top 5 for
               those queries, shuffled, showing only query, title and text, so labels are blind to systems and to
               the LLM. Both judges get the same pairs in the same order.
    agreement  The LLM's labels against each person's (and the two people against each other, the ceiling):
               weighted kappa (linear) and raw agreement, overall, per query language, per coverage tier, and per
               system (pairs in that system's top 5), the judge-bias check.

Usage:
    uv run python -m src.benchmark.validation select
    uv run python -m src.benchmark.validation sheet --judge author
    uv run python -m src.benchmark.validation agreement
Files:
    data/judging/validation_queries_v1.json
    data/judging/validation_<judge>_v1.csv      fill in `label` (0-3)
    results/judging/validation_agreement_v1.json and .md
"""

import argparse
import csv
import gzip
import json
import random
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from src.benchmark.judge_prompt import cut
from src.benchmark.judging import commit, pair_id, read_run
from src.corpus.wikimedia import ROOT

QUERIES = ROOT / "data/queries/test_v1.jsonl"
DATA = ROOT / "data/judging"
RESULTS = ROOT / "results/judging"
RUNS = ROOT / "results/retrieval/runs"
RECORDS = ROOT / "data/corpus_v1/records.jsonl.gz"
JUDGEMENTS = RESULTS / "test_judgements_v1.jsonl"
SELECTED = DATA / "validation_queries_v1.json"
SEED = 20261123
N, PER_INDIC, SPARSE_MIN, TOP = 15, 2, 4, 5
LABELS = (0, 1, 2, 3)


def select() -> None:
    if SELECTED.exists() and any(DATA.glob("validation_*_v1.csv")):
        raise SystemExit("a validation sheet exists; the selected queries are never redrawn")
    queries = [json.loads(line) for line in QUERIES.open(encoding="utf-8")]
    rng = random.Random(SEED)
    picked: list[dict] = []
    for lang in ("hi", "kn"):
        pool = sorted((q for q in queries if q["language"] == lang), key=lambda q: q["qid"])
        # Prefer sparse-tier queries first so the tier quota is met without taking more Indic queries.
        pool.sort(key=lambda q: (q.get("coverage_tier") != "sparse", rng.random()))
        picked += pool[:PER_INDIC]
    english = sorted((q for q in queries if q["language"] == "en"), key=lambda q: q["qid"])
    rng.shuffle(english)
    need_sparse = max(0, SPARSE_MIN - sum(q.get("coverage_tier") == "sparse" for q in picked))
    picked += [q for q in english if q.get("coverage_tier") == "sparse"][:need_sparse]
    types = defaultdict(int)
    for q in picked:
        types[q["query_type"]] += 1
    for q in english:
        if len(picked) == N:
            break
        # Fill with the least represented type, so the four types stay spread out.
        if q in picked or types[q["query_type"]] > min(
            types.get(t, 0) for t in ("simple", "entity", "concept", "complex")
        ):
            continue
        picked.append(q)
        types[q["query_type"]] += 1
    for q in english:
        if len(picked) == N:
            break
        if q not in picked:
            picked.append(q)
    sparse = sum(q.get("coverage_tier") == "sparse" for q in picked)
    SELECTED.parent.mkdir(parents=True, exist_ok=True)
    SELECTED.write_text(
        json.dumps({"seed": SEED, "queries": sorted(q["qid"] for q in picked), "sparse": sparse}, indent=2) + "\n"
    )
    print(f"{SELECTED.relative_to(ROOT)}: {len(picked)} queries, {sparse} sparse-tier")
    if sparse < SPARSE_MIN:
        print(f"only {sparse} sparse-tier queries available; fewer than {SPARSE_MIN} (reported)")


def top_pairs(qids: set[str], runs: list[Path]) -> dict[str, dict]:
    pairs: dict[str, dict] = {}
    for path in runs:
        for qid, docs in read_run(path, TOP).items():
            if qid in qids:
                for doc in docs:
                    entry = pairs.setdefault(pair_id(qid, doc), {"qid": qid, "doc_id": doc, "systems": []})
                    entry["systems"].append(path.stem)
    return pairs


def sheet(judge: str, runs: list[Path]) -> None:
    out = DATA / f"validation_{judge}_v1.csv"
    if out.exists() and any(r["label"].strip() for r in csv.DictReader(out.open(encoding="utf-8-sig"))):
        raise SystemExit(f"{out.name} already has labels; it is never rewritten")
    selected = json.loads(SELECTED.read_text())["queries"]
    runs = runs or sorted(RUNS.glob("*_test_v1.trec"))
    if not runs:
        raise SystemExit("no test runs yet (they wait for the committed analysis plan)")
    pairs = top_pairs(set(selected), runs)
    texts = {q["qid"]: q["text"] for q in map(json.loads, QUERIES.open(encoding="utf-8"))}
    docs = {}
    with gzip.open(RECORDS, "rt", encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            docs[rec["id"]] = rec
    order = sorted(pairs)
    random.Random(f"{SEED}:sheet").shuffle(order)  # the same order for every judge
    with open(out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["pair_id", "query", "title", "text", "label", "notes"])
        writer.writeheader()
        for pid in order:
            p = pairs[pid]
            d = docs[p["doc_id"]]
            writer.writerow(
                {
                    "pair_id": pid,
                    "query": texts[p["qid"]],
                    "title": d["title"],
                    "text": cut(d["text"]),
                    "label": "",
                    "notes": "",
                }
            )
    (DATA / "validation_pairs_v1.json").write_text(json.dumps(pairs, indent=2) + "\n")
    print(f"{out.relative_to(ROOT)}: {len(order)} pairs from {len(runs)} runs")


def stats(a: list[int], b: list[int]) -> dict:
    from sklearn.metrics import cohen_kappa_score

    if not a:
        return {"n": 0}
    return {
        "n": len(a),
        "weighted_kappa_linear": round(float(cohen_kappa_score(a, b, weights="linear", labels=list(LABELS))), 3),
        "raw_agreement": round(sum(x == y for x, y in zip(a, b, strict=True)) / len(a), 3),
    }


def read_labels(path: Path) -> dict[str, int]:
    rows = list(csv.DictReader(path.open(encoding="utf-8-sig")))
    bad = [r["pair_id"] for r in rows if r["label"].strip() not in {"0", "1", "2", "3"}]
    if bad:
        raise SystemExit(f"{path.name}: label must be 0-3; missing or wrong for {len(bad)} pairs")
    return {r["pair_id"]: int(r["label"]) for r in rows}


def agreement() -> None:
    pairs = json.loads((DATA / "validation_pairs_v1.json").read_text())
    queries = {q["qid"]: q for q in map(json.loads, QUERIES.open(encoding="utf-8"))}
    llm = {}
    for line in JUDGEMENTS.open(encoding="utf-8"):
        r = json.loads(line)
        llm[r["pair_id"]] = r["label"]
    people = {
        j: read_labels(DATA / f"validation_{j}_v1.csv")
        for j in ("author", "second")
        if (DATA / f"validation_{j}_v1.csv").exists()
    }

    def compare(a: dict, b: dict, keep=lambda pid: True) -> dict:
        ids = [p for p in pairs if p in a and p in b and a[p] is not None and b[p] is not None and keep(p)]
        return stats([a[p] for p in ids], [b[p] for p in ids])

    def breakdown(a: dict, b: dict) -> dict:
        out = {"overall": compare(a, b)}
        for field, key in (("language", "language"), ("tier", "coverage_tier")):
            values = sorted({queries[p["qid"]].get(key) or "no entity" for p in pairs.values()})
            out[f"by_{field}"] = {
                v: compare(a, b, lambda pid, v=v, key=key: (queries[pairs[pid]["qid"]].get(key) or "no entity") == v)
                for v in values
            }
        systems = sorted({s for p in pairs.values() for s in p["systems"]})
        out["by_system"] = {s: compare(a, b, lambda pid, s=s: s in pairs[pid]["systems"]) for s in systems}
        return out

    report = {
        "generated": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "commit": commit(),
        "pairs": len(pairs),
        "llm_vs": {j: breakdown(labels, llm) for j, labels in people.items()},
        "human_vs_human": breakdown(people["author"], people["second"]) if len(people) == 2 else None,
    }
    out = RESULTS / "validation_agreement_v1"
    RESULTS.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n")
    lines = [
        "# Human validation of the LLM judge (15 test queries)",
        "",
        f"Generated by `src/benchmark/validation.py` on {report['generated'][:10]} at commit `{report['commit']}`. "
        "Weighted kappa with linear weights over labels 0-3; raw agreement.",
        "",
        "| Comparison | Group | Pairs | Weighted kappa | Raw agreement |",
        "| --- | --- | --- | --- | --- |",
    ]
    rows = [(f"LLM vs {j}", b) for j, b in report["llm_vs"].items()]
    if report["human_vs_human"]:
        rows.append(("author vs second", report["human_vs_human"]))
    for name, b in rows:
        groups = [("overall", b["overall"])]
        for key in ("by_language", "by_tier", "by_system"):
            groups += [(f"{key[3:]} {k}", v) for k, v in b[key].items()]
        for g, s in groups:
            if s["n"]:
                lines.append(f"| {name} | {g} | {s['n']} | {s['weighted_kappa_linear']} | {s['raw_agreement']} |")
    out.with_suffix(".md").write_text("\n".join(lines) + "\n")
    print(json.dumps({k: v["overall"] for k, v in report["llm_vs"].items()}))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("step", choices=["select", "sheet", "agreement"])
    p.add_argument("--judge", choices=["author", "second"], default="author")
    p.add_argument("--runs", type=Path, nargs="*", default=[])
    a = p.parse_args()
    if a.step == "select":
        select()
    elif a.step == "sheet":
        sheet(a.judge, a.runs)
    else:
        agreement()


if __name__ == "__main__":
    main()
