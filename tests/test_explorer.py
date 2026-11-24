"""Tests for the explorer data builder (src/explorer/build.py) and the files it wrote."""

import gzip
import json
from collections import Counter

from src.explorer.build import EARTH, NODES, OUT_DIR, communities, coordinate, display_hubs, percentile

MOON = "http://www.wikidata.org/entity/Q405"


def p625(lat, lon, rank="normal", globe=EARTH, snaktype="value"):
    snak = {"snaktype": snaktype}
    if snaktype == "value":
        snak["datavalue"] = {"value": {"latitude": lat, "longitude": lon, "globe": globe}}
    return {"rank": rank, "mainsnak": snak}


def test_coordinate_follows_truthy_rank_and_earth_only():
    assert coordinate({}) == (None, "none")
    assert coordinate({"P625": [p625(12.3, 76.6)]}) == ((12.3, 76.6), "ok")
    # A preferred statement wins over normal ones; deprecated is never used.
    claims = {"P625": [p625(1, 1), p625(15.3, 76.4, rank="preferred"), p625(2, 2, rank="deprecated")]}
    assert coordinate(claims) == ((15.3, 76.4), "ok")
    assert coordinate({"P625": [p625(10, 70), p625(11, 71)]}) == ((10.0, 70.0), "several")
    assert coordinate({"P625": [p625(1, 1, globe=MOON)]}) == (None, "not_earth")
    assert coordinate({"P625": [p625(0, 0, snaktype="somevalue")]}) == (None, "none")
    assert coordinate({"P625": [p625(1, 1, rank="deprecated")]}) == (None, "none")


def test_percentile_is_a_degree_that_occurs():
    assert percentile([1, 2, 3, 4, 100], 99) == 100
    assert percentile([5] * 10 + [50], 50) == 5
    assert percentile(list(range(1, 101)), 99) == 99


def test_period_nodes_are_always_hubs_and_entities_only_above_the_threshold():
    nodes = {f"e{i}": {"kind": "entity"} for i in range(100)} | {"century:12": {"kind": "period"}}
    degree = Counter({f"e{i}": 1 for i in range(99)} | {"e99": 40, "century:12": 1})
    hubs, threshold = display_hubs(nodes, degree)
    assert threshold == 1 and hubs == {"century:12", "e99"}


def test_communities_do_not_depend_on_input_order():
    edges = [("a", "b"), ("b", "c"), ("c", "a"), ("x", "y"), ("y", "z"), ("z", "x"), ("c", "x"), ("q", "r")]
    first = communities(list("abcxyzqr"), edges)
    assert communities(list("rqzyxcba"), list(reversed(edges))) == first
    assert sorted(n for c in first for n in c) == sorted("abcxyzqr")
    assert [len(c) for c in first] == sorted((len(c) for c in first), reverse=True)


def test_written_files_cover_every_graph_node_once():
    graph = [json.loads(line)["id"] for line in gzip.open(NODES, "rt", encoding="utf-8")]
    rows = [json.loads(line) for line in gzip.open(OUT_DIR / "nodes.jsonl.gz", "rt", encoding="utf-8")]
    assert sorted(r["id"] for r in rows) == sorted(graph)
    for r in rows:
        assert (r["community"] is None) == r["hub"]
        if "lat" in r:
            assert -90 <= r["lat"] <= 90 and -180 <= r["lon"] <= 180
    groups = json.loads(gzip.open(OUT_DIR / "communities.json.gz", "rt", encoding="utf-8").read())
    sizes = Counter(r["community"] for r in rows if r["community"] is not None)
    assert [c["size"] for c in groups["communities"]] == [sizes[c["id"]] for c in groups["communities"]]


def test_a_community_has_a_centre_only_when_its_places_cluster():
    from src.explorer.build import CENTRE_MIN_PLACED, centre, group_of

    belur = [(13.16 + i * 0.01, 75.86 + i * 0.01) for i in range(5)]
    c = centre(belur)
    assert c["spread"] == "regional" and abs(c["centre"][0] - 13.18) < 0.01
    assert centre(belur[: CENTRE_MIN_PLACED - 1]) == {"centre": None, "spread": "too few placed"}
    india = [(8.5, 77.0), (13.0, 80.2), (19.0, 72.8), (28.6, 77.2), (26.9, 75.8), (22.5, 88.3)]
    assert centre(india) == {"centre": None, "spread": "across India"}
    # The interface's colour groups (LiveGraph.groupOf), with documents counted on their own.
    assert group_of({"kind": "entity", "type": "polity"}) == "people"
    assert group_of({"kind": "connector", "type": "place"}) == "built"
    assert group_of({"kind": "document", "type": "site"}) == "documents"
    assert group_of({"kind": "entity", "type": "other"}) == "other"
