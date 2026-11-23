"""Tests for the translate-then-search control's files (src/queries/translate.py, decision 0019)."""

import csv
import json

import pytest

from src.queries import translate


@pytest.fixture
def files(tmp_path, monkeypatch):
    for name, file in (("QUERIES", "queries.jsonl"), ("INPUT", "input.tsv"), ("TRANSLATIONS", "translations.tsv"),
                       ("ADEQUACY", "adequacy.csv"), ("RUN_INPUT", "translate_dev_v1.tsv"), ("REPORT", "report.json")):  # fmt: skip
        monkeypatch.setattr(translate, name, tmp_path / file)
    monkeypatch.setattr(translate, "ROOT", tmp_path)
    queries = [
        {"qid": "q001", "language": "en", "text": "Hoysala temples", "split": "dev"},
        {"qid": "q161", "language": "hi", "text": "खजुराहो के\tमंदिर", "split": "dev"},
        {"qid": "q162", "language": "hi", "text": "मुगल चित्रकला", "split": "test"},
        {"qid": "q181", "language": "kn", "text": "ಹಂಪಿ ದೇವಾಲಯಗಳು", "split": "dev"},
    ]
    (tmp_path / "queries.jsonl").write_text(
        "".join(json.dumps(q, ensure_ascii=False) + "\n" for q in queries), encoding="utf-8"
    )
    return tmp_path


def write_translations(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        csv.writer(f, delimiter="\t", lineterminator="\n").writerows(rows)


def test_input_has_every_hindi_and_kannada_query_of_both_splits(files):
    translate.make_input()
    rows = translate.read_tsv(files / "input.tsv")
    assert [r[0] for r in rows] == ["q161", "q162", "q181"]
    assert rows[0][2] == "खजुराहो के मंदिर"  # a tab inside a query would break the file


def test_check_needs_exactly_one_translation_each(files):
    translate.make_input()
    write_translations(
        files / "translations.tsv", [["q161", "hi", "x", "Khajuraho temples"], ["q181", "kn", "y", "Hampi temples"]]
    )
    with pytest.raises(SystemExit):
        translate.check()  # q162 is missing
    write_translations(
        files / "translations.tsv",
        [
            ["q161", "hi", "x", "Khajuraho temples"],
            ["q162", "hi", "y", "Mughal painting"],
            ["q181", "kn", "z", "Hampi temples"],
        ],
    )
    translate.check()
    sheet = list(csv.DictReader(open(files / "adequacy.csv", encoding="utf-8")))
    assert [r["qid"] for r in sheet] == ["q161", "q162", "q181"] and all(r["adequate"] == "" for r in sheet)


def test_run_input_is_english_and_dev_only_and_adequacy_is_reported(files):
    translate.make_input()
    write_translations(
        files / "translations.tsv",
        [
            ["q161", "hi", "x", "Khajuraho temples"],
            ["q162", "hi", "y", "Mughal painting"],
            ["q181", "kn", "z", "Hampi temples"],
        ],
    )
    translate.check()
    translate.runs()
    assert translate.read_tsv(files / "translate_dev_v1.tsv") == [
        ["q161", "en", "Khajuraho temples"],
        ["q181", "en", "Hampi temples"],
    ]
    sheet = list(csv.DictReader(open(files / "adequacy.csv", encoding="utf-8")))
    for r, mark in zip(sheet, ["yes", "no", "yes"], strict=True):
        r["adequate"] = mark
    with open(files / "adequacy.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(sheet[0]))
        writer.writeheader()
        writer.writerows(sheet)
    translate.check()  # the marked sheet is kept, never rewritten
    assert list(csv.DictReader(open(files / "adequacy.csv", encoding="utf-8")))[0]["adequate"] == "yes"
    translate.adequacy()
    report = json.loads((files / "report.json").read_text())
    assert report["by_language"]["hi"]["adequate"] == 1 and report["by_language"]["hi"]["of"] == 2
    assert report["by_language"]["kn"]["share"] == 1.0
