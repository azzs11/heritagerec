"""Tests for the interface server (server/): graph views, degraded starts, explanations, and fuzzing.

Three layers:
- graph view rules on a small hand-built graph (no files needed);
- the app on the real committed graph and explorer files, started without keyword search (runs in CI);
- keyword search and its explanation check on the real indexes (skipped where Java or the indexes are absent).
The fuzz tests send arbitrary input and fail on any 500.
"""

import os
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from server import graph_views
from server.app import create_app
from server.components import Edge, Graph, Paths
from server.keyword import detect_language

ROOT = Path(__file__).resolve().parents[1]
HAVE_RECORDS = Paths().records.exists()
HAVE_KEYWORD = all((Paths().indexes / lang).exists() for lang in ("en", "hi", "kn"))
ALLOWED = {200, 400, 404, 422, 503}
TEXT = st.text(
    alphabet=st.characters(codec="utf-8", categories=("L", "M", "N", "P", "S", "Z", "Cc"), include_characters="ऀಀ"),
    max_size=80,
)


def small_graph() -> Graph:
    """A star of 30 documents around one entity, one hub linked to everything, and a chain a-b-c."""
    g = Graph(adjacency=defaultdict(list))

    def add(n, kind, degree=1, hub=False, lat=None, lon=None):
        g.nodes[n] = {"id": n, "kind": kind, "type": "site", "labels": {"en": n}}
        g.meta[n] = {"id": n, "degree": degree, "hub": hub, "community": None if hub else 0}
        if lat is not None:
            g.meta[n]["lat"], g.meta[n]["lon"] = lat, lon

    def link(s, r, t):
        g.adjacency[s].append(Edge(t, r, "out", "core", "1"))
        g.adjacency[t].append(Edge(s, r, "in", "core", "1"))

    add("star", "entity", degree=31, lat=12.0, lon=76.0)
    add("hub", "period", degree=40, hub=True)
    for i in range(30):
        add(f"d{i}", "document")
        link(f"d{i}", "about", "star")
    for n in ("a", "b", "c"):
        add(n, "entity", degree=2, lat=12.1, lon=76.1)
    link("a", "P361", "b")
    link("b", "P361", "c")
    for n in ["star", "a", "c"] + [f"d{i}" for i in range(5)]:
        link(n, "in_period", "hub")
    g.communities = {"communities": [{"id": 0, "size": 35}], "links": []}
    return g


# ---------- graph view rules ----------


@pytest.mark.parametrize("budget", [2, 3, 5, 10, 33, 150])
def test_ego_never_exceeds_its_budget(budget):
    view = graph_views.ego(small_graph(), "star", budget=budget)
    assert len(view["nodes"]) + len(view["bundles"]) <= max(budget, 3)
    assert view["shown"] + sum(b["count"] for b in view["bundles"]) == view["neighbours"]


def test_a_hub_is_never_drawn_as_all_its_spokes():
    view = graph_views.ego(small_graph(), "hub", budget=600)
    assert view["center_is_hub"] and view["shown"] <= 20


def test_paths_avoid_hubs_first_and_say_when_they_cannot():
    g = small_graph()
    direct = graph_views.path(g, "a", "c")
    assert direct["through_hubs"] is False and [n["id"] for n in direct["paths"][0]["nodes"]] == ["a", "b", "c"]
    via = graph_views.path(g, "star", "a")
    assert via["through_hubs"] is True and via["length"] == 2
    assert graph_views.path(g, "a", "a")["length"] == 0


def test_near_returns_nearest_first_and_skips_hubs():
    view = graph_views.near(small_graph(), 12.1, 76.1, k=3)
    assert [p["id"] for p in view["places"]][:3] == ["a", "b", "c"]
    assert all(not p["hub"] for p in view["places"])
    assert {p["node"]["id"] for p in view["periods"]} == {"hub"}


def test_language_is_read_from_the_script():
    assert detect_language("Hoysala temples")["language"] == "en"
    assert detect_language("मुगल किला")["language"] == "hi"
    assert detect_language("ಹಂಪೆ ದೇವಾಲಯ")["language"] == "kn"
    assert detect_language("123 !!")["language"] == "en"


# ---------- the app on the real graph, without keyword search ----------


@pytest.fixture(scope="module")
def graph_client():
    return TestClient(create_app(use_keyword=False))


def test_health_names_every_part_and_what_is_not_built(graph_client):
    h = graph_client.get("/api/health").json()
    assert h["graph"]["status"] == "ok" and h["keyword"]["status"] == "missing"
    assert h["keyword"]["fix"] and h["planned"]["dense"]["status"] == "not built yet"
    # The graph lens runs (linker and PageRank) but is not measured until the dev queries are judged.
    assert h["graph_lens"]["status"] == "ok" and h["graph_lens"]["evaluated"] is False


def test_search_without_its_part_says_why(graph_client):
    r = graph_client.get("/api/search", params={"q": "fort"})
    assert r.status_code == 503 and r.json()["detail"]["part"] == "keyword"


def test_real_graph_views(graph_client):
    hub = graph_client.get("/api/graph/ego/Q668").json()
    assert hub["center_is_hub"] and len(hub["nodes"]) + len(hub["bundles"]) <= hub["budget"]
    places = graph_client.get("/api/atlas/places").json()
    assert places and all(-90 <= p["lat"] <= 90 for p in places)
    near = graph_client.get("/api/atlas/near", params={"lat": 13.16, "lon": 75.87, "k": 10}).json()
    distances = [p["distance_km"] for p in near["places"]]
    assert distances == sorted(distances)
    assert graph_client.get("/api/graph/ego/not-a-node").status_code == 404


def test_graph_rank_explains_each_result_with_a_path_from_a_seed(graph_client):
    r = graph_client.get("/api/graph/rank", params={"seeds": "Q466581", "k": 5}).json()
    assert len(r["results"]) == 5 and r["seeds"][0]["id"] == "Q466581"
    scores = [x["score"] for x in r["results"]]
    assert scores == sorted(scores, reverse=True)
    for x in r["results"]:
        assert x["document"]["kind"] == "document"
        assert x["path"]["paths"][0]["nodes"][0]["id"] == "Q466581"
        assert x["path"]["paths"][0]["nodes"][-1]["id"] == x["document"]["id"]
    assert all(w["node"]["kind"] != "document" for w in r["walk_spends_time_at"])


def test_link_route_returns_cards_and_seeds(graph_client):
    r = graph_client.get("/api/link", params={"q": "Hoysala temples Belur"}).json()
    assert [m["candidates"][0]["id"] for m in r["mentions"]] == ["Q466581", "Q760603"]
    assert r["seeds"] == {"Q466581": 1.0, "Q760603": 1.0}
    assert graph_client.get("/api/link", params={"q": ""}).status_code == 400


def test_graph_rank_refuses_unknown_seeds_and_settings(graph_client):
    assert graph_client.get("/api/graph/rank", params={"seeds": "Qnope"}).status_code == 400
    assert graph_client.get("/api/graph/rank", params={"seeds": ";;"}).status_code == 400
    assert graph_client.get("/api/graph/rank", params={"seeds": "Q466581", "hub_power": 0.3}).status_code == 400
    assert graph_client.get("/api/graph/rank", params={"seeds": "Q466581", "restart": 1}).status_code == 422


def test_every_route_degrades_when_nothing_is_on_disk(tmp_path):
    empty = Paths(
        root=tmp_path,
        records=tmp_path / "r.gz",
        manifest=tmp_path / "m.json",
        nodes=tmp_path / "n.gz",
        edges=tmp_path / "e.gz",
        explorer_nodes=tmp_path / "x.gz",
        communities=tmp_path / "c.gz",
        indexes=tmp_path / "idx",
        results=tmp_path / "results",
    )
    client = TestClient(create_app(empty, use_keyword=True))
    for url in [
        "/api/corpus/stats",
        "/api/graph/overview",
        "/api/graph/ego/Q668",
        "/api/atlas/places",
        "/api/atlas/near?lat=1&lon=1",
        "/api/graph/rank?seeds=Q1",
        "/api/search?q=fort",
        "/api/explain?q=fort&doc=x",
        "/api/documents/x",
    ]:
        r = client.get(url)
        assert r.status_code == 503, url
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/ledger").json() == []


# ---------- fuzzing: nothing may answer 500 ----------

FUZZ = settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])


@FUZZ
@given(node=TEXT, budget=st.integers(-5, 1000), relations=st.one_of(st.none(), TEXT))
def test_fuzz_ego(graph_client, node, budget, relations):
    params = {"budget": budget} | ({"relations": relations} if relations is not None else {})
    assert graph_client.get(f"/api/graph/ego/{quote(node, safe='')}", params=params).status_code in ALLOWED


@FUZZ
@given(lat=st.floats(allow_nan=True, allow_infinity=True), lon=st.floats(), k=st.integers(-3, 500))
def test_fuzz_near(graph_client, lat, lon, k):
    assert graph_client.get("/api/atlas/near", params={"lat": lat, "lon": lon, "k": k}).status_code in ALLOWED


@FUZZ
@given(a=TEXT, b=TEXT, q=TEXT)
def test_fuzz_path_and_find(graph_client, a, b, q):
    assert graph_client.get("/api/graph/path", params={"source": a, "target": b}).status_code in ALLOWED
    assert graph_client.get("/api/graph/find", params={"q": q}).status_code in ALLOWED


@FUZZ
@given(seeds=TEXT, restart=st.floats(allow_nan=True), hub=st.sampled_from([0, 0.5, 1, 2, -1]))
def test_fuzz_graph_rank(graph_client, seeds, restart, hub):
    params = {"seeds": seeds, "restart": restart, "hub_power": hub}
    assert graph_client.get("/api/graph/rank", params=params).status_code in ALLOWED


@FUZZ
@given(doc=TEXT, offset=st.integers(-5, 10**6), limit=st.integers(-5, 500))
def test_fuzz_documents(graph_client, doc, offset, limit):
    assert graph_client.get(f"/api/documents/{quote(doc, safe='')}").status_code in ALLOWED
    r = graph_client.get(f"/api/documents/{quote(doc, safe='')}/passages", params={"offset": offset, "limit": limit})
    assert r.status_code in ALLOWED


# ---------- keyword search on the real indexes ----------

needs_keyword = pytest.mark.skipif(
    not (HAVE_KEYWORD and HAVE_RECORDS and (os.environ.get("JAVA_HOME") or (ROOT / ".env").exists())),
    reason="needs Java, the BM25 indexes and the corpus snapshot",
)


@pytest.fixture(scope="module")
def full_client():
    return TestClient(create_app())


@needs_keyword
@pytest.mark.parametrize(
    "q", ["Hoysala temples Belur", "temple temple Belur", "मुगल किला आगरा", "ಹಂಪೆ ದೇವಾಲಯ", "Mughal miniature painting"]
)
@pytest.mark.parametrize("system", ["bm25", "bm25_rm3"])
def test_explanations_add_up_to_lucene_scores(full_client, q, system):
    results = full_client.get("/api/search", params={"q": q, "system": system, "k": 3}).json()["results"]
    assert results
    for r in results:
        x = full_client.get("/api/explain", params={"q": q, "doc": r["doc_id"], "system": system}).json()
        assert x["rank"] == r["rank"]
        assert x["winner"]["check"]["matches"], x["winner"]["check"]


@needs_keyword
@FUZZ
@given(
    q=TEXT, lang=st.sampled_from([None, "en", "hi", "kn", "xx"]), system=st.sampled_from(["bm25", "bm25_rm3", "ppr"])
)
def test_fuzz_search(full_client, q, lang, system):
    params = {"q": q, "system": system} | ({"lang": lang} if lang else {})
    assert full_client.get("/api/search", params=params).status_code in ALLOWED
