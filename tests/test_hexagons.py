"""Tests for the hexagon work (decision 0030): the proximity layer and the ring routes."""

import gzip

from fastapi.testclient import TestClient

from server.app import create_app
from src.graph.proximity_layer import OUT, build

# Belur, its temple a kilometre away, Halebidu about 15 km off, and Delhi far away.
POINTS = {
    "belur": (13.163, 75.865),
    "temple": (13.162, 75.861),
    "halebidu": (13.214, 75.994),
    "delhi": (28.61, 77.21),
}


def test_each_place_joins_only_its_nearest_neighbours_within_one_ring():
    _, edges = build(POINTS, resolution=5, rings=1, nearest=1)
    assert ("belur", "temple") in edges
    assert all("delhi" not in pair for pair in edges)  # nothing within one ring of Delhi
    assert all(a < b for a, b in edges)  # each pair once
    ring, km = edges[("belur", "temple")]
    assert ring in (0, 1) and 0 < km < 1.5


def test_building_twice_gives_the_same_layer():
    assert build(POINTS) == build(POINTS)


def test_the_committed_layer_keeps_places_local():
    rows = [line.rstrip("\n").split("\t") for line in gzip.open(OUT, "rt", encoding="utf-8")][1:]
    assert rows and all(r[1] == "near" and r[3] == "proximity" and r[6] in ("0", "1") for r in rows)
    degree = {}
    for r in rows:
        for n in (r[0], r[2]):
            degree[n] = degree.get(n, 0) + 1
    assert max(degree.values()) <= 2 * 8 + 8  # the nearest-8 rule bounds how many lines meet at a place


def test_rings_spread_out_from_the_point_and_recommendations_skip_the_document():
    client = TestClient(create_app(use_keyword=False))
    r = client.get("/api/atlas/rings", params={"lat": 13.16, "lon": 75.87, "k": 2}).json()
    assert [b["ring"] for b in r["rings"]] == [0, 1, 2]
    d = client.get("/api/graph/rings/wikipedia:en:7051661").json()
    ids = [x["id"] for b in d["rings"] for x in b["documents"]]
    assert "wikipedia:en:7051661" not in ids and len(ids) == len(set(ids))
    h = client.get("/api/atlas/hexes", params={"res": 4}).json()
    assert sum(x["count"] for x in h) == sum(1 for p in client.get("/api/atlas/places").json() if not p["hub"])
