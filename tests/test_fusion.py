"""Tests for reciprocal rank fusion (src/retrieval/fusion.py, decision 0008)."""

import pytest

from src.retrieval.fusion import K, fuse, read_ranks


def test_rrf_sums_one_over_k_plus_rank_and_breaks_ties_by_id():
    a = {"q1": {"d1": 1, "d2": 2}}
    b = {"q1": {"d2": 1, "d3": 2}}
    ranked = dict(fuse([a, b])["q1"])
    assert ranked["d2"] == pytest.approx(1 / (K + 2) + 1 / (K + 1))
    assert ranked["d1"] == pytest.approx(1 / (K + 1))
    order = [d for d, _ in fuse([a, b])["q1"]]
    assert order == ["d2", "d1", "d3"]
    # Equal scores: the document id decides, so the result never depends on input order.
    assert [d for d, _ in fuse([{"q": {"b": 1}}, {"q": {"a": 1}}])["q"]] == ["a", "b"]


def test_a_query_missing_from_one_run_still_gets_the_other_runs_documents():
    fused = fuse([{"q1": {"d1": 1}}, {"q2": {"d9": 1}}])
    assert set(fused) == {"q1", "q2"} and fused["q2"][0][0] == "d9"


def test_ranks_are_reread_from_scores_like_trec_eval(tmp_path):
    run = tmp_path / "r.trec"
    # The file's rank column disagrees with the scores; trec_eval orders by score, then id.
    run.write_text("q1 Q0 dB 1 0.5 r\nq1 Q0 dA 2 0.5 r\nq1 Q0 dC 3 0.9 r\n")
    assert read_ranks(run) == {"q1": {"dC": 1, "dA": 2, "dB": 3}}
