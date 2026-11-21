"""Tests for the core graph builder in src/graph/core_graph.py (no network)."""

from src.graph.core_graph import build, centuries, century, century_label, item_values, truthy, year_of


def item(target: str, rank: str = "normal") -> dict:
    return {
        "rank": rank,
        "mainsnak": {"snaktype": "value", "datatype": "wikibase-item", "datavalue": {"value": {"id": target}}},
    }


def entity(qid: str, rev: int = 1, **claims) -> dict:
    return {"id": qid, "lastrevid": rev, "claims": {p: [item(t) for t in ts] for p, ts in claims.items()}}


def test_truthy_prefers_preferred_and_never_deprecated():
    assert truthy([item("Q1"), item("Q2", "preferred")]) == [item("Q2", "preferred")]
    assert truthy([item("Q1"), item("Q2", "deprecated")]) == [item("Q1")]
    unknown = {"rank": "normal", "mainsnak": {"snaktype": "somevalue", "datatype": "wikibase-item"}}
    assert item_values({"P84": [unknown, item("Q3")]}, "P84") == ["Q3"]


def test_centuries_follow_the_usual_numbering():
    assert year_of("+1650-00-00T00:00:00Z") == 1650
    assert year_of("-0300-00-00T00:00:00Z") == -300
    assert [century(y) for y in (1, 100, 101, 1700, 1701)] == [1, 1, 2, 17, 18]
    assert [century(y) for y in (-1, -100, -101, 0)] == [-1, -1, -2, -1]
    assert centuries(-150, 50) == [-2, -1, 1]
    assert century_label(-3) == "3rd century BCE"
    assert century_label(11) == "11th century"
    assert century_label(21) == "21st century"


def test_connectors_need_two_corpus_entities():
    records = [
        {"id": "a", "entity_ids": ["Q1"], "period_start": None},
        {"id": "b", "entity_ids": ["Q2"], "period_start": None},
    ]
    entities = {
        "Q1": entity("Q1", P149=["Q10"], P131=["Q20"]),
        "Q2": entity("Q2", P149=["Q10"]),
    }
    corpus, connectors, edges, counts = build(records, entities, {})
    assert corpus == {"Q1", "Q2"}
    assert connectors == {"Q10"}  # shared style kept; Q20 has one source and is dropped
    assert ("Q1", "P131", "Q20", "wikidata", "1") not in edges
    assert ("Q1", "P149", "Q10", "wikidata", "1") in edges
    assert ("a", "about", "Q1", "corpus", "") in edges
    assert counts["connector candidates dropped (one corpus entity)"] == 1


def test_source_institutions_self_loops_and_redirects():
    records = [
        {"id": "a", "entity_ids": ["Q1"], "period_start": 1500, "period_end": 1610},
        {"id": "b", "entity_ids": ["Q3"], "period_start": None},
    ]
    entities = {
        "Q1": entity("Q1", P276=["Q657415"], P361=["Q1"]),
        "Q2": entity("Q2", P361=["Q1"]),  # Q3 redirects here
    }
    _, connectors, edges, counts = build(records, entities, {"Q3": "Q2"})
    assert counts["edges to a source institution skipped"] == 1
    assert counts["self loops skipped"] == 1
    assert ("b", "about", "Q2", "corpus", "") in edges
    assert ("Q2", "P361", "Q1", "wikidata", "1") in edges
    assert {e[2] for e in edges if e[0] == "a" and e[1] == "in_period"} == {"century:15", "century:16", "century:17"}
    assert connectors == set()
