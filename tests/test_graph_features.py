"""Tests for the graph features of decision 0036 (src/graph_retrieval/features.py) on a graph small enough to check by hand."""

import math
from collections import Counter

import pytest

from src.graph_retrieval.features import GraphIndex, horn, pair_features, seed_documents, simrank

#   d1 -about-> e1 -P53-> dyn <-P53- e2 <-about- d2       (e1 and e2 share a dynasty)
#   d3 -about-> e3 -P131-> place                         (shares nothing with e1)
#   e1, e2, e3 -in_period-> century:12                    (a hub: everyone shares it)
EDGES = [
    ("d1", "about", "e1"),
    ("d2", "about", "e2"),
    ("d3", "about", "e3"),
    ("e1", "P53", "dyn"),
    ("e2", "P53", "dyn"),
    ("e3", "P131", "place"),
    ("e1", "in_period", "century:12"),
    ("e2", "in_period", "century:12"),
    ("e3", "in_period", "century:12"),
]


@pytest.fixture
def g():
    return GraphIndex(EDGES, documents={"d1", "d2", "d3"}, hubs={"century:12"})


def test_horn_is_one_for_proportional_and_zero_for_disjoint():
    assert horn(Counter(a=2, b=2), Counter(a=1, b=1)) == pytest.approx(1.0)
    assert horn(Counter(a=1), Counter(b=1)) == 0.0
    assert horn(Counter(), Counter(a=1)) == 0.0
    assert 0 < horn(Counter(a=2, b=1), Counter(a=1, c=1)) < 1


def test_meta_paths_count_the_family_and_weigh_down_common_nodes(g):
    seeds = {"e1"}
    d1, d2, d3 = (pair_features(g, d, seeds) for d in ("d1", "d2", "d3"))
    assert d1["overlap"] == 1.0 and d2["overlap"] == 0.0
    # d2 shares the dynasty (degree 2): weight 1 / log 3.
    assert d2["mp_dynasty"] == pytest.approx(1 / math.log(3))
    assert d3["mp_dynasty"] == 0.0 and d3["mp_place"] == 0.0
    # Everyone shares the century; it counts, but less than the dynasty (degree 3).
    assert 0 < d3["mp_period"] < d2["mp_dynasty"]
    # The direct overlap is not counted again as a meta-path.
    assert d1["mp_dynasty"] == pytest.approx(1 / math.log(3))


def test_simrank_rewards_a_shared_dynasty_and_gives_nothing_to_an_unrelated_document(g):
    assert seed_documents(g, {"e1"}) == ["d1"]
    sr = simrank(g, ["d1", "d2", "d3"], {"e1"})
    assert sr["d1"] == 1.0  # a seed document itself
    assert sr["d2"] > 0.0  # d2 - e2 - dyn - e1 - d1
    assert sr["d3"] == 0.0  # only the hub century joins e3 to e1, and hubs are kept out of the subgraph
    assert simrank(g, ["d2"], set()) == {"d2": 0.0}
