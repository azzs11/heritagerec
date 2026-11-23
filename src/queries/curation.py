"""Curation of the generated benchmark queries, reserves, and the 40 dev / 160 test split (decisions 0021, 0031).

Steps:
    sheet      Build (or extend) the author's curation sheet from the notebook's outputs. Rows already
               curated are never changed; reserve outputs are added as new rows.
    reserves   Write data/queries/reserve_requests_v1.json: for each slot whose latest row is rejected, the
               next reserve rank. Commit it and rerun notebooks/query_generation.ipynb, then `sheet` again.
    finalize   Check every slot has one kept or edited query; write the queries with their target entity, its
               provisional coverage tier and whether the query links to the gazetteer; split 40 dev / 160 test,
               stratified by language and type and, inside those, by tier; report the sparse-tier quotas of 0031
               and the SHA-256 of the test file. Nothing is run on the test file until the analysis plan is
               committed (src.benchmark.evaluate refuses).

The author fills in, per row: `action` (keep, edit or reject), `edited_query` (when editing), `reason` (for an
edit or a rejection), `target_entity` (the QID the query is about, or none), and `notes`. The target entity is
marked from the query and backstory alone, without looking at any system's results.

Usage:
    uv run python -m src.queries.curation sheet | reserves | finalize
"""

import argparse
import csv
import hashlib
import json
import random
import re
import subprocess
from collections import Counter, defaultdict
from datetime import UTC, datetime

from src.corpus.wikimedia import ROOT

OUTPUTS = ROOT / "results/queries/generation_v1/outputs.jsonl"
SHEET = ROOT / "data/queries/curation_v1.csv"
REQUESTS = ROOT / "data/queries/reserve_requests_v1.json"
QUERIES = ROOT / "data/queries/queries_v1.jsonl"
DEV = ROOT / "data/queries/dev_v1.jsonl"
# The runners (src/retrieval/bm25.py, dense.py) read a TSV: query id, language, text. Only dev gets one now; the test
# queries are written as JSONL and get their TSV in phase 2, after the analysis plan is committed.
DEV_TSV = ROOT / "data/queries/dev_v1.tsv"
# Groups for results by type, language and tier (src.benchmark.evaluate --groups).
DEV_GROUPS = ROOT / "data/queries/dev_v1_groups.tsv"
TEST = ROOT / "data/queries/test_v1.jsonl"
REPORT = ROOT / "results/queries/split_v1"
SPLIT_SEED = 20261123
MAX_RANK = 2
# Decision 0021: 40 dev queries, 10 per type, of which 4 Hindi and 4 Kannada (one per type each).
DEV_PER_CELL = {"en": 8, "hi": 1, "kn": 1}
# Decision 0031: sparse-tier queries at least 30 in test and 8 in dev.
SPARSE_MIN = {"test": 30, "dev": 8}
QID = re.compile(r"^Q\d+$")
CELL_FIELDS = ["slot", "rank", "language", "query_type", "style", "role", "purpose", "area", "region", "period"]
AUTHOR_FIELDS = ["action", "edited_query", "reason", "target_entity", "notes"]
COLUMNS = ["cell_id", *CELL_FIELDS, "backstory", "query", *AUTHOR_FIELDS]


def read_sheet() -> list[dict]:
    if not SHEET.exists():
        return []
    with open(SHEET, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write_sheet(rows: list[dict]) -> None:
    SHEET.parent.mkdir(parents=True, exist_ok=True)
    with open(SHEET, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def sheet() -> None:
    outputs = [json.loads(line) for line in OUTPUTS.open(encoding="utf-8")]
    rows = read_sheet()
    have = {r["cell_id"] for r in rows}
    added = 0
    for o in outputs:
        if o["cell_id"] in have:
            continue
        cell = o["cell"]
        rows.append(
            {
                "cell_id": o["cell_id"],
                **{k: cell[k] for k in CELL_FIELDS},
                "backstory": o["backstory"],
                "query": o["query"],
                **{k: "" for k in AUTHOR_FIELDS},
            }
        )
        added += 1
    rows.sort(key=lambda r: (r["slot"], int(r["rank"])))
    write_sheet(rows)
    print(f"{SHEET.relative_to(ROOT)}: {len(rows)} rows, {added} added")


def latest(rows: list[dict]) -> dict[str, dict]:
    """The highest-rank row of each slot: the one that counts."""
    out: dict[str, dict] = {}
    for r in rows:
        if r["slot"] not in out or int(r["rank"]) > int(out[r["slot"]]["rank"]):
            out[r["slot"]] = r
    return out


def check_rows(rows: list[dict]) -> list[str]:
    problems = []
    for r in rows:
        action = r["action"].strip().lower()
        if action not in ("", "keep", "edit", "reject"):
            problems.append(f"{r['cell_id']}: action must be keep, edit or reject")
        if action == "edit" and not r["edited_query"].strip():
            problems.append(f"{r['cell_id']}: an edit needs edited_query")
        if action in ("edit", "reject") and not r["reason"].strip():
            problems.append(f"{r['cell_id']}: an edit or rejection needs a reason")
        target = r["target_entity"].strip()
        if action in ("keep", "edit") and not (QID.match(target) or target.lower() == "none"):
            problems.append(f"{r['cell_id']}: target_entity must be a QID or none")
    return problems


def reserves() -> None:
    rows = read_sheet()
    problems = check_rows(rows)
    if problems:
        raise SystemExit("\n".join(problems))
    requests, unfillable = {}, []
    for slot, r in sorted(latest(rows).items()):
        if r["action"].strip().lower() == "reject":
            if int(r["rank"]) >= MAX_RANK:
                unfillable.append(slot)
            else:
                requests[slot] = int(r["rank"]) + 1
    REQUESTS.write_text(json.dumps(requests, indent=2) + "\n")
    print(f"{REQUESTS.relative_to(ROOT)}: {len(requests)} reserve requests")
    if unfillable:
        # Both reserves rejected: the slot goes back to the author (0021 allows no further draws).
        print("slots with both reserves rejected, for the author to decide:", ", ".join(unfillable))


def split(queries: list[dict]) -> dict[str, str]:
    """40 dev: per language and type, systematic picks over the queries ordered by tier, so dev mirrors the tiers."""
    order = {"sparse": 0, "middle": 1, "rich": 2, "": 3}
    out = {}
    cells = defaultdict(list)
    for q in queries:
        cells[(q["language"], q["query_type"])].append(q)
    for (lang, qtype), members in sorted(cells.items()):
        rng = random.Random(f"{SPLIT_SEED}:{lang}:{qtype}")
        members = sorted(members, key=lambda q: (order[q["coverage_tier"]], rng.random()))
        k = DEV_PER_CELL[lang]
        step = len(members) / k
        start = rng.random() * step
        dev = {members[int(start + i * step)]["qid"] for i in range(k)}
        for q in members:
            out[q["qid"]] = "dev" if q["qid"] in dev else "test"
    return out


def finalize() -> None:
    from src.graph_retrieval.linker import link, load
    from src.queries.tiers import tier_of

    rows = read_sheet()
    problems = check_rows(rows)
    final = latest(rows)
    pending = [s for s, r in final.items() if r["action"].strip().lower() in ("", "reject")]
    if problems or pending:
        raise SystemExit("\n".join(problems + [f"slots without a kept or edited query: {', '.join(sorted(pending))}"]))

    gaz = load()
    targets = sorted({r["target_entity"].strip() for r in final.values() if QID.match(r["target_entity"].strip())})
    tiers = tier_of(targets)
    queries = []
    for slot, r in sorted(final.items()):
        text = r["edited_query"].strip() if r["action"].strip().lower() == "edit" else r["query"]
        target = r["target_entity"].strip()
        mentions = link(text, gaz)["mentions"]
        queries.append(
            {
                "qid": slot,
                "text": text,
                "language": r["language"],
                "query_type": r["query_type"],
                "style": r["style"],
                "cell_id": r["cell_id"],
                "target_entity": target if QID.match(target) else "",
                "coverage_tier": tiers.get(target, {}).get("tier", "") if QID.match(target) else "",
                "linkable": bool(mentions),
            }
        )
    assignment = split(queries)
    for q in queries:
        q["split"] = assignment[q["qid"]]
    for path, part in ((QUERIES, None), (DEV, "dev"), (TEST, "test")):
        with open(path, "w", encoding="utf-8") as f:
            for q in queries:
                if part is None or q["split"] == part:
                    f.write(json.dumps(q, ensure_ascii=False) + "\n")
    write_tsv(DEV_TSV, [q for q in queries if q["split"] == "dev"])
    with open(DEV_GROUPS, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t", lineterminator="\n")
        writer.writerow(["qid", "query_type", "language", "coverage_tier"])
        for q in queries:
            if q["split"] == "dev":
                writer.writerow([q["qid"], q["query_type"], q["language"], q["coverage_tier"] or "no entity"])

    actions = Counter(r["action"].strip().lower() for r in rows)
    sparse = Counter(q["split"] for q in queries if q["coverage_tier"] == "sparse")
    report = {
        "generated": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "commit": subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip(),
        "tiers": "provisional (decision 0031 fixes them on the frozen snapshot)",
        "curation": dict(actions),
        "queries": len(queries),
        "by_split": dict(Counter(q["split"] for q in queries)),
        "by_split_language_type": {
            f"{s}/{lang}/{t}": n
            for (s, lang, t), n in sorted(
                Counter((q["split"], q["language"], q["query_type"]) for q in queries).items()
            )
        },
        "by_split_tier": {
            f"{s}/{t or 'no entity'}": n
            for (s, t), n in sorted(Counter((q["split"], q["coverage_tier"]) for q in queries).items())
        },
        "sparse_quota": {
            s: {"needed": SPARSE_MIN[s], "have": sparse.get(s, 0), "met": sparse.get(s, 0) >= SPARSE_MIN[s]}
            for s in SPARSE_MIN
        },
        "linkable_share": {
            f"{lang}/{t}": round(sum(q["linkable"] for q in g) / len(g), 3)
            for (lang, t), g in sorted(_group(queries, ("language", "query_type")).items())
        },
        "linkable_share_overall": round(sum(q["linkable"] for q in queries) / len(queries), 3),
        "test_sha256": hashlib.sha256(TEST.read_bytes()).hexdigest(),
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.with_suffix(".json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    REPORT.with_suffix(".md").write_text(markdown(report))
    for s, q in report["sparse_quota"].items():
        if not q["met"]:
            print(f"sparse-tier quota not met in {s}: {q['have']} of {q['needed']}; top up from audit entries (0031)")
    print(f"{len(queries)} queries; split {report['by_split']}; test SHA-256 {report['test_sha256'][:16]}")


def write_tsv(path, queries: list[dict]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t", lineterminator="\n")
        for q in queries:
            # A tab or line break inside a query would break the runners' TSV reading.
            writer.writerow([q["qid"], q["language"], " ".join(q["text"].split())])


def _group(items: list[dict], keys: tuple[str, ...]) -> dict:
    out = defaultdict(list)
    for item in items:
        out[tuple(item[k] for k in keys)].append(item)
    return out


def markdown(report: dict) -> str:
    out = [
        "# Benchmark queries: curation and split",
        "",
        f"Generated by `src/queries/curation.py` on {report['generated'][:10]} at commit `{report['commit']}` "
        f"(decisions 0021, 0031). Coverage tiers are {report['tiers']}.",
        "",
        f"Curation actions over all rows: {', '.join(f'{k or "blank"} {v}' for k, v in report['curation'].items())}.",
        "",
        "| Split / language / type | Queries |",
        "| --- | --- |",
        *[f"| {k} | {v} |" for k, v in report["by_split_language_type"].items()],
        "",
        "| Split / coverage tier | Queries |",
        "| --- | --- |",
        *[f"| {k} | {v} |" for k, v in report["by_split_tier"].items()],
        "",
        "| Sparse-tier quota | Needed | Have | Met |",
        "| --- | --- | --- | --- |",
        *[
            f"| {s} | {q['needed']} | {q['have']} | {'yes' if q['met'] else 'no'} |"
            for s, q in report["sparse_quota"].items()
        ],
        "",
        f"Queries with a linkable entity: {report['linkable_share_overall']:.0%} overall.",
        "",
        "| Language / type | Share linkable |",
        "| --- | --- |",
        *[f"| {k} | {v:.0%} |" for k, v in report["linkable_share"].items()],
        "",
        f"Test file SHA-256: `{report['test_sha256']}`.",
    ]
    return "\n".join(out) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("step", choices=["sheet", "reserves", "finalize"])
    args = parser.parse_args()
    {"sheet": sheet, "reserves": reserves, "finalize": finalize}[args.step]()


if __name__ == "__main__":
    main()
