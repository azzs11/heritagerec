"""Views of the graph at a readable level of detail (decision 0025): overview, ego, path, nearby, find.

No view ever returns the whole graph. An ego view stays under a node budget: when a node has more neighbours than
fit, the least connected are folded into bundles ("+212 more documents about this"). A display hub (every century,
and the entities above the explorer's degree threshold) can appear as a neighbour, but its own neighbours are
always bundled rather than drawn as spokes. Paths avoid hubs as stepping stones unless no other path exists, and
say so when they pass through one.
"""

import math
from collections import defaultdict, deque

from server.components import RELATION_LABELS, Edge, Graph

DEFAULT_BUDGET = 150
MAX_BUDGET = 600
BUNDLE_SAMPLE = 5
NEAR_DEFAULT = 25
NEAR_MAX = 100
SHARED_MAX = 30
KIND_ORDER = {"entity": 0, "connector": 1, "period": 2, "document": 3}


def edge_json(source: str, e: Edge) -> dict:
    s, t = (source, e.other) if e.direction == "out" else (e.other, source)
    return {
        "source": s,
        "target": t,
        "relation": e.relation,
        "relation_label": RELATION_LABELS.get(e.relation, e.relation),
        "layer": e.layer,
        "revision": e.revision,
    }


def overview(g: Graph, min_size: int = 10) -> dict:
    groups = g.communities["communities"]
    shown = [c for c in groups if c["size"] >= min_size]
    ids = {c["id"] for c in shown}
    rest = [c for c in groups if c["size"] < min_size]
    return {
        "min_size": min_size,
        "communities": shown,
        "links": [x for x in g.communities["links"] if x["a"] in ids and x["b"] in ids],
        "others": {"communities": len(rest), "nodes": sum(c["size"] for c in rest)},
        "hubs": sorted((m["id"] for m in g.meta.values() if m["hub"]), key=lambda n: (-g.meta[n]["degree"], n)),
    }


def ego(
    g: Graph,
    node_id: str,
    budget: int = DEFAULT_BUDGET,
    relations: set[str] | None = None,
    layers: set[str] | None = None,
    kinds: set[str] | None = None,
) -> dict:
    """One node and its neighbours, filtered, under the budget; the rest bundled by relation and kind."""
    budget = max(2, min(budget, MAX_BUDGET))
    edges = [
        e
        for e in g.adjacency.get(node_id, [])
        if (relations is None or e.relation in relations)
        and (layers is None or e.layer in layers)
        and (kinds is None or g.nodes[e.other]["kind"] in kinds)
    ]
    by_neighbour: dict[str, list[Edge]] = defaultdict(list)
    for e in edges:
        by_neighbour[e.other].append(e)

    def priority(n: str) -> tuple:
        return (KIND_ORDER.get(g.nodes[n]["kind"], 9), -g.meta.get(n, {}).get("degree", 0), n)

    ordered = sorted(by_neighbour, key=priority)
    center_is_hub = g.meta.get(node_id, {}).get("hub", False)
    room = budget - 1
    if center_is_hub:
        # A hub's spokes are never all drawn: only its most connected neighbours, the rest bundled.
        room = min(room, BUNDLE_SAMPLE * 4)

    def key(n: str) -> tuple:
        e = by_neighbour[n][0]
        return (e.relation, e.direction, g.nodes[n]["kind"])

    # The centre, the shown neighbours and one mark per bundle together never exceed the budget.
    keep = min(room, len(ordered))
    while keep > 1 and 1 + keep + len({key(n) for n in ordered[keep:]}) > budget:
        keep -= 1
    shown, folded = ordered[:keep], ordered[keep:]

    bundles: dict[tuple, list[str]] = defaultdict(list)
    for n in folded:
        bundles[key(n)].append(n)
    return {
        "center": node_id,
        "budget": budget,
        "nodes": [g.card(node_id)] + [g.card(n) for n in shown],
        "edges": [edge_json(node_id, e) for n in shown for e in by_neighbour[n]],
        "bundles": [
            {
                "relation": rel,
                "relation_label": RELATION_LABELS.get(rel, rel),
                "direction": direction,
                "kind": kind,
                "count": len(members),
                "sample": [g.card(m) for m in members[:BUNDLE_SAMPLE]],
            }
            for (rel, direction, kind), members in sorted(bundles.items(), key=lambda kv: (-len(kv[1]), kv[0]))
        ],
        "neighbours": len(ordered),
        "shown": len(shown),
        "center_is_hub": center_is_hub,
    }


def path(g: Graph, a: str, b: str, max_len: int = 4, k: int = 3) -> dict:
    """Up to k shortest paths from a to b (undirected), first without stepping through hubs, then allowing them."""
    for through_hubs in (False, True):
        found = shortest_paths(g, a, b, max_len, k, through_hubs)
        if found:
            return {
                "from": a,
                "to": b,
                "through_hubs": through_hubs,
                "length": len(found[0]) - 1,
                "paths": [path_json(g, p) for p in found],
            }
    return {"from": a, "to": b, "through_hubs": None, "length": None, "paths": []}


def shortest_paths(g: Graph, a: str, b: str, max_len: int, k: int, through_hubs: bool) -> list[list[str]]:
    if a == b:
        return [[a]]

    def passable(n: str) -> bool:
        return through_hubs or n == b or not g.meta.get(n, {}).get("hub", False)

    dist, parents = {a: 0}, defaultdict(list)
    queue = deque([a])
    while queue:
        n = queue.popleft()
        if dist[n] >= max_len or (n != a and not passable(n)):
            continue
        for e in g.adjacency.get(n, []):
            m = e.other
            if m not in dist:
                dist[m] = dist[n] + 1
                parents[m].append(n)
                queue.append(m)
            elif dist[m] == dist[n] + 1 and n not in parents[m]:
                parents[m].append(n)
    if b not in dist:
        return []

    out: list[list[str]] = []

    def walk(n: str, tail: list[str]) -> None:
        if len(out) >= k:
            return
        if n == a:
            out.append([a] + tail)
            return
        for p in sorted(parents[n]):
            walk(p, [n] + tail)

    walk(b, [])
    return out


def path_json(g: Graph, nodes: list[str]) -> dict:
    steps = []
    for x, y in zip(nodes, nodes[1:], strict=False):
        e = next(e for e in g.adjacency[x] if e.other == y)
        steps.append(edge_json(x, e))
    return {"nodes": [g.card(n) for n in nodes], "edges": steps}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def places(g: Graph) -> list[dict]:
    """Every placed entity and connector, for the atlas to draw all marks at once (a few thousand)."""
    return [
        {
            "id": n,
            "lat": m["lat"],
            "lon": m["lon"],
            "type": g.nodes[n].get("type"),
            "labels": g.label(n),
            "hub": m["hub"],
            "documents": g.documents_about.get(n, 0),
        }
        for n, m in sorted(g.meta.items())
        if "lat" in m
    ]


def near(g: Graph, lat: float, lon: float, k: int = NEAR_DEFAULT) -> dict:
    """The k nearest non-hub places to a point, and how the graph ties them together.

    Nearest rather than within a radius, so a click in a sparse region still answers. Shared neighbours are the
    nodes linked to two or more of the places; centuries are returned apart, as a period rail, since one century
    can join almost everything nearby.
    """
    k = max(1, min(k, NEAR_MAX))
    candidates = [
        (haversine_km(lat, lon, m["lat"], m["lon"]), n) for n, m in g.meta.items() if "lat" in m and not m["hub"]
    ]
    nearest = sorted(candidates)[:k]
    members = [n for _, n in nearest]
    member_set = set(members)

    direct, touches = [], defaultdict(set)
    shared_edges = defaultdict(list)
    for n in members:
        for e in g.adjacency.get(n, []):
            if e.other in member_set:
                if e.direction == "out":
                    direct.append(edge_json(n, e))
            else:
                touches[e.other].add(n)
                shared_edges[e.other].append(edge_json(n, e))
    periods, shared, documents = [], [], []
    for other, linked in touches.items():
        if len(linked) < 2:
            continue
        kind = g.nodes[other]["kind"]
        row = {"node": g.card(other), "members": sorted(linked)}
        if kind == "period":
            periods.append(row)
        elif kind == "document":
            documents.append(row)
        else:
            shared.append(row)

    def by_reach(rows: list[dict]) -> list[dict]:
        return sorted(rows, key=lambda r: (-len(r["members"]), r["node"]["id"]))

    shared = by_reach(shared)[:SHARED_MAX]
    return {
        "point": {"lat": lat, "lon": lon},
        "places": [dict(g.card(n), distance_km=round(d, 1)) for d, n in nearest],
        "links": direct,
        "shared": shared,
        "shared_edges": [e for r in shared for e in shared_edges[r["node"]["id"]]],
        "periods": by_reach(periods),
        "documents_about_several": by_reach(documents)[:SHARED_MAX],
        "documents_per_place": {n: g.documents_about.get(n, 0) for n in members},
    }


def find(g: Graph, text: str, limit: int = 20) -> list[dict]:
    """Nodes whose label in any language starts with or contains the text; prefix matches and big nodes first."""
    q = text.strip().casefold()
    if not q:
        return []
    hits = []
    for n, node in g.nodes.items():
        best = None
        for label in (node.get("labels") or {}).values():
            low = label.casefold()
            if low.startswith(q):
                best = 0
                break
            if q in low:
                best = 1
        if best is not None:
            hits.append((best, KIND_ORDER.get(node["kind"], 9), -g.meta.get(n, {}).get("degree", 0), n))
    return [g.card(n) for *_, n in sorted(hits)[: max(1, min(limit, 100))]]
