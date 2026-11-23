"""Tests for the coverage-tier analysis (src/benchmark/tier_analysis.py, decision 0031)."""

import numpy as np
import pytest

from src.benchmark.tier_analysis import analyse, interaction, markdown, regression


def queries_and_values(n=12):
    """Graph beats text by 0.3 on rich queries and by nothing on sparse ones."""
    queries, graph, text = [], {}, {}
    for i in range(n):
        tier = ["rich", "middle", "sparse"][i % 3]
        score = {"rich": 0.8, "middle": 0.5, "sparse": 0.2}[tier] + i * 0.001
        qid = f"q{i:03d}"
        queries.append({"qid": qid, "coverage_tier": tier, "coverage_score": score})
        text[qid] = 0.4
        graph[qid] = 0.4 + {"rich": 0.3, "middle": 0.15, "sparse": 0.0}[tier]
    queries.append({"qid": "q900", "coverage_tier": "", "coverage_score": None})
    graph["q900"], text["q900"] = 0.0, 0.5
    return queries, {"ppr": graph, "bm25": text}


def test_tiers_interaction_and_regression_point_the_right_way():
    queries, per_query = queries_and_values()
    r = analyse(per_query, queries, "ppr", "bm25")
    assert r["by_tier"]["rich"]["difference"]["mean"] == pytest.approx(0.3)
    assert r["by_tier"]["sparse"]["difference"]["mean"] == pytest.approx(0.0)
    assert r["by_tier"]["no entity"]["queries"] == 1  # scored, never dropped
    assert r["interaction_sparse_vs_rich"]["sparse_minus_rich"] == pytest.approx(-0.3)
    assert r["regression_on_coverage_score"]["slope"] > 0  # more coverage, bigger graph advantage
    assert r["regression_on_coverage_score"]["queries"] == 12  # the no-entity query has no score
    assert "| sparse | 4 |" in markdown(r, "dev_v1")


def test_interaction_p_is_one_for_identical_groups_and_small_for_separated_ones():
    assert interaction(np.zeros(5), np.zeros(5)) == 1.0
    assert interaction(np.zeros(8), np.ones(8)) < 0.01


def test_regression_recovers_a_known_slope():
    x = np.linspace(0, 1, 20)
    r = regression(x, 2 * x + 1)
    assert r["slope"] == pytest.approx(2.0) and r["intercept"] == pytest.approx(1.0)


def test_unknown_system_is_refused():
    queries, per_query = queries_and_values()
    with pytest.raises(SystemExit):
        analyse(per_query, queries, "simrank", "bm25")
