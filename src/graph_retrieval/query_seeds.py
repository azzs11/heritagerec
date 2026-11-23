"""Seeds for the graph runs: each query's linked entities, as the PageRank runner reads them (decisions 0026, 0027).

Reads a query TSV (query id, language, text; the file the BM25 and dense runners read), links every query with the
gazetteer linker, and writes the seeds TSV `src.graph_retrieval.ppr --queries` takes: query id, then
`Q1:weight;Q2:weight`. A query with no linked entity gets an empty seed list, so the graph run returns nothing for
it and the evaluation scores it zero (src.benchmark.evaluate counts it, it is not dropped). The report gives the
linked share overall and per language, and how the mentions were matched.

Usage:
    uv run python -m src.graph_retrieval.query_seeds --queries data/queries/dev_v1.tsv
Outputs:
    data/queries/<stem>_seeds.tsv
    results/retrieval/seeds_<stem>.json
"""

import argparse
import csv
import json
import subprocess
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from src.corpus.wikimedia import ROOT
from src.graph_retrieval.linker import link, load

REPORTS = ROOT / "results/retrieval"


def seeds_cell(seeds: dict[str, float]) -> str:
    return ";".join(f"{q}:{w:.6f}" for q, w in sorted(seeds.items()))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--queries", type=Path, required=True)
    a = p.parse_args()
    rows = list(csv.reader(open(a.queries, encoding="utf-8"), delimiter="\t"))
    gaz = load()
    out = a.queries.with_name(f"{a.queries.stem}_seeds.tsv")
    linked, methods, by_lang = 0, Counter(), Counter()
    total_lang = Counter(lang for _, lang, _ in rows)
    with open(out, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t", lineterminator="\n")
        for qid, lang, text in rows:
            result = link(text, gaz)
            writer.writerow([qid, seeds_cell(result["seeds"])])
            if result["seeds"]:
                linked += 1
                by_lang[lang] += 1
            methods.update(m["method"] for m in result["mentions"])
    report = {
        "generated": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "commit": subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip(),
        "queries": len(rows),
        "with_seeds": linked,
        "with_seeds_by_language": {lang: f"{by_lang[lang]} of {n}" for lang, n in sorted(total_lang.items())},
        "mentions_by_method": dict(methods),
        "seeds_file": str(out.relative_to(ROOT)),
    }
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / f"seeds_{a.queries.stem}.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"{out.relative_to(ROOT)}: {linked} of {len(rows)} queries have seeds")


if __name__ == "__main__":
    main()
