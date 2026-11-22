"""The graph lens: personalised PageRank from chosen entities, with the path that explains each result.

Until the query linker exists (decision 0026), the seeds are entities a reader picks; the interface says so. Each
result carries the shortest path from a seed to it (avoiding hubs where a path without them exists), and the
entities where the walk spent most of its time, so the ranking can be read rather than trusted.
"""

from server import graph_views
from server.components import Graph, Paths
from src.graph_retrieval.ppr import rank_documents, scores

WHERE_TOP = 8


def rank(g: Graph, paths: Paths, seeds: dict[str, float], k: int, restart: float, hub_power: float) -> dict:
    """PageRank from weighted seeds (an ambiguous name's weight is split among its entities, decision 0027)."""
    walk = g.walk(paths, hub_power)
    x = scores(walk, seeds, restart)
    results = []
    for i, (doc, score) in enumerate(rank_documents(walk, x, k), 1):
        best = None
        for seed in seeds:
            p = graph_views.path(g, seed, doc, max_len=4, k=1)
            if p["paths"] and (best is None or p["length"] < best["length"]):
                best = p
        results.append({"rank": i, "score": score, "document": g.card(doc), "path": best})
    seed_set = set(seeds)
    places = [
        (float(x[j]), walk.ids[j])
        for j in x.argsort()[::-1][: WHERE_TOP * 4]
        if not walk.kinds[j] and walk.ids[j] not in seed_set and x[j] > 0
    ][:WHERE_TOP]
    return {
        "seeds": [dict(g.card(s), weight=w) for s, w in seeds.items()],
        "settings": {"restart": restart, "hub_power": hub_power, "decision": "0027"},
        "results": results,
        "walk_spends_time_at": [{"node": g.card(n), "share": share} for share, n in places],
    }
