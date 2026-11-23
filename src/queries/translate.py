"""The translate-then-search control (decision 0019): Hindi and Kannada queries translated to English.

Steps:
    input      data/queries/translation_input_v1.tsv: every Hindi and Kannada query of the benchmark (dev and test
               alike, made at the same time; test runs still wait for the frozen analysis plan).
    check      After notebooks/query_translation.ipynb: every input query has exactly one translation. Writes the
               author's adequacy sheet (meaning kept, entity names right: yes or no), a separate file, so the
               machine output is never edited.
    runs       data/queries/translate_dev_v1.tsv for the runners: query id, "en", English text, dev queries only.
               BM25 then searches the English index, the dense models the whole corpus; the runs are named
               `<system>_translate_dev_v1` so pooling picks them up with the other dev runs.
    adequacy   The share of translations the author marked adequate, per language, with Wilson 95% intervals.

Usage:
    uv run python -m src.queries.translate input | check | runs | adequacy
Files:
    data/queries/translation_input_v1.tsv
    data/queries/translations_v1.tsv              from the notebook: query id, language, original, English
    data/queries/translations_v1.json             model, revision, toolkit version, settings, date
    data/queries/translation_adequacy_v1.csv      for the author
    data/queries/translate_dev_v1.tsv
    results/queries/translation_adequacy_v1.json
"""

import argparse
import csv
import json
from collections import Counter
from datetime import UTC, datetime

from statsmodels.stats.proportion import proportion_confint

from src.corpus.wikimedia import ROOT

QUERIES = ROOT / "data/queries/queries_v1.jsonl"
INPUT = ROOT / "data/queries/translation_input_v1.tsv"
TRANSLATIONS = ROOT / "data/queries/translations_v1.tsv"
ADEQUACY = ROOT / "data/queries/translation_adequacy_v1.csv"
RUN_INPUT = ROOT / "data/queries/translate_dev_v1.tsv"
REPORT = ROOT / "results/queries/translation_adequacy_v1.json"
SOURCE = ("hi", "kn")


def read_tsv(path) -> list[list[str]]:
    return list(csv.reader(open(path, encoding="utf-8"), delimiter="\t"))


def write_tsv(path, rows) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        csv.writer(f, delimiter="\t", lineterminator="\n").writerows(rows)


def queries() -> list[dict]:
    return [json.loads(line) for line in QUERIES.open(encoding="utf-8")]


def make_input() -> None:
    rows = [[q["qid"], q["language"], " ".join(q["text"].split())] for q in queries() if q["language"] in SOURCE]
    write_tsv(INPUT, rows)
    print(f"{INPUT.relative_to(ROOT)}: {len(rows)} queries ({dict(Counter(r[1] for r in rows))})")


def check() -> None:
    wanted = {r[0]: r for r in read_tsv(INPUT)}
    got = Counter(r[0] for r in read_tsv(TRANSLATIONS))
    problems = [f"{q}: {got[q]} translations" for q in wanted if got[q] != 1]
    problems += [f"{q}: not an input query" for q in got if q not in wanted]
    empty = [r[0] for r in read_tsv(TRANSLATIONS) if not r[3].strip()]
    problems += [f"{q}: empty translation" for q in empty]
    if problems:
        raise SystemExit("\n".join(problems))
    if ADEQUACY.exists() and any(r["adequate"].strip() for r in csv.DictReader(ADEQUACY.open(encoding="utf-8-sig"))):
        print(f"translations complete; {ADEQUACY.name} already has the author's marks and is kept")
        return
    with open(ADEQUACY, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["qid", "language", "original", "english", "adequate", "notes"])
        writer.writeheader()
        for qid, lang, original, english in read_tsv(TRANSLATIONS):
            writer.writerow(
                {"qid": qid, "language": lang, "original": original, "english": english, "adequate": "", "notes": ""}
            )
    print(f"translations complete: {len(wanted)}; {ADEQUACY.relative_to(ROOT)} written for the author")


def runs() -> None:
    dev = {q["qid"] for q in queries() if q["split"] == "dev"}
    rows = [[qid, "en", " ".join(english.split())] for qid, _, _, english in read_tsv(TRANSLATIONS) if qid in dev]
    write_tsv(RUN_INPUT, rows)
    print(f"{RUN_INPUT.relative_to(ROOT)}: {len(rows)} dev queries")


def adequacy() -> None:
    rows = list(csv.DictReader(ADEQUACY.open(encoding="utf-8-sig")))
    bad = [r["qid"] for r in rows if r["adequate"].strip().lower() not in ("yes", "no")]
    if bad:
        raise SystemExit(f"adequate must be yes or no: {', '.join(bad)}")
    report = {"generated": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), "by_language": {}}
    for lang in SOURCE:
        group = [r for r in rows if r["language"] == lang]
        k = sum(r["adequate"].strip().lower() == "yes" for r in group)
        lo, hi = proportion_confint(k, len(group), alpha=0.05, method="wilson") if group else (None, None)
        report["by_language"][lang] = {
            "adequate": k,
            "of": len(group),
            "share": round(k / len(group), 3) if group else None,
            "ci95": [round(float(lo), 3), round(float(hi), 3)] if group else None,
        }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report["by_language"]))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("step", choices=["input", "check", "runs", "adequacy"])
    {"input": make_input, "check": check, "runs": runs, "adequacy": adequacy}[p.parse_args().step]()


if __name__ == "__main__":
    main()
