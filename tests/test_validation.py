"""Tests for the 15-query human validation (src/benchmark/validation.py)."""

import csv
import gzip
import json

import pytest

from src.benchmark import validation

TYPES = ["simple", "entity", "concept", "complex"]


@pytest.fixture
def ws(tmp_path, monkeypatch):
    for name, sub in (("DATA", "data"), ("RESULTS", "results"), ("RUNS", "runs")):
        (tmp_path / sub).mkdir()
        monkeypatch.setattr(validation, name, tmp_path / sub)
    monkeypatch.setattr(validation, "ROOT", tmp_path)
    monkeypatch.setattr(validation, "SELECTED", tmp_path / "data/validation_queries_v1.json")
    monkeypatch.setattr(validation, "JUDGEMENTS", tmp_path / "results/test_judgements_v1.jsonl")
    queries = []
    for i in range(40):
        lang = "hi" if i < 4 else "kn" if i < 8 else "en"
        tier = "sparse" if i % 7 == 0 else "rich"
        queries.append(
            {
                "qid": f"t{i:03d}",
                "language": lang,
                "query_type": TYPES[i % 4],
                "coverage_tier": tier,
                "text": f"query {i}",
            }
        )
    (tmp_path / "test.jsonl").write_text("".join(json.dumps(q) + "\n" for q in queries))
    monkeypatch.setattr(validation, "QUERIES", tmp_path / "test.jsonl")
    with gzip.open(tmp_path / "records.jsonl.gz", "wt") as f:
        for d in range(20):
            f.write(json.dumps({"id": f"d{d}", "title": f"Doc {d}", "text": "words " * 900}) + "\n")
    monkeypatch.setattr(validation, "RECORDS", tmp_path / "records.jsonl.gz")
    for run, offset in (("bm25_test_v1", 0), ("ppr_test_v1", 3)):
        with open(tmp_path / f"runs/{run}.trec", "w") as f:
            for q in queries:
                for rank in range(1, 9):
                    f.write(f"{q['qid']} Q0 d{rank + offset} {rank} {10 - rank} {run}\n")
    return tmp_path


def test_selection_meets_the_language_and_sparse_quotas(ws):
    validation.select()
    chosen = json.loads((ws / "data/validation_queries_v1.json").read_text())
    assert len(chosen["queries"]) == 15 and chosen["sparse"] >= 4
    ids = set(chosen["queries"])
    assert (
        sum(1 for i in range(4) if f"t{i:03d}" in ids) == 2 and sum(1 for i in range(4, 8) if f"t{i:03d}" in ids) == 2
    )


def test_sheets_are_blind_identical_in_order_and_agreement_is_computed(ws):
    validation.select()
    validation.sheet("author", [])
    validation.sheet("second", [])
    a = list(csv.DictReader(open(ws / "data/validation_author_v1.csv", encoding="utf-8")))
    b = list(csv.DictReader(open(ws / "data/validation_second_v1.csv", encoding="utf-8")))
    assert [r["pair_id"] for r in a] == [r["pair_id"] for r in b]
    assert list(a[0]) == ["pair_id", "query", "title", "text", "label", "notes"]
    assert len(a) == 15 * 8  # top 5 of two runs offset by 3: 8 documents per query
    labels = {r["pair_id"]: str(i % 4) for i, r in enumerate(a)}
    for name, rows in (("author", a), ("second", b)):
        for r in rows:
            r["label"] = labels[r["pair_id"]]
        with open(ws / f"data/validation_{name}_v1.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    with pytest.raises(SystemExit):
        validation.sheet("author", [])  # labelled: never rewritten
    with open(ws / "results/test_judgements_v1.jsonl", "w") as f:
        for pid, lab in labels.items():
            f.write(json.dumps({"pair_id": pid, "label": int(lab)}) + "\n")
    validation.agreement()
    report = json.loads((ws / "results/validation_agreement_v1.json").read_text())
    assert report["llm_vs"]["author"]["overall"]["weighted_kappa_linear"] == 1.0
    assert report["human_vs_human"]["overall"]["raw_agreement"] == 1.0
    assert set(report["llm_vs"]["author"]["by_system"]) == {"bm25_test_v1", "ppr_test_v1"}
    assert report["llm_vs"]["author"]["by_system"]["bm25_test_v1"]["n"] == 15 * 5
