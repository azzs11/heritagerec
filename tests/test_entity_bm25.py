"""Tests for the entity-expanded BM25 control (src/retrieval/entity_bm25.py, decision 0033); no Java needed."""

import pytest

from src.graph_retrieval.linker import load
from src.retrieval.entity_bm25 import alpha_tag, entity_names, merge, min_max, weighted_terms


def test_names_share_alpha_times_the_query_weight_however_many_there_are():
    terms = weighted_terms(["hoysala", "templ"], ["hoysala", "empir", "belur", "beluhur"], 0.5)
    query = [w for t, w in terms[:2]]
    names = [w for t, w in terms[2:]]
    assert query == [1.0, 1.0]
    assert sum(names) == pytest.approx(0.5 * 2)  # alpha times the query's total weight
    # A twenty-alias entity weighs the same in total as a one-name entity.
    many = weighted_terms(["a"], [f"n{i}" for i in range(20)], 1.0)
    assert sum(w for _, w in many[1:]) == pytest.approx(1.0)


def test_an_index_in_another_language_searches_the_names_alone_and_no_terms_means_no_search():
    assert weighted_terms([], ["ಹೊಯ್ಸಳ"], 0.5) == [("ಹೊಯ್ಸಳ", 1.0)]
    assert weighted_terms([], [], 0.5) == []
    assert weighted_terms(["x", "x"], ["x"], 1.0)[0] == ("x", 1.0)  # repeated terms count once


def test_min_max_and_a_merge_that_does_not_favour_english():
    assert min_max([("a", 4.0), ("b", 2.0), ("c", 0.0)]) == [("a", 1.0), ("b", 0.5), ("c", 0.0)]
    assert min_max([("a", 3.0)]) == [("a", 1.0)]
    per_index = {
        "en": [("wikipedia:en:1", 9.0), ("wikipedia:en:2", 1.0)],
        "hi": [("wikipedia:hi:1", 5.0), ("wikipedia:hi:2", 1.0)],
    }
    # Both top documents scale to 1.0; the query's own language comes first, whichever it is.
    assert [d for d, _ in merge(per_index, "hi")][:2] == ["wikipedia:hi:1", "wikipedia:en:1"]
    assert [d for d, _ in merge(per_index, "en")][:2] == ["wikipedia:en:1", "wikipedia:hi:1"]
    assert merge(per_index, "en", depth=3)[-1][1] == 0.0


def test_expansion_uses_the_names_the_linker_trusts():
    seeds, names = entity_names("Hoysala temples at Belur")
    g = load()
    assert seeds and all(q in g.names for q in seeds)
    for lang, ns in names.items():
        for q in seeds:
            assert set(g.names[q].get(lang, [])) <= set(ns)
    assert entity_names("how were these made") == ([], {})
    assert alpha_tag(0.25) == "a025" and alpha_tag(1.0) == "a100"
