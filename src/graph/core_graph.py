"""Core Wikidata graph: documents, the entities they are about, and the facts between them (decision 0020).

Nodes are the corpus documents, the Wikidata entities in their `entity_ids`, connector
entities (no document, but linked from two or more corpus entities) and derived
century nodes. Edges are `about` (document -> entity), the 16 core Wikidata relations
(truthy values only) and `in_period` (document or entity -> century). The graph holds
no text-similarity edges (decision 0006); hubs are down-weighted later, at retrieval.

Usage:
    uv run python -m src.graph.core_graph

Output:
    data/graph/core_v1/nodes.jsonl.gz   one node per line: id, kind, type, labels, classes
    data/graph/core_v1/edges.tsv.gz     source, relation, target, layer, origin, revision
    results/graph/core_v1.json, .md     statistics, generated into the data card
"""

import gzip
import io
import json
import subprocess
from collections import Counter, defaultdict
from datetime import UTC, datetime

from src.corpus.wikimedia import ROOT, Wikimedia

SNAPSHOT = ROOT / "data/corpus_v1/records.jsonl.gz"
GAZETTEER = ROOT / "data/gazetteer/gazetteer_v1.jsonl.gz"
RAW_DIR = ROOT / "data/raw/graph_core_v1"
OUT_DIR = ROOT / "data/graph/core_v1"
REPORT = ROOT / "results/graph/core_v1"
API = "https://www.wikidata.org/w/api.php"
BATCH = 50  # the most ids wbgetentities accepts per request
LAYER = "core"
LANGS = ("en", "hi", "kn")
MIN_CONNECTOR_SOURCES = 2  # a connector with one link cannot join two corpus entities
TOP_HUBS = 20

# The 16 relations of the neighbour probe (src/corpus/neighbour_probe.py), followed outwards only.
RELATIONS = {
    "P131": "located in the administrative entity",
    "P276": "location",
    "P361": "part of",
    "P527": "has part",
    "P88": "commissioned by",
    "P84": "architect",
    "P112": "founded by",
    "P53": "family (dynasty)",
    "P36": "capital",
    "P149": "architectural style",
    "P136": "genre",
    "P135": "movement",
    "P1365": "replaces",
    "P1366": "replaced by",
    "P800": "notable work",
    "P170": "creator",
}
DATE_PROPS = ("P571", "P580", "P582", "P576")  # inception, start, end, dissolved
CENTURY_PRECISION = 7  # Wikidata time precision: 7 century, 8 decade, 9 year and finer
# The institutions the corpus was collected from. A statement that an object is held by one of
# them says which source the record came from, not anything about the heritage, so it would
# relate documents by source (author decision, 21 Nov 2026; docs/data_notes.md).
SOURCE_INSTITUTIONS = {
    "Q657415": "Cleveland Museum of Art",
    "Q160236": "Metropolitan Museum of Art",
    "Q239303": "Art Institute of Chicago",
    "Q7981191": "Wellcome Collection",
    "Q461": "Internet Archive",
}


def truthy(statements: list[dict]) -> list[dict]:
    """The values the query service exposes as wdt: preferred rank if any, else normal; never deprecated."""
    preferred = [s for s in statements if s.get("rank") == "preferred"]
    return preferred or [s for s in statements if s.get("rank") == "normal"]


def item_values(claims: dict, prop: str) -> list[str]:
    out = []
    for s in truthy(claims.get(prop, [])):
        snak = s.get("mainsnak", {})
        # "somevalue" (unknown) and "novalue" carry no datavalue and are skipped.
        if snak.get("snaktype") == "value" and snak.get("datatype") == "wikibase-item":
            out.append(snak["datavalue"]["value"]["id"])
    return out


def year_of(time: str) -> int:
    """'+1650-00-00T00:00:00Z' -> 1650; '-0300-...' -> -300 (Wikidata writes BCE years as negative)."""
    sign = -1 if time.startswith("-") else 1
    return sign * int(time[1:].split("-", 1)[0])


def date_years(claims: dict) -> list[int]:
    years = []
    for prop in DATE_PROPS:
        for s in truthy(claims.get(prop, [])):
            snak = s.get("mainsnak", {})
            if snak.get("snaktype") != "value" or snak.get("datatype") != "time":
                continue
            value = snak["datavalue"]["value"]
            if value.get("precision", 0) >= CENTURY_PRECISION:
                years.append(year_of(value["time"]))
    return years


def century(year: int) -> int:
    """1601..1700 -> 17; -100..-1 -> -1 (1st century BCE). There is no century 0; year 0 counts as 1 BCE."""
    if year >= 1:
        return (year - 1) // 100 + 1
    return -((max(-year, 1) - 1) // 100 + 1)


def centuries(start: int, end: int) -> list[int]:
    lo, hi = sorted((century(start), century(end)))
    return [c for c in range(lo, hi + 1) if c != 0]


def century_id(c: int) -> str:
    return f"century:{c}"


def century_label(c: int) -> str:
    n = abs(c)
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix} century" + (" BCE" if c < 0 else "")


def fetch_entities(wm: Wikimedia, qids: list[str], name: str) -> tuple[dict[str, dict], dict[str, str], list[str]]:
    """Entity JSON by id, redirects (asked id -> current id) and ids Wikidata reports missing."""
    entities, redirects, missing = {}, {}, []
    for i in range(0, len(qids), BATCH):
        chunk = qids[i : i + BATCH]
        params = {
            "action": "wbgetentities",
            "ids": "|".join(chunk),
            "props": "claims|labels|info",
            "languages": "|".join(LANGS),
            "format": "json",
        }
        data = wm.get_json(f"{name}_{i // BATCH:03d}", API, params)
        if "error" in data:
            raise SystemExit(f"wbgetentities error in batch {i // BATCH}: {data['error']}")
        for asked, ent in data.get("entities", {}).items():
            if "missing" in ent:
                missing.append(asked)
                continue
            if "redirects" in ent:
                redirects[ent["redirects"]["from"]] = ent["redirects"]["to"]
            entities[ent["id"]] = ent
    return entities, redirects, missing


def connected_components(nodes: list[str], edges: list[tuple[str, str]]):
    """Component sizes, largest first, and the root finder, treating edges as undirected (union-find)."""
    parent = {n: n for n in nodes}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in edges:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    sizes = Counter(find(n) for n in nodes)
    return sorted(sizes.values(), reverse=True), find


def write_gz(path, lines: list[str]) -> None:
    # gzip with mtime 0 and no file name, so the same graph gives the same bytes.
    buf = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=buf, mtime=0) as gz:
        gz.write("".join(line + "\n" for line in lines).encode("utf-8"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(buf.getvalue())


def build(records: list[dict], entities: dict[str, dict], redirects: dict[str, str]):
    """Nodes and edges from records and fetched entity JSON. Kept apart from fetching so it can be tested."""
    canon = lambda q: redirects.get(q, q)  # noqa: E731
    corpus_entities = {canon(q) for r in records for q in r["entity_ids"]} & set(entities)
    edges: set[tuple[str, str, str, str, str]] = set()  # source, relation, target, origin, revision
    counts = Counter()

    for r in records:
        for q in r["entity_ids"]:
            edges.add((r["id"], "about", canon(q), "corpus", ""))
        if r.get("period_start") is not None:
            end = r["period_end"] if r.get("period_end") is not None else r["period_start"]
            for c in centuries(r["period_start"], end):
                edges.add((r["id"], "in_period", century_id(c), "derived", ""))

    # Statement edges to targets outside the corpus wait until we know how many corpus entities share them.
    pending: dict[str, set[tuple[str, str, str]]] = defaultdict(set)
    for q in sorted(corpus_entities):
        ent = entities[q]
        claims, rev = ent.get("claims", {}), str(ent.get("lastrevid", ""))
        for prop in RELATIONS:
            for t in item_values(claims, prop):
                t = canon(t)
                if t == q:
                    counts["self loops skipped"] += 1
                elif t in SOURCE_INSTITUTIONS:
                    counts["edges to a source institution skipped"] += 1
                elif t in corpus_entities:
                    edges.add((q, prop, t, "wikidata", rev))
                else:
                    pending[t].add((q, prop, rev))
        years = date_years(claims)
        if years:
            for c in centuries(min(years), max(years)):
                edges.add((q, "in_period", century_id(c), "derived", rev))

    connectors = {t for t, src in pending.items() if len({s for s, _, _ in src}) >= MIN_CONNECTOR_SOURCES}
    for t in connectors:
        for q, prop, rev in pending[t]:
            edges.add((q, prop, t, "wikidata", rev))
    counts["connector candidates"] = len(pending)
    counts["connectors kept"] = len(connectors)
    counts["connector candidates dropped (one corpus entity)"] = len(pending) - len(connectors)
    counts["statement edges dropped with them"] = sum(len(pending[t]) for t in pending if t not in connectors)
    return corpus_entities, connectors, sorted(edges), counts


def node_rows(records, corpus_entities, connectors, edges, entities, gaz_type) -> list[dict]:
    rows = [{"id": r["id"], "kind": "document", "type": r["doc_type"], "labels": {"en": r["title"]}} for r in records]
    for q in sorted(corpus_entities | connectors):
        ent = entities.get(q, {})
        labels = {lang: v["value"] for lang, v in sorted(ent.get("labels", {}).items())}
        classes = sorted(set(item_values(ent.get("claims", {}), "P31")))
        rows.append(
            {
                "id": q,
                "kind": "entity" if q in corpus_entities else "connector",
                "type": gaz_type.get(q, "other"),
                "labels": labels,
                "classes": classes,
                "revision": ent.get("lastrevid"),
            }
        )
    used = sorted({e[2] for e in edges if e[1] == "in_period"}, key=lambda s: int(s.split(":")[1]))
    rows += [{"id": c, "kind": "period", "type": "century", "labels": {"en": century_label(int(c.split(":")[1]))}}
             for c in used]  # fmt: skip
    return rows


def statistics(records, nodes, edges, counts, redirects, missing) -> dict:
    kind_of = {n["id"]: n["kind"] for n in nodes}
    label_of = {n["id"]: n["labels"].get("en") or next(iter(n["labels"].values()), "") for n in nodes}
    degree = Counter()
    for s, _, t, _, _ in edges:
        degree[s] += 1
        degree[t] += 1
    sizes, find = connected_components([n["id"] for n in nodes], [(s, t) for s, _, t, _, _ in edges])
    comp_size = Counter(find(n["id"]) for n in nodes)
    giant = comp_size.most_common(1)[0][0]
    docs = [n["id"] for n in nodes if n["kind"] == "document"]
    docs_in_giant = sum(1 for d in docs if find(d) == giant)
    by_kind_degree = defaultdict(list)
    for n in nodes:
        by_kind_degree[n["kind"]].append(degree[n["id"]])

    def summary(values: list[int]) -> dict:
        v = sorted(values)
        return {"nodes": len(v), "min": v[0], "median": v[len(v) // 2], "max": v[-1], "mean": round(sum(v) / len(v), 2)}

    hubs = [n for n, _ in degree.most_common() if kind_of.get(n) != "document"][:TOP_HUBS]
    return {
        "nodes": len(nodes),
        "edges": len(edges),
        "nodes_by_kind": dict(Counter(n["kind"] for n in nodes).most_common()),
        "entity_nodes_by_type": dict(
            Counter(n["type"] for n in nodes if n["kind"] in ("entity", "connector")).most_common()
        ),
        "edges_by_relation": {
            rel: {"label": RELATIONS.get(rel, rel.replace("_", " ")), "edges": n}
            for rel, n in Counter(e[1] for e in edges).most_common()
        },
        "degree_by_kind": {k: summary(v) for k, v in by_kind_degree.items()},
        "components": {"count": len(sizes), "largest": sizes[0], "sizes_top10": sizes[:10]},
        "documents": len(docs),
        "documents_in_largest_component": docs_in_giant,
        "top_hubs": [
            {"id": h, "label": label_of.get(h, ""), "kind": kind_of.get(h), "degree": degree[h]} for h in hubs
        ],
        "build": dict(counts),
        "redirects": len(redirects),
        "missing_entities": sorted(missing),
    }


def markdown(report: dict) -> str:
    s = report["stats"]
    lines = [
        "# Core Wikidata graph v1: statistics",
        "",
        f"Generated by `src/graph/core_graph.py` on {report['date']} at commit `{report['commit']}`"
        " (decision 0020). Do not edit by hand.",
        "",
        f"{s['nodes']:,} nodes and {s['edges']:,} edges, layer `core`. {s['documents_in_largest_component']:,} of"
        f" {s['documents']:,} documents are in the largest connected component ({s['components']['largest']:,} nodes"
        f" of {s['nodes']:,}; {s['components']['count']:,} components).",
        "",
        "| Node kind | Nodes |",
        "| --- | --- |",
        *[f"| {k} | {v:,} |" for k, v in s["nodes_by_kind"].items()],
        "",
        "| Entity type (gazetteer; `other` = not in the gazetteer) | Nodes |",
        "| --- | --- |",
        *[f"| {k} | {v:,} |" for k, v in s["entity_nodes_by_type"].items()],
        "",
        "| Relation | Label | Edges |",
        "| --- | --- | --- |",
        *[f"| {k} | {v['label']} | {v['edges']:,} |" for k, v in s["edges_by_relation"].items()],
        "",
        "| Node kind | Min degree | Median | Mean | Max |",
        "| --- | --- | --- | --- | --- |",
        *[f"| {k} | {v['min']} | {v['median']} | {v['mean']} | {v['max']:,} |" for k, v in s["degree_by_kind"].items()],
        "",
        f"Largest components: {', '.join(f'{x:,}' for x in s['components']['sizes_top10'])}.",
        "",
        "Top hubs (not documents), before down-weighting:",
        "",
        "| Node | Label | Kind | Degree |",
        "| --- | --- | --- | --- |",
        *[f"| {h['id']} | {h['label']} | {h['kind']} | {h['degree']:,} |" for h in s["top_hubs"]],
        "",
        "Build counts:",
        "",
        *[f"- {k}: {v:,}" for k, v in s["build"].items()],
        f"- redirected entity ids followed: {s['redirects']:,}",
        f"- entity ids Wikidata reports missing: {len(s['missing_entities']):,}"
        + (f" ({', '.join(s['missing_entities'])})" if s["missing_entities"] else ""),
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    records = [json.loads(line) for line in gzip.open(SNAPSHOT, "rt", encoding="utf-8")]
    gaz_type = {e["qid"]: e["type"] for e in map(json.loads, gzip.open(GAZETTEER, "rt", encoding="utf-8"))}
    wm = Wikimedia(RAW_DIR)

    asked = sorted({q for r in records for q in r["entity_ids"]})
    entities, redirects, missing = fetch_entities(wm, asked, "entities")
    corpus_entities, connectors, edges, counts = build(records, entities, redirects)
    # Connectors are fetched only for their labels and classes; their own statements are not followed.
    extra, more_redirects, more_missing = fetch_entities(wm, sorted(connectors - set(entities)), "connectors")
    entities.update(extra)
    redirects.update(more_redirects)
    missing += more_missing

    nodes = node_rows(records, corpus_entities, connectors, edges, entities, gaz_type)
    write_gz(OUT_DIR / "nodes.jsonl.gz", [json.dumps(n, ensure_ascii=False, sort_keys=True) for n in nodes])
    header = "source\trelation\ttarget\tlayer\torigin\trevision"
    write_gz(OUT_DIR / "edges.tsv.gz", [header] + [f"{s}\t{r}\t{t}\t{LAYER}\t{o}\t{v}" for s, r, t, o, v in edges])

    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    report = {
        "date": datetime.now(UTC).date().isoformat(),
        "commit": commit,
        "requests": {"fetched": wm.fetched, "reused": wm.reused},
        "relations": RELATIONS,
        "min_connector_sources": MIN_CONNECTOR_SOURCES,
        "stats": statistics(records, nodes, edges, counts, redirects, missing),
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.with_suffix(".json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    REPORT.with_suffix(".md").write_text(markdown(report), encoding="utf-8")
    print(markdown(report))


if __name__ == "__main__":
    main()
