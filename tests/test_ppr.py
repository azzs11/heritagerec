"""Tests for personalised PageRank (src/graph_retrieval/ppr.py), checked against networkx's own implementation."""

import networkx as nx
import numpy as np
import pytest

from src.graph_retrieval.ppr import build, parse_seeds, rank_documents, scores

# A small heritage-shaped graph: a dynasty, its two temples, a century hub everything touches,
# documents about each temple, and one document about the century only.
IDS = ["c:12", "d:a", "d:b", "d:hub", "e:dyn", "e:t1", "e:t2", "e:other", "d:other"]
DOCS = {"d:a", "d:b", "d:hub", "d:other"}
PAIRS = {
    ("e:dyn", "e:t1"),
    ("e:dyn", "e:t2"),
    ("d:a", "e:t1"),
    ("d:b", "e:t2"),
    ("c:12", "e:t1"),
    ("c:12", "e:t2"),
    ("c:12", "e:other"),
    ("c:12", "d:hub"),
    ("d:other", "e:other"),
}


def walk(hub_power):
    ids = sorted(IDS)
    return build(ids, [i in DOCS for i in ids], {(min(a, b), max(a, b)) for a, b in PAIRS}, hub_power)


def networkx_ppr(seeds, restart, hub_power):
    g = nx.DiGraph()
    und = nx.Graph(list(PAIRS))
    for u, v in und.edges():
        for a, b in ((u, v), (v, u)):
            g.add_edge(a, b, w=und.degree(b) ** -hub_power)
    return nx.pagerank(g, alpha=1 - restart, personalization=seeds, weight="w", tol=1e-14, max_iter=1000)


@pytest.mark.parametrize("hub_power", [0.0, 0.5, 1.0])
@pytest.mark.parametrize("seeds", [{"e:dyn": 1.0}, {"e:t1": 1.0, "e:other": 3.0}])
def test_matches_networkx(hub_power, seeds):
    w = walk(hub_power)
    ours = scores(w, seeds, restart=0.15)
    theirs = networkx_ppr(seeds, 0.15, hub_power)
    for node, value in theirs.items():
        assert ours[w.index[node]] == pytest.approx(value, abs=1e-8)
    assert ours.sum() == pytest.approx(1.0)


def test_down_weighting_hubs_moves_mass_away_from_the_hub():
    seeds = {"e:t1": 1.0}
    plain, weighted = walk(0.0), walk(1.0)
    hub_doc_plain = scores(plain, seeds)[plain.index["d:hub"]]
    hub_doc_weighted = scores(weighted, seeds)[weighted.index["d:hub"]]
    assert hub_doc_weighted < hub_doc_plain


def test_documents_are_ranked_deterministically_and_unknown_seeds_give_nothing():
    w = walk(1.0)
    ranked = rank_documents(w, scores(w, {"e:dyn": 1.0}))
    assert [d for d, _ in ranked][:2] == ["d:a", "d:b"]  # the two temples' documents tie; id breaks the tie
    assert ranked[0][1] == pytest.approx(ranked[1][1])
    assert rank_documents(w, scores(w, {"Q-not-in-graph": 1.0})) == []


def test_a_node_without_edges_sends_the_walk_back_to_the_seeds():
    ids = ["a", "b", "lonely"]
    w = build(ids, [False, True, False], {("a", "b")}, 1.0)
    x = scores(w, {"lonely": 1.0, "a": 1.0})
    assert x.sum() == pytest.approx(1.0) and np.all(x >= 0)


def test_seed_strings():
    assert parse_seeds("Q1;Q2") == {"Q1": 1.0, "Q2": 1.0}
    assert parse_seeds("Q1:0.25; Q2:0.75;") == {"Q1": 0.25, "Q2": 0.75}
