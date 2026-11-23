"""Tests for the judge prompt and the pool, pilot, agreement and qrels steps (src/benchmark/, decision 0022)."""

import csv
import gzip
import json

import pytest

from src.benchmark import judging
from src.benchmark.judge_prompt import TEXT_WORDS, cut, judge_prompt, parse, template_sha256


def test_prompt_carries_only_query_title_and_cut_text():
    text = " ".join(f"w{i}" for i in range(TEXT_WORDS + 50))
    p = judge_prompt("Hoysala temples", "Chennakeshava Temple, Belur", text)
    assert "Query: Hoysala temples" in p and "Document title: Chennakeshava Temple, Belur" in p
    assert f"w{TEXT_WORDS - 1}" in p and f"w{TEXT_WORDS}" not in p and p.count("…") == 1
    assert "##final score" in p and "{" not in p  # every placeholder filled
    assert cut("a b c", 5) == "a b c"
    assert len(template_sha256()) == 64


def test_parse_takes_the_last_valid_score_line():
    assert parse("Directly about Belur.\n##final score: 3") == (3, "Directly about Belur.")
    assert parse("Loosely related.\n## Final Score : 1") == (1, "Loosely related.")
    assert parse("x ##final score: 2 then ##final score: 0") == (0, "x ##final score: 2 then")
    assert parse("no score here")[0] is None
    assert parse("##final score: 5")[0] is None  # outside the scale


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    for name, sub in (("DATA", "data/judging"), ("RESULTS", "results/judging"), ("QRELS", "data/qrels"),
                      ("RUNS", "runs"), ("QUERIES", "queries")):  # fmt: skip
        (tmp_path / sub).mkdir(parents=True)
        monkeypatch.setattr(judging, name, tmp_path / sub)
    monkeypatch.setattr(judging, "ROOT", tmp_path)
    records = tmp_path / "records.jsonl.gz"
    with gzip.open(records, "wt", encoding="utf-8") as f:
        for i in range(30):
            f.write(json.dumps({"id": f"d{i}", "title": f"Doc {i}", "text": f"text {i}", "language": "en"}) + "\n")
    monkeypatch.setattr(judging, "RECORDS", records)
    queries = [("q1", "en"), ("q2", "hi"), ("q3", "kn")]
    with open(tmp_path / "queries/dev_v1.jsonl", "w", encoding="utf-8") as f:
        for qid, lang in queries:
            f.write(json.dumps({"qid": qid, "language": lang, "text": f"query {qid}"}) + "\n")
    for run, offset in (("bm25", 0), ("e5", 5)):
        with open(tmp_path / f"runs/{run}_dev_v1.trec", "w") as f:
            for qid, _ in queries:
                for rank in range(1, 16):
                    f.write(f"{qid} Q0 d{rank + offset} {rank} {20 - rank} {run}\n")
    return tmp_path


def read_jsonl(path):
    return [json.loads(line) for line in open(path, encoding="utf-8")]


def test_pool_is_the_union_of_top_ten_with_best_ranks(workspace):
    judging.pool("dev", 10, [])
    rows = read_jsonl(workspace / "data/judging/dev_pool_v1.jsonl")
    # bm25 gives d1-d10, e5 gives d6-d15: 15 documents per query, 3 queries.
    assert len(rows) == 45
    d6 = next(r for r in rows if r["qid"] == "q1" and r["doc_id"] == "d6")
    assert d6["best_rank"] == 1 and d6["runs"] == {"bm25_dev_v1": 6, "e5_dev_v1": 1}
    assert len({r["pair_id"] for r in rows}) == 45
    report = json.loads((workspace / "results/judging/dev_pool_v1.json").read_text())
    assert report["pairs"] == 45 and report["new_pairs"] == 45 and set(report["runs"]) == {"bm25_dev_v1", "e5_dev_v1"}
    judging.pool("dev", 10, [])  # re-pooling keeps the ids, so nothing is new
    assert json.loads((workspace / "results/judging/dev_pool_v1.json").read_text())["new_pairs"] == 0
    with pytest.raises(SystemExit):
        judging.pool("test", 10, [])  # test pools wait for phase 2


def test_pilot_sheet_is_blind_and_never_rewritten(workspace, monkeypatch):
    monkeypatch.setattr(judging, "PILOT", {"en": 6, "hi": 4, "kn": 4})
    judging.pool("dev", 10, [])
    judging.pilot("dev")
    path = workspace / "data/judging/dev_pilot_sheet_v1.csv"
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    assert len(rows) == 14
    assert list(rows[0]) == ["pair_id", "query", "title", "text", "label", "notes"]  # no runs, ranks or labels
    rows[0]["label"] = "2"
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(SystemExit):
        judging.pilot("dev")


def test_agreement_and_qrels_from_the_judgements(workspace, monkeypatch):
    monkeypatch.setattr(judging, "PILOT", {"en": 4, "hi": 2, "kn": 2})
    judging.pool("dev", 10, [])
    judging.pilot("dev")
    sheet_path = workspace / "data/judging/dev_pilot_sheet_v1.csv"
    sheet = list(csv.DictReader(open(sheet_path, encoding="utf-8")))
    for i, r in enumerate(sheet):
        r["label"] = str(i % 4)
    with open(sheet_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(sheet[0]))
        writer.writeheader()
        writer.writerows(sheet)
    pool_rows = read_jsonl(workspace / "data/judging/dev_pool_v1.jsonl")
    author = {r["pair_id"]: int(r["label"]) for r in sheet}
    with open(workspace / "results/judging/dev_judgements_v1.jsonl", "w", encoding="utf-8") as f:
        for r in pool_rows[:-1]:  # the last pair is not judged yet
            label = author.get(r["pair_id"], 1)
            f.write(json.dumps({"pair_id": r["pair_id"], "label": label, "model": "m", "revision": "r"}) + "\n")
        # One output with no score line, then its rerun: the rerun replaces it.
        f.write(json.dumps({"pair_id": pool_rows[0]["pair_id"], "label": None}) + "\n")
        f.write(
            json.dumps({"pair_id": pool_rows[0]["pair_id"], "label": author.get(pool_rows[0]["pair_id"], 1)}) + "\n"
        )
    judging.agreement("dev")
    report = json.loads((workspace / "results/judging/dev_pilot_agreement_v1.json").read_text())
    assert report["overall"]["n"] == 8 and report["overall"]["raw_agreement"] == 1.0
    assert report["overall"]["weighted_kappa_linear"] == 1.0
    judging.qrels("dev")
    lines = (workspace / "data/qrels/dev_v1.qrels").read_text().splitlines()
    assert len(lines) == len(pool_rows) - 1 and lines[0].split()[1] == "0"
