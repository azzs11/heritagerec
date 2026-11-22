"""Blind rating sheet and summary for the query generator trial (decision 0021).

The notebook `notebooks/query_generator_trial.ipynb` writes every model's backstory and query for the
30 trial cells. `sheet` shuffles them into one sheet that does not show the model; the author fills in
three columns per row. `summary` reads the filled sheet back and reports the ratings per model and
language. The item-to-model key is never written to disk: `summary` rebuilds it from the same seed,
so nothing in the folder tells the rater which model wrote what.

Usage:
    uv run python -m src.queries.generator_trial sheet
    (fill in fluency, fits_backstory and right_type in the sheet)
    uv run python -m src.queries.generator_trial summary

Files (results/queries/generator_trial_v1/):
    outputs.jsonl          from the notebook
    rating_sheet_v1.csv    for the author: fluency 1-3; fits_backstory and right_type yes or no
    summary_v1.json, .md   ratings per model and language
"""

import csv
import json
import random
import subprocess
import sys
from collections import defaultdict
from datetime import UTC, datetime

from src.corpus.wikimedia import ROOT

DIR = ROOT / "results/queries/generator_trial_v1"
OUTPUTS = DIR / "outputs.jsonl"
SHEET = DIR / "rating_sheet_v1.csv"
SUMMARY = DIR / "summary_v1"
SHUFFLE_SEED = 20261122
CELL_FIELDS = ["language", "query_type", "style", "role", "purpose", "area", "region", "period"]
RATINGS = ["fluency", "fits_backstory", "right_type"]
FLUENCY = {"1", "2", "3"}
YES_NO = {"yes", "no"}


def shown(path) -> str:
    return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)


def load_outputs() -> list[dict]:
    rows = [json.loads(line) for line in open(OUTPUTS, encoding="utf-8")]
    per_model = defaultdict(set)
    for r in rows:
        per_model[r["model"]].add(r["cell_id"])
    cells = set.union(*per_model.values())
    incomplete = {m: len(cells - c) for m, c in per_model.items() if c != cells}
    if incomplete:
        raise SystemExit(f"Some models are missing cells: {incomplete}")
    return sorted(rows, key=lambda r: (r["model"], r["cell_id"]))


def shuffled(rows: list[dict]) -> list[tuple[str, dict]]:
    order = list(rows)
    random.Random(SHUFFLE_SEED).shuffle(order)
    return [(f"R{i:02d}", r) for i, r in enumerate(order, 1)]


def sheet() -> None:
    if SHEET.exists():
        raise SystemExit(f"{shown(SHEET)} exists; it may hold ratings, so it is not overwritten")
    with open(SHEET, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["item", *CELL_FIELDS, "backstory", "query", *RATINGS, "notes"])
        for item, r in shuffled(load_outputs()):
            w.writerow([item, *(r["cell"][k] for k in CELL_FIELDS), r["backstory"], r["query"], "", "", "", ""])
    print(f"wrote {shown(SHEET)}")


def check(row: dict) -> list[str]:
    problems = []
    if row["fluency"].strip() not in FLUENCY:
        problems.append("fluency must be 1, 2 or 3")
    for k in ("fits_backstory", "right_type"):
        if row[k].strip().lower() not in YES_NO:
            problems.append(f"{k} must be yes or no")
    return problems


def summary() -> None:
    key = {item: r for item, r in shuffled(load_outputs())}
    rated = list(csv.DictReader(open(SHEET, encoding="utf-8")))
    problems = {row["item"]: p for row in rated if (p := check(row))}
    if problems:
        raise SystemExit(
            "Unfinished or invalid ratings:\n" + "\n".join(f"{i}: {', '.join(p)}" for i, p in problems.items())
        )
    if {row["item"] for row in rated} != set(key):
        raise SystemExit("The sheet's items do not match the outputs")

    groups = defaultdict(list)
    for row in rated:
        r = key[row["item"]]
        for lang in (r["cell"]["language"], "hi+kn" if r["cell"]["language"] != "en" else None, "all"):
            if lang:
                groups[(r["model"], lang)].append(row)

    def stats(rows: list[dict]) -> dict:
        n = len(rows)
        return {
            "items": n,
            "mean_fluency": round(sum(int(x["fluency"]) for x in rows) / n, 2),
            "fits_backstory": round(sum(x["fits_backstory"].strip().lower() == "yes" for x in rows) / n, 2),
            "right_type": round(sum(x["right_type"].strip().lower() == "yes" for x in rows) / n, 2),
        }

    models = sorted({m for m, _ in groups})
    langs = ["en", "hi", "kn", "hi+kn", "all"]
    table = {m: {lang: stats(groups[(m, lang)]) for lang in langs if groups[(m, lang)]} for m in models}
    revisions = {r["model"]: r["revision"] for r in key.values()}
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    report = {
        "date": datetime.now(UTC).date().isoformat(),
        "commit": commit,
        "revisions": revisions,
        "ratings": table,
    }
    SUMMARY.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Query generator trial: ratings by model and language",
        "",
        f"Generated by `src/queries/generator_trial.py` on {report['date']} at commit `{commit}` from the author's"
        " blind ratings in `rating_sheet_v1.csv` (decision 0021). Fluency is the mean on a 1–3 scale; the other two"
        " columns are the share of items rated yes.",
        "",
        "| Model | Revision | Language | Items | Fluency | Fits backstory | Right type |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for m in models:
        for lang, s in table[m].items():
            lines.append(
                f"| {m} | `{revisions[m][:10]}` | {lang} | {s['items']} | {s['mean_fluency']} |"
                f" {s['fits_backstory']} | {s['right_type']} |"
            )
    lines += [
        "",
        "Decision rule (0021): the model with the best Hindi and Kannada ratings (row `hi+kn`) is used; if none"
        " writes fluent Kannada, the choice goes back to the author.",
        "",
    ]
    SUMMARY.with_suffix(".md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    {"sheet": sheet, "summary": summary}[sys.argv[1] if len(sys.argv) > 1 else "sheet"]()
