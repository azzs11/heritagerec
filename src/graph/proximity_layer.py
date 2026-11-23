"""The proximity layer: places joined by nearness on Uber's H3 hexagon grid (decision 0030, option C).

A separate edge layer, never mixed into the core: the headline RQ1 result uses the core Wikidata layer only, and
this layer is reported beside it as an addition. It holds no text similarity, only distance between coordinates.

Every placed entity that is not a display hub is put in its resolution-5 hexagon (about 10 km across). Each place is
joined to its K nearest places within one ring of hexagons (its own cell and the six around it). Joining every pair
within one ring would give 70,029 edges and up to 133 per place in dense cities, which would act as hubs; the
nearest-K rule keeps the layer local. Each edge keeps its ring distance (0 or 1) and its great-circle length in km.

Usage:
    uv run python -m src.graph.proximity_layer

Output:
    data/graph/proximity_v1/edges.tsv.gz      source, relation (near), target, layer, origin, revision, ring, km
    results/graph/proximity_v1.json, .md      settings, counts, degrees, rings, components
"""

import gzip
import hashlib
import io
import json
import math
import subprocess
from collections import Counter, defaultdict
from datetime import UTC, datetime

import h3

from src.corpus.wikimedia import ROOT

EXPLORER = ROOT / "data/explorer/v1/nodes.jsonl.gz"
OUT = ROOT / "data/graph/proximity_v1/edges.tsv.gz"
REPORT = ROOT / "results/graph/proximity_v1"
RESOLUTION = 5
RINGS = 1
NEAREST = 8


def km(a: tuple[float, float], b: tuple[float, float]) -> float:
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = p2 - p1, math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def places() -> dict[str, tuple[float, float]]:
    out = {}
    for line in gzip.open(EXPLORER, "rt", encoding="utf-8"):
        n = json.loads(line)
        if "lat" in n and not n["hub"]:
            out[n["id"]] = (n["lat"], n["lon"])
    return dict(sorted(out.items()))


def build(
    points: dict[str, tuple[float, float]], resolution: int = RESOLUTION, rings: int = RINGS, nearest: int = NEAREST
):
    """Undirected edges (a < b) with ring distance and km: each place to its nearest within `rings` hexagons."""
    cell = {n: h3.latlng_to_cell(lat, lon, resolution) for n, (lat, lon) in points.items()}
    by_cell = defaultdict(list)
    for n, c in cell.items():
        by_cell[c].append(n)
    edges: dict[tuple[str, str], tuple[int, float]] = {}
    for n, c in cell.items():
        candidates = []
        for cc in h3.grid_disk(c, rings):
            for m in by_cell.get(cc, ()):
                if m != n:
                    candidates.append((km(points[n], points[m]), m))
        for d, m in sorted(candidates)[:nearest]:
            a, b = (n, m) if n < m else (m, n)
            edges[(a, b)] = (h3.grid_distance(cell[a], cell[b]), round(d, 3))
    return cell, dict(sorted(edges.items()))


def components(nodes: list[str], edges) -> list[int]:
    parent = {n: n for n in nodes}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in edges:
        parent[find(a)] = find(b)
    return sorted(Counter(find(n) for n in nodes).values(), reverse=True)


def main() -> None:
    points = places()
    cell, edges = build(points)
    rows = [f"{a}\tnear\t{b}\tproximity\th3\tres{RESOLUTION}\t{ring}\t{d}\n" for (a, b), (ring, d) in edges.items()]
    buf = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=buf, mtime=0) as gz:
        gz.write(("source\trelation\ttarget\tlayer\torigin\trevision\tring\tkm\n" + "".join(rows)).encode("utf-8"))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(buf.getvalue())

    degree = Counter()
    for a, b in edges:
        degree[a] += 1
        degree[b] += 1
    ds = sorted(degree.values())
    sizes = components(list(points), edges)
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    report = {
        "built": datetime.now(UTC).date().isoformat(),
        "commit": commit,
        "h3": h3.__version__,
        "settings": {"resolution": RESOLUTION, "rings": RINGS, "nearest": NEAREST},
        "places": len(points),
        "cells": len(set(cell.values())),
        "edges": len(edges),
        "edges_by_ring": dict(sorted(Counter(r for r, _ in edges.values()).items())),
        "places_with_an_edge": len(degree),
        "degree": {"median": ds[len(ds) // 2], "p99": ds[int(0.99 * len(ds))], "max": ds[-1]} if ds else {},
        "km": {"median": sorted(d for _, d in edges.values())[len(edges) // 2]} if edges else {},
        "components": {"count": len(sizes), "largest": sizes[:5], "single_places": sum(1 for x in sizes if x == 1)},
        "output_sha256": hashlib.sha256(OUT.read_bytes()).hexdigest(),
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    md = [
        "# Proximity layer v1",
        "",
        f"Built {report['built']} at commit `{commit[:7]}` with h3 {report['h3']}. Generated by",
        "`src/graph/proximity_layer.py`; do not edit by hand. A separate layer: never part of the headline core result.",
        "",
        f"{report['places']} places in {report['cells']} resolution-{RESOLUTION} hexagons; each joined to its {NEAREST}",
        f"nearest within {RINGS} ring. {report['edges']} edges ({report['edges_by_ring']} by ring), touching",
        f"{report['places_with_an_edge']} places; degree median {report['degree'].get('median')}, 99th percentile",
        f"{report['degree'].get('p99')}, most {report['degree'].get('max')}; median length {report['km'].get('median')} km.",
        f"Components: {report['components']['count']}, largest {report['components']['largest']},",
        f"{report['components']['single_places']} places alone.",
        "",
    ]
    REPORT.with_suffix(".md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
