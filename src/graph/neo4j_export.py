"""Export the graph for Neo4j (decision 0029, option C).

The study never reads from Neo4j: retrieval and evaluation run on the files in data/graph/. This export lets anyone
who prefers Cypher load the identical graph, layer by layer, with `neo4j-admin database import full`. Each
relationship keeps its layer, so a query can stay on the core layer that the headline result uses.

Usage:
    uv run python -m src.graph.neo4j_export

Output (gitignored, rebuilt on demand; published with the interim snapshot and the freeze):
    data/graph/neo4j_v1/nodes.csv.gz                 one row per node, Neo4j label from its kind
    data/graph/neo4j_v1/relationships_core.csv.gz    the core Wikidata layer, `about` and `in_period`
    data/graph/neo4j_v1/relationships_proximity.csv.gz  `NEAR`, with ring and km
    data/graph/neo4j_v1/import.sh, schema.cypher, examples.cypher
    results/graph/neo4j_v1.json, .md                 counts per label and type, checksums
"""

import csv
import gzip
import hashlib
import io
import json
import re
import subprocess
from collections import Counter
from datetime import UTC, datetime

from src.corpus.wikimedia import ROOT
from src.graph.core_graph import RELATIONS

CORE = ROOT / "data/graph/core_v1"
PROXIMITY = ROOT / "data/graph/proximity_v1/edges.tsv.gz"
OUT = ROOT / "data/graph/neo4j_v1"
REPORT = ROOT / "results/graph/neo4j_v1"

LABELS = {"document": "Document", "entity": "Entity", "connector": "Connector", "period": "Century"}
NAMED = {"about": "ABOUT", "in_period": "IN_CENTURY", "near": "NEAR"}
LANGS = ("en", "hi", "kn")


def rel_type(relation: str) -> str:
    """A readable Cypher type: P131 becomes LOCATED_IN_THE_ADMINISTRATIVE_ENTITY; the property id is kept too."""
    if relation in NAMED:
        return NAMED[relation]
    words = re.sub(r"[^A-Za-z0-9]+", "_", RELATIONS.get(relation, relation)).strip("_")
    return words.upper()


def clean(text: str | None) -> str:
    return " ".join((text or "").split())


def write_csv(path, header: list[str], rows) -> int:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    n = 0
    for r in rows:
        w.writerow(r)
        n += 1
    raw = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as gz:
        gz.write(buf.getvalue().encode("utf-8"))
    path.write_bytes(raw.getvalue())
    return n


def node_rows(nodes: list[dict]):
    for n in nodes:
        labels = n.get("labels", {})
        yield [
            n["id"],
            n["kind"],
            n.get("type") or "",
            *(clean(labels.get(lang)) for lang in LANGS),
            ";".join(n.get("classes") or []),
            n.get("revision") or "",
            ";".join(
                [LABELS[n["kind"]]] + ([n["type"].capitalize()] if n.get("type") and n["kind"] == "entity" else [])
            ),
        ]


def read_tsv(path) -> list[list[str]]:
    lines = gzip.open(path, "rt", encoding="utf-8").read().splitlines()
    return [line.split("\t") for line in lines[1:] if line]


def core_rows(edges: list[list[str]]):
    for source, relation, target, layer, origin, revision in edges:
        yield [source, target, rel_type(relation), relation, layer, origin, revision]


def proximity_rows(edges: list[list[str]]):
    for source, relation, target, layer, origin, revision, ring, km in edges:
        yield [source, target, rel_type(relation), relation, layer, origin, revision, ring, km]


SCHEMA = """// Run after the import, in the database you imported into.
CREATE INDEX node_id IF NOT EXISTS FOR (n:Document) ON (n.id);
CREATE INDEX entity_id IF NOT EXISTS FOR (n:Entity) ON (n.id);
CREATE INDEX century_id IF NOT EXISTS FOR (n:Century) ON (n.id);
CREATE INDEX connector_id IF NOT EXISTS FOR (n:Connector) ON (n.id);
CREATE FULLTEXT INDEX names IF NOT EXISTS FOR (n:Entity|Document) ON EACH [n.label_en, n.label_hi, n.label_kn];
"""

EXAMPLES = """// Example queries. Keep to {layer: 'core'} for anything compared with the headline result.

// What the Chennakesava Temple at Belur is tied to, on the core layer only.
MATCH (t:Entity {id: 'Q3536222'})-[r {layer: 'core'}]-(x) RETURN t, r, x LIMIT 50;

// Documents about places within one hexagon ring of Belur (the proximity layer).
MATCH (b:Entity {id: 'Q760603'})-[:NEAR]-(p:Entity)<-[:ABOUT]-(d:Document)
RETURN p.label_en AS place, d.label_en AS document LIMIT 25;

// Shortest chain of facts from the Chennakesava Temple to the Konark Sun Temple, ignoring proximity.
MATCH path = shortestPath((a:Entity {id: 'Q3536222'})-[*..6]-(b:Entity {id: 'Q752091'}))
WHERE all(r IN relationships(path) WHERE r.layer = 'core')
RETURN path;

// Find by name in any of the three scripts.
CALL db.index.fulltext.queryNodes('names', 'हम्पी OR Hampi OR ಹಂಪೆ') YIELD node, score
RETURN node.id, node.label_en, score LIMIT 10;
"""

IMPORT = """#!/bin/sh
# Load the export into an empty Neo4j 5 database (Neo4j Desktop: stop the database, open its terminal, then run this
# with the path to this folder). Afterwards start the database and run schema.cypher.
set -e
HERE="${1:-$(dirname "$0")}"
neo4j-admin database import full neo4j --overwrite-destination \\
  --nodes="$HERE/nodes.csv.gz" \\
  --relationships="$HERE/relationships_core.csv.gz" \\
  --relationships="$HERE/relationships_proximity.csv.gz" \\
  --array-delimiter=";"
"""


def main() -> None:
    nodes = [json.loads(line) for line in gzip.open(CORE / "nodes.jsonl.gz", "rt", encoding="utf-8")]
    nodes.sort(key=lambda n: n["id"])
    core = read_tsv(CORE / "edges.tsv.gz")
    proximity = read_tsv(PROXIMITY)
    ids = {n["id"] for n in nodes}
    missing = {x for e in core + proximity for x in (e[0], e[2]) if x not in ids}
    if missing:
        raise SystemExit(f"{len(missing)} edge ends are not nodes, for example {sorted(missing)[:3]}")

    OUT.mkdir(parents=True, exist_ok=True)
    common = [":START_ID", ":END_ID", ":TYPE", "property", "layer", "origin", "revision"]
    counts = {
        "nodes": write_csv(
            OUT / "nodes.csv.gz",
            ["id:ID", "kind", "type", "label_en", "label_hi", "label_kn", "classes:string[]", "revision", ":LABEL"],
            node_rows(nodes),
        ),
        "core": write_csv(OUT / "relationships_core.csv.gz", common, core_rows(core)),
        "proximity": write_csv(
            OUT / "relationships_proximity.csv.gz", common + ["ring:int", "km:float"], proximity_rows(proximity)
        ),
    }
    (OUT / "schema.cypher").write_text(SCHEMA, encoding="utf-8")
    (OUT / "examples.cypher").write_text(EXAMPLES, encoding="utf-8")
    (OUT / "import.sh").write_text(IMPORT, encoding="utf-8")
    (OUT / "import.sh").chmod(0o755)

    files = sorted(p for p in OUT.iterdir() if p.is_file())
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    report = {
        "built": datetime.now(UTC).date().isoformat(),
        "commit": commit,
        "sources": {
            "core_nodes": "data/graph/core_v1/nodes.jsonl.gz",
            "core_edges": "data/graph/core_v1/edges.tsv.gz",
            "proximity": "data/graph/proximity_v1/edges.tsv.gz",
        },
        "counts": counts,
        "labels": dict(sorted(Counter(LABELS[n["kind"]] for n in nodes).items())),
        "types": dict(sorted(Counter(rel_type(e[1]) for e in core + proximity).items())),
        "sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.with_suffix(".json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md = [
        "# Neo4j export v1",
        "",
        f"Built {report['built']} at commit `{commit[:7]}` by `src/graph/neo4j_export.py`; do not edit by hand.",
        "The files are rebuilt on demand (gitignored) and published with the snapshots; the checksums below identify them.",
        "",
        f"{counts['nodes']} nodes, {counts['core']} core relationships, {counts['proximity']} proximity relationships.",
        "",
        "| Node label | Count |",
        "| --- | --- |",
        *(f"| {k} | {v} |" for k, v in report["labels"].items()),
        "",
        "| Relationship type | Count |",
        "| --- | --- |",
        *(f"| {k} | {v} |" for k, v in report["types"].items()),
        "",
        "| File | sha256 |",
        "| --- | --- |",
        *(f"| `{k}` | `{v}` |" for k, v in report["sha256"].items()),
        "",
    ]
    REPORT.with_suffix(".md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md[:6]))


if __name__ == "__main__":
    main()
