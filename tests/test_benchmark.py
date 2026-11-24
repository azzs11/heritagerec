"""Tests for the evaluation harness (src/benchmark/evaluate.py) on small hand-made qrels and runs."""

import json
import math

import pytest

from src.benchmark.evaluate import evaluate, holm

# q1: d1 is directly about the query (3), d2 loosely related (1). q2: d5 clearly related (2).
# q3: nothing relevant was found, so it cannot be scored and must be reported as left out.
QRELS = "q1 0 d1 3\nq1 0 d2 1\nq2 0 d5 2\nq3 0 d9 0\n"
QUERIES = "q1\ten\tone\nq2\thi\ttwo\nq3\tkn\tthree\n"
PERFECT_Q1_ONLY = "q1 Q0 d1 1 2.0 a\nq1 Q0 d2 2 1.0 a\n"  # nothing for q2: must count as zero, not vanish
SWAPPED = "q1 Q0 d2 1 2.0 b\nq1 Q0 d1 2 1.0 b\nq1 Q0 dX 3 0.5 b\nq2 Q0 d5 1 1.0 b\n"


@pytest.fixture
def files(tmp_path):
    (tmp_path / "q.qrels").write_text(QRELS)
    (tmp_path / "q.tsv").write_text(QUERIES)
    (tmp_path / "a.trec").write_text(PERFECT_Q1_ONLY)
    (tmp_path / "b.trec").write_text(SWAPPED)
    (tmp_path / "groups.tsv").write_text("query_id\tlanguage\nq1\ten\nq2\thi\nq3\tkn\n")
    return tmp_path


def run(files, **kw):
    return evaluate(
        "t",
        kw.pop("split", "dev"),
        files / "q.qrels",
        files / "q.tsv",
        [files / "a.trec", files / "b.trec"],
        root=files,
        out_dir=files / "out",
        **kw,
    )


def test_a_query_the_run_missed_scores_zero_and_unscorable_queries_are_reported(files):
    s = run(files)
    assert s["queries_scored"] == 2 and s["queries_without_relevant_judgement"] == ["q3"]
    # a: q1 perfect (1.0), q2 missing (0.0)
    assert s["systems"]["a"]["measures"]["nDCG@10"]["mean"] == pytest.approx(0.5)
    assert s["systems"]["a"]["queries_answered"] == 1


def test_graded_ndcg_matches_the_hand_computed_value(files):
    s = run(files)
    # b, q1: gains 1 then 3 -> DCG = 1 + 3/log2(3); ideal 3 + 1/log2(3). q2 perfect.
    q1 = (1 + 3 / math.log2(3)) / (3 + 1 / math.log2(3))
    assert s["systems"]["b"]["measures"]["nDCG@10"]["mean"] == pytest.approx((q1 + 1) / 2, abs=1e-4)
    # Relevance for binary measures starts at grade 2: in q1 only d1 counts, found at rank 2.
    assert s["systems"]["b"]["measures"]["RR(rel=2)@10"]["mean"] == pytest.approx((0.5 + 1) / 2)


def test_unjudged_documents_in_the_top_10_are_counted(files):
    s = run(files)
    assert s["systems"]["a"]["unjudged_in_top10"] == 0
    assert s["systems"]["b"]["unjudged_in_top10"] == 1  # dX


def test_comparisons_are_corrected_and_repeatable(files):
    first = run(files, baseline="a")
    again = run(files, baseline="a")
    (c,) = first["comparisons"]
    assert c["system"] == "b" and c["p_holm"] >= c["p"]
    assert first["comparisons"] == again["comparisons"]
    assert holm([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.06, 0.06])


def test_groups_and_files_are_written(files):
    s = run(files, groups_path=files / "groups.tsv")
    assert s["groups"]["language"]["en"]["queries"] == 1 and "kn" not in s["groups"]["language"]
    out = files / "out" / "t"
    assert json.loads((out / "summary.json").read_text())["name"] == "t"
    assert len((out / "per_query.tsv").read_text().splitlines()) == 1 + 2 * 2


def test_the_test_split_is_refused_without_a_committed_analysis_plan(files):
    with pytest.raises(SystemExit, match="analysis_plan"):
        run(files, split="test")


def test_type_coverage_counts_distinct_known_types_in_the_top_ten():
    from src.benchmark.type_coverage import coverage

    types = {"a": "site", "b": "site", "c": "object", "d": "culture", "e": "unknown-kind"}
    assert coverage(["a", "b"], types) == 1 / 6
    assert coverage(["a", "c", "d", "e"], types) == 3 / 6  # an unknown type does not count
    assert coverage(["x"] * 3 + ["a"], types, k=3) == 0.0  # only the first k
