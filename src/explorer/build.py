"""Files the interface's atlas and graph views read: coordinates, degrees, display hubs and communities (decision 0025).

Nothing here changes the graph or the records. It derives, from the core graph and the raw Wikidata responses
already on disk, what the interface needs to draw the graph at a readable level of detail:

- coordinates: the truthy P625 value of each entity and connector, from the raw response with the revision the
  graph recorded; only coordinates on Earth (globe Q2); the first statement when there are several;
- degree of every node;
- display hubs: every century node, plus entities and connectors above the 99th percentile of their degrees.
  They are drawn as bundles, never as spokes. This is a display rule only; retrieval down-weights hubs its own
  way (decision 0007);
- communities: networkx Louvain with a fixed seed on the graph without display hubs, so the same graph always
  gives the same communities; numbered by size.

Usage:
    uv run python -m src.explorer.build

Output:
    data/explorer/v1/nodes.jsonl.gz      one line per graph node: id, degree, hub, community, lat, lon
    data/explorer/v1/communities.json.gz communities by size: members, documents, top entities, links between them
    results/explorer/explorer_v1.json, .md   counts, settings, input checksums, versions
"""

import glob
import gzip
import hashlib
import io
import json
import math
import subprocess
from collections import Counter
from datetime import UTC, datetime

from src.corpus.wikimedia import ROOT
from src.graph.core_graph import truthy

NODES = ROOT / "data/graph/core_v1/nodes.jsonl.gz"
EDGES = ROOT / "data/graph/core_v1/edges.tsv.gz"
RAW_DIR = ROOT / "data/raw/graph_core_v1"
OUT_DIR = ROOT / "data/explorer/v1"
REPORT = ROOT / "results/explorer/explorer_v1"
EARTH = "http://www.wikidata.org/entity/Q2"
HUB_PERCENTILE = 99
LOUVAIN_SEED = 0
TOP_MEMBERS = 5
# A rough box around India, only to count marks the India map will not show; never used to drop anything.
INDIA_BOX = {"lat": (6.0, 37.5), "lon": (68.0, 97.5)}


def sha256(path) -> str:
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def read_graph() -> tuple[dict[str, dict], list[tuple[str, str, str]]]:
    nodes = {}
    for line in gzip.open(NODES, "rt", encoding="utf-8"):
        n = json.loads(line)
        nodes[n["id"]] = n
    edges = []
    with gzip.open(EDGES, "rt", encoding="utf-8") as f:
        next(f)  # header
        for line in f:
            s, r, t, *_ = line.rstrip("\n").split("\t")
            edges.append((s, r, t))
    return nodes, edges


def coordinate(claims: dict) -> tuple[tuple[float, float] | None, str]:
    """The entity's map point and why: "ok", "none", "not_earth" or "several" (first one taken)."""
    values = []
    for s in truthy(claims.get("P625", [])):
        snak = s.get("mainsnak", {})
        if snak.get("snaktype") == "value":
            values.append(snak["datavalue"]["value"])
    if not values:
        return None, "none"
    earth = [v for v in values if v.get("globe") == EARTH]
    if not earth:
        return None, "not_earth"
    lat, lon = float(earth[0]["latitude"]), float(earth[0]["longitude"])
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None, "none"
    return (lat, lon), ("several" if len(earth) > 1 else "ok")


def raw_entities(revisions: dict[str, int]) -> dict[str, dict]:
    """For each wanted entity, the raw copy with the revision the graph recorded (some appear in several files)."""
    found = {}
    for path in sorted(glob.glob(str(RAW_DIR / "*.json.gz"))):
        data = json.load(gzip.open(path, "rt", encoding="utf-8"))
        for ent in (data.get("entities") or {}).values():
            qid = ent.get("id")
            if qid in revisions and ent.get("lastrevid") == revisions[qid]:
                found[qid] = ent
    return found


def percentile(values: list[int], p: float) -> int:
    """Nearest-rank percentile, so the threshold is a degree that occurs in the data."""
    ordered = sorted(values)
    return ordered[max(0, math.ceil(p / 100 * len(ordered)) - 1)]


def display_hubs(nodes: dict[str, dict], degree: Counter) -> tuple[set[str], int]:
    named = [degree[n] for n, d in nodes.items() if d["kind"] in ("entity", "connector")]
    threshold = percentile(named, HUB_PERCENTILE)
    hubs = {n for n, d in nodes.items() if d["kind"] == "period"}
    hubs |= {n for n, d in nodes.items() if d["kind"] in ("entity", "connector") and degree[n] > threshold}
    return hubs, threshold


def communities(node_ids: list[str], edges: list[tuple[str, str]]) -> list[list[str]]:
    """Louvain on a graph built in sorted order (node order affects the result); largest community first."""
    import networkx as nx

    g = nx.Graph()
    g.add_nodes_from(sorted(node_ids))
    g.add_edges_from(sorted(edges))
    found = nx.community.louvain_communities(g, seed=LOUVAIN_SEED)
    return sorted((sorted(c) for c in found), key=lambda c: (-len(c), c[0]))


# Decision 0035: what a community holds, in the interface's colour groups (web/components/LiveGraph.tsx, groupOf).
GROUPS = {
    "site": "built",
    "place": "built",
    "person": "people",
    "polity": "people",
    "culture": "culture",
    "style": "culture",
}
# A community has a centre on the map only if its placed members cluster: at least this many placed, and the middle
# half of their latitudes and of their longitudes each within this many degrees (about 330 km). Otherwise it lies
# "across India", and is shown apart rather than at a misleading middle point.
CENTRE_MIN_PLACED = 3
REGIONAL_IQR_DEGREES = 3.0


def group_of(node: dict) -> str:
    if node["kind"] == "document":
        return "documents"
    return GROUPS.get(node.get("type") or "", "other")


def quartiles(values: list[float]) -> tuple[float, float, float]:
    v = sorted(values)

    def at(q: float) -> float:
        i = q * (len(v) - 1)
        lo = int(i)
        return v[lo] + (v[min(lo + 1, len(v) - 1)] - v[lo]) * (i - lo)

    return at(0.25), at(0.5), at(0.75)


def centre(points: list[tuple[float, float]]) -> dict:
    """The median point of a community's placed members when they cluster; else why it has none."""
    if len(points) < CENTRE_MIN_PLACED:
        return {"centre": None, "spread": "too few placed"}
    (la1, la, la3), (lo1, lo, lo3) = quartiles([p[0] for p in points]), quartiles([p[1] for p in points])
    if la3 - la1 > REGIONAL_IQR_DEGREES or lo3 - lo1 > REGIONAL_IQR_DEGREES:
        return {"centre": None, "spread": "across India"}
    return {"centre": [round(la, 4), round(lo, 4)], "spread": "regional"}


def label(node: dict) -> str:
    labels = node.get("labels") or {}
    return labels.get("en") or labels.get("hi") or labels.get("kn") or node["id"]


def write_gz(path, lines: list[str]) -> None:
    buf = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=buf, mtime=0) as gz:
        gz.write("".join(lines).encode("utf-8"))
    path.write_bytes(buf.getvalue())


def main() -> None:
    import networkx as nx

    nodes, edges = read_graph()
    degree = Counter()
    for s, _, t in edges:
        degree[s] += 1
        degree[t] += 1
    documents_about = Counter(t for _, r, t in edges if r == "about")

    revisions = {n: d["revision"] for n, d in nodes.items() if d.get("revision") is not None}
    raw = raw_entities(revisions)
    points, why = {}, Counter()
    for qid in sorted(revisions):
        if qid not in raw:
            why["raw_missing"] += 1
            continue
        point, reason = coordinate(raw[qid].get("claims") or {})
        why[reason] += 1
        if point:
            points[qid] = point

    hubs, threshold = display_hubs(nodes, degree)
    kept = [n for n in nodes if n not in hubs]
    keep = set(kept)
    groups = communities(kept, [(s, t) for s, _, t in edges if s in keep and t in keep])
    community_of = {n: i for i, members in enumerate(groups) for n in members}

    lines = []
    for n in sorted(nodes):
        row = {"id": n, "degree": degree[n], "hub": n in hubs, "community": community_of.get(n)}
        if n in points:
            row["lat"], row["lon"] = points[n]
        lines.append(json.dumps(row, ensure_ascii=False) + "\n")

    links = Counter()
    for s, _, t in edges:
        a, b = community_of.get(s), community_of.get(t)
        if a is not None and b is not None and a != b:
            links[(min(a, b), max(a, b))] += 1
    summary = []
    for i, members in enumerate(groups):
        named = [m for m in members if nodes[m]["kind"] in ("entity", "connector")]
        top = sorted(named, key=lambda m: (-degree[m], m))[:TOP_MEMBERS]
        summary.append(
            {
                "id": i,
                "size": len(members),
                "documents": sum(1 for m in members if nodes[m]["kind"] == "document"),
                "entities": len(named),
                "placed": sum(1 for m in named if m in points),
                "label": label(nodes[top[0]]) if top else None,
                "top": top,
                "top_labels": [label(nodes[m]) for m in top[:3]],
                "composition": dict(Counter(group_of(nodes[m]) for m in members)),
                **centre([points[m] for m in named if m in points]),
            }
        )
    community_file = {
        "communities": summary,
        "links": [{"a": a, "b": b, "edges": n} for (a, b), n in sorted(links.items())],
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    write_gz(OUT_DIR / "nodes.jsonl.gz", lines)
    write_gz(OUT_DIR / "communities.json.gz", [json.dumps(community_file, ensure_ascii=False) + "\n"])

    named_kinds = Counter(d["kind"] for n, d in nodes.items() if n in revisions)
    in_box = sum(
        1
        for lat, lon in points.values()
        if INDIA_BOX["lat"][0] <= lat <= INDIA_BOX["lat"][1] and INDIA_BOX["lon"][0] <= lon <= INDIA_BOX["lon"][1]
    )
    sizes = [len(g) for g in groups]
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    report = {
        "built": datetime.now(UTC).date().isoformat(),
        "commit": commit,
        "inputs_sha256": {"nodes": sha256(NODES), "edges": sha256(EDGES)},
        "networkx": nx.__version__,
        "settings": {"hub_percentile": HUB_PERCENTILE, "louvain_seed": LOUVAIN_SEED, "india_box": INDIA_BOX},
        "nodes": len(nodes),
        "edges": len(edges),
        "coordinates": {
            "entities_and_connectors": dict(sorted(named_kinds.items())),
            "placed": len(points),
            "not_placed": len(revisions) - len(points),
            "reasons": dict(sorted(why.items())),
            "placed_inside_india_box": in_box,
            "placed_outside_india_box": len(points) - in_box,
        },
        "hubs": {
            "degree_threshold": threshold,
            "period_nodes": sum(1 for n in hubs if nodes[n]["kind"] == "period"),
            "entities_and_connectors": sum(1 for n in hubs if nodes[n]["kind"] != "period"),
            "top": [
                {"id": n, "label": label(nodes[n]), "degree": degree[n]}
                for n in sorted(hubs, key=lambda n: (-degree[n], n))[:20]
            ],
        },
        "communities": {
            "count": len(groups),
            "largest": sizes[:10],
            "with_10_or_more_nodes": sum(1 for s in sizes if s >= 10),
            "single_nodes": sum(1 for s in sizes if s == 1),
            "links_between": len(links),
            # Decision 0035: of the communities of 10 or more nodes, how many have a centre on the map.
            "spread_of_10_or_more": dict(Counter(c["spread"] for c in summary if c["size"] >= 10)),
            "centre_rule": {"min_placed": CENTRE_MIN_PLACED, "max_iqr_degrees": REGIONAL_IQR_DEGREES},
        },
        "documents_about_an_entity": sum(1 for _, r, _ in edges if r == "about"),
        "entities_with_documents": len(documents_about),
        "outputs_sha256": {
            "nodes": sha256(OUT_DIR / "nodes.jsonl.gz"),
            "communities": sha256(OUT_DIR / "communities.json.gz"),
        },
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.with_suffix(".json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    REPORT.with_suffix(".md").write_text(markdown(report), encoding="utf-8")
    print(markdown(report))


def markdown(r: dict) -> str:
    c, h, k = r["coordinates"], r["hubs"], r["communities"]
    out = [
        "# Explorer data v1",
        "",
        f"Built {r['built']} at commit `{r['commit'][:7]}` from the core graph ({r['nodes']} nodes, {r['edges']} edges);",
        f"networkx {r['networkx']}. Generated by `src/explorer/build.py`; do not edit by hand.",
        "",
        "## Coordinates",
        "",
        "| | Count |",
        "| --- | --- |",
        *[f"| {kind} | {n} |" for kind, n in c["entities_and_connectors"].items()],
        f"| Placed on the map | {c['placed']} |",
        f"| Not placed | {c['not_placed']} |",
        *[f"| Reason: {why} | {n} |" for why, n in c["reasons"].items()],
        f"| Placed, inside a rough box around India | {c['placed_inside_india_box']} |",
        f"| Placed, outside it | {c['placed_outside_india_box']} |",
        "",
        "Reasons: `ok` one coordinate; `several` more than one, the first taken; `none` no usable coordinate;",
        "`not_earth` a coordinate on another globe; `raw_missing` no raw response with the graph's revision.",
        "",
        "## Display hubs",
        "",
        f"Every century node ({h['period_nodes']}) and the entities and connectors with degree above "
        f"{h['degree_threshold']} (the {r['settings']['hub_percentile']}th percentile): {h['entities_and_connectors']}.",
        "",
        "| Hub | Degree |",
        "| --- | --- |",
        *[f"| {x['label']} (`{x['id']}`) | {x['degree']} |" for x in h["top"]],
        "",
        "## Communities",
        "",
        f"Louvain (seed {r['settings']['louvain_seed']}) on the graph without display hubs: {k['count']} communities, "
        f"{k['with_10_or_more_nodes']} with 10 or more nodes, {k['single_nodes']} single nodes, "
        f"{k['links_between']} pairs of communities linked by at least one edge. Largest: "
        + ", ".join(str(s) for s in k["largest"])
        + ".",
        "",
    ]
    return "\n".join(out)


if __name__ == "__main__":
    main()
