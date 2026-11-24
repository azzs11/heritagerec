"""Generate docs/data_card.md from the snapshot, its manifest and the collection reports.

Every number in the data card is computed here from committed or regenerable files;
nothing is written in by hand. Re-run after every snapshot build.

Usage:
    uv run python -m src.corpus.data_card
"""

import csv
import gzip
import json
import statistics
from collections import Counter, defaultdict

from src.corpus.wikimedia import ROOT

SNAPSHOT = ROOT / "data/corpus_v1/records.jsonl.gz"
MANIFEST = ROOT / "data/corpus_v1/manifest.json"
REPORTS = ROOT / "results/collection"
SEED_LISTS = {
    "seeds": ROOT / "data/seeds/seeds_v1.csv",
    "ASI remainder": ROOT / "data/seeds/asi_remainder_v1.csv",
    "neighbours": ROOT / "data/seeds/neighbours_v1.csv",
    "class list": ROOT / "data/seeds/class_list_v1.csv",
}
LINKS_REPORT = ROOT / "results/linking/object_links_v1.json"
GRAPH_REPORT = ROOT / "results/graph/core_v1.json"
PASSAGE_MANIFEST = ROOT / "data/passages/manifest_v1.json"
SEED_REPORT = ROOT / "data/seeds/seed_report.md"
OUT = ROOT / "docs/data_card.md"
LICENCE_NAMES = {
    "https://creativecommons.org/licenses/by-sa/4.0/": "CC BY-SA 4.0",
    "https://creativecommons.org/publicdomain/zero/1.0/": "CC0 1.0",
    "https://creativecommons.org/publicdomain/mark/1.0/": "Public Domain Mark 1.0",
    "https://creativecommons.org/licenses/by/4.0/": "CC BY 4.0",
}


def table(header: list[str], rows: list[list]) -> list[str]:
    return [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
        *["| " + " | ".join(str(c) for c in r) + " |" for r in rows],
    ]


def fmt(n) -> str:
    return f"{n:,}" if isinstance(n, int) else str(n)


def target_sentence(n: int) -> str:
    if n >= 10_000:
        return (
            "The specification's target was about 10,000 documents; the corpus meets it without out-of-scope"
            " documents (decisions 0015, 0017, 0018)."
        )
    return (
        "The specification's target was about 10,000 documents. The corpus is smaller; it is not padded with"
        " out-of-scope documents (decisions 0015, 0017, 0018)."
    )


def linking_section() -> list[str]:
    if not LINKS_REPORT.exists():
        return []
    rep = json.load(open(LINKS_REPORT, encoding="utf-8"))
    rows = []
    for name, c in rep["by_file"].items():
        if isinstance(c, dict):
            rows.append([name, fmt(c["records"]), fmt(c.get("with layer 1", 0)), fmt(c.get("with layer 2", 0)),
                         fmt(c.get("with layer 3", 0)), fmt(c.get("linked to India only", 0))])  # fmt: skip
    return [
        "## Entity links of museum objects (decision 0017)",
        "",
        "Layer 1: links the museum gives. Layer 2: structured fields matched against the gazetteer by entity type."
        " Layer 3: names in titles and descriptions, kept as mentions in `data/corpus_v1/links_v1.jsonl.gz` only."
        " Precision per layer comes from the author's check of `results/linking/link_check_sample_v1.csv`.",
        "",
        *table(["Staging file", "Records", "Layer 1", "Layer 2", "Layer 3", "India only"], rows),
        "",
    ]


def graph_section() -> list[str]:
    if not GRAPH_REPORT.exists():
        return []
    rep = json.load(open(GRAPH_REPORT, encoding="utf-8"))
    s = rep["stats"]
    return [
        "## Knowledge graph: core Wikidata layer (decision 0020)",
        "",
        f"Built by `src/graph/core_graph.py` on {rep['date']} at commit `{rep['commit']}`:"
        f" {fmt(s['nodes'])} nodes and {fmt(s['edges'])} edges. {fmt(s['documents_in_largest_component'])} of"
        f" {fmt(s['documents'])} documents are in the largest connected component"
        f" ({fmt(s['components']['count'])} components). Hubs are down-weighted at retrieval time (decision 0007),"
        " not in the graph. Full statistics: `results/graph/core_v1.md`.",
        "",
        *table(["Node kind", "Nodes"], [[k, fmt(v)] for k, v in s["nodes_by_kind"].items()]),
        "",
        *table(
            ["Relation", "Label", "Edges"],
            [[k, v["label"], fmt(v["edges"])] for k, v in s["edges_by_relation"].items()],
        ),
        "",
        *[f"- {k}: {fmt(v)}" for k, v in s["build"].items()],
        "",
    ]


PROXIMITY = ROOT / "results/graph/proximity_v1.json"


def proximity_section() -> list[str]:
    """The proximity layer (decision 0030), written from its own report so a regeneration never drops it."""
    if not PROXIMITY.exists():
        return []
    r = json.load(open(PROXIMITY, encoding="utf-8"))
    st = r["settings"]
    return [
        "## Knowledge graph: proximity layer (decision 0030)",
        "",
        "A separate layer, never part of the headline core result. Built by `src/graph/proximity_layer.py` on"
        f" {r['built']} at commit `{r['commit'][:7]}`: each placed entity that is not a hub is put in its"
        f" resolution-{st['resolution']} H3 hexagon (Uber's grid) and joined by a `near` edge to its {st['nearest']}"
        f" nearest places within {st['rings']} ring of hexagons; each edge keeps its ring distance and length in km. It"
        f" holds no text similarity. {fmt(r['edges'])} edges among {fmt(r['places'])} places; counts, degrees and"
        " components: `results/graph/proximity_v1.md`.",
        "",
    ]


COVERAGE = ROOT / "results/coverage_audit/coverage_v1.json"
COVERAGE_ROWS = [
    "item on Wikidata",
    "English Wikipedia article",
    "Hindi label",
    "Kannada label",
    "local-language Wikipedia article",
    "in corpus v1",
]
STRATA = {
    "karnataka_state": "Karnataka, state list",
    "karnataka_asi": "Karnataka, ASI",
    "hindi_belt_state": "Madhya Pradesh, state list",
    "hindi_belt_asi": "Hindi belt, ASI",
    "rest_asi": "Rest of India, ASI",
    "unesco_ich": "UNESCO intangible heritage",
}


def coverage_section() -> list[str]:
    """What the corpus can know: official lists against Wikidata (decisions 0031, 0032), read from the audit's file."""
    if not COVERAGE.exists():
        return []
    rep = json.load(open(COVERAGE, encoding="utf-8"))
    strata = rep["strata"]

    def cell(m: dict) -> str:
        return "n/a" if m["share"] is None else f"{m['share']:.0%} [{m['ci95'][0]:.0%}, {m['ci95'][1]:.0%}]"

    return [
        "## Coverage of official heritage lists (decisions 0031, 0032)",
        "",
        "Every document enters through a Wikidata entity, so the corpus can only hold heritage Wikidata describes. A"
        " seeded sample of official lists (ASI centrally protected monuments, the Karnataka and Madhya Pradesh state"
        " lists, UNESCO intangible heritage for India) was matched to Wikidata by hand. Shares of the sampled entries,"
        f" with Wilson 95% intervals; generated by `src/coverage_audit/fill.py` on {rep['generated'][:10]} at commit"
        f" `{rep['commit'][:7]}` ({rep['progress'].get('matched', 0)} matched, {rep['progress'].get('none', 0)} with no"
        " item). Full table: `results/coverage_audit/coverage_v1.md`.",
        "",
        *table(
            ["Share of entries with", *[STRATA.get(s, s) for s in strata]],
            [[m, *[cell(strata[s]["measures"][m]) for s in strata]] for m in COVERAGE_ROWS],
        ),
        "",
        "Claims made with this corpus are scoped to heritage that Wikidata describes as of the snapshot; results are"
        " also reported by coverage tier (decision 0031).",
        "",
    ]


def passage_section() -> list[str]:
    if not PASSAGE_MANIFEST.exists():
        return []
    m = json.load(open(PASSAGE_MANIFEST, encoding="utf-8"))
    st = m["settings"]
    return [
        "## Passages for retrieval (decision 0023)",
        "",
        f"Every document is split into passages of {st['words']} words with a {st['stride']}-word stride, each"
        " starting with the document's title; every retrieval system uses the same passages and scores a document"
        f" by its best passage. {fmt(m['passages_total'])} passages (`{m['passages']['path']}`, SHA-256"
        f" `{m['passages']['sha256']}`), built {m['built']} at commit `{m['commit']}`.",
        "",
        *table(
            ["Language", "Documents", "Passages"],
            [[k, fmt(m["documents_by_language"][k]), fmt(v)] for k, v in m["passages_by_language"].items()],
        ),  # fmt: skip
        "",
        *table(["Source", "Passages"], [[k, fmt(v)] for k, v in m["passages_by_source"].items()]),
        "",
    ]


def main() -> None:
    records = [json.loads(line) for line in gzip.open(SNAPSHOT, "rt", encoding="utf-8")]
    manifest = json.load(open(MANIFEST, encoding="utf-8"))
    n = len(records)

    lists, state = {}, {}
    for name, path in SEED_LISTS.items():
        for r in csv.DictReader(open(path, encoding="utf-8")):
            lists.setdefault(r["qid"], name)
            if r.get("state"):
                state[r["qid"]] = r["state"]

    by = {k: Counter(r[k] for r in records) for k in ("source", "language", "doc_type")}
    by_list = Counter(
        lists.get(r["entity_ids"][0], "museum objects collected by place (decision 0017)") for r in records
    )
    by_licence = Counter(LICENCE_NAMES.get(r["licence"], r["licence"]) for r in records)
    by_state = Counter(state[r["entity_ids"][0]] for r in records if r["entity_ids"][0] in state)
    with_state = sum(by_state.values())
    lengths = defaultdict(list)
    for r in records:
        lengths[(r["source"], r["doc_type"])].append(len(r["text"]))
    with_period = sum(1 for r in records if r["period_start"] is not None)
    multi = sum(1 for r in records if len(r["entity_ids"]) > 1)
    centuries = Counter(
        f"{(r['period_start'] // 100) + 1}th c." if r["period_start"] > 0 else "BCE"
        for r in records
        if r["period_start"] is not None
    )

    reports = {p.stem: json.load(open(p, encoding="utf-8")) for p in sorted(REPORTS.glob("*_v1.json"))}
    seed_notes = [
        line
        for line in open(SEED_REPORT, encoding="utf-8").read().splitlines()
        if line.startswith(("- Fewer than 5 seeds", "- No cultural seed", "- No site seed"))
    ]
    snap = manifest["snapshot"]

    lines = [
        "# Data card: HeritageRec corpus v1",
        "",
        f"Generated by `src/corpus/data_card.py` from `{snap['path']}` (SHA-256 `{snap['sha256']}`,"
        f" {fmt(snap['bytes'])} bytes), built {manifest['built']} at commit `{manifest['commit']}`."
        " Do not edit by hand; re-run the script after every snapshot build.",
        "",
        "## Summary",
        "",
        f"{fmt(n)} documents about the heritage of the Republic of India (decision 0001), in English, Hindi and"
        f" Kannada, each linked to at least one Wikidata entity. {fmt(multi)} documents are linked to more than one"
        f" entity. Raw API responses: {fmt(manifest['raw_files']['count'])} files,"
        f" {fmt(manifest['raw_files']['bytes'])} bytes, each listed with its SHA-256 in `data/corpus_v1/manifest.json`.",
        "",
        target_sentence(n),
        "",
        "## Documents by source, language, type and licence",
        "",
        *table(["Source", "Documents"], [[k, fmt(v)] for k, v in by["source"].most_common()]),
        "",
        *table(["Language", "Documents"], [[k, fmt(v)] for k, v in by["language"].most_common()]),
        "",
        *table(["Document type", "Documents"], [[k, fmt(v)] for k, v in by["doc_type"].most_common()]),
        "",
        *table(["Licence", "Documents"], [[k, fmt(v)] for k, v in by_licence.most_common()]),
        "",
        "## Documents by entity list",
        "",
        *table(
            ["Entity list (first linked entity)", "Documents"],
            [[k, fmt(v)] for k, v in by_list.most_common()],
        ),
        "",
        f"{fmt(manifest['duplicates_merged'])} pages reached from two lists were merged into one record each.",
        "",
        *linking_section(),
        *graph_section(),
        *proximity_section(),
        *passage_section(),
        *coverage_section(),
        "## Text length (characters)",
        "",
        *table(
            ["Source", "Document type", "Documents", "Median", "Min", "Max"],
            [
                [s, t, fmt(len(v)), fmt(int(statistics.median(v))), fmt(min(v)), fmt(max(v))]
                for (s, t), v in sorted(lengths.items())
            ],
        ),
        "",
        "Internet Archive documents are whole digitised books (decision 0016); retrieval systems split long"
        " documents into passages and score each document by its best passage.",
        "",
        "## Coverage by state and period",
        "",
        f"State is known for documents whose first entity is a seed with a resolved state: {fmt(with_state)} of"
        f" {fmt(n)}. Documents of the ASI remainder and neighbour lists carry no state yet.",
        "",
        *table(["State or union territory", "Documents"], [[k, fmt(v)] for k, v in by_state.most_common()]),
        "",
        "Places that could not be filled at seed selection (from `data/seeds/seed_report.md`):",
        "",
        *seed_notes,
        "",
        f"A period (start year) is known for {fmt(with_period)} of {fmt(n)} documents, almost all of them museum and"
        " library records; Wikipedia articles carry no period yet.",
        "",
        *table(
            ["Period start", "Documents"], [[k, fmt(v)] for k, v in sorted(centuries.items(), key=lambda kv: kv[0])]
        ),
        "",
        "## Collection outcomes",
        "",
        "Every record a collector looked at, and why it was kept or left out (from `results/collection/`).",
        "",
    ]
    for name, rep in reports.items():
        if name.endswith("_sample_v1"):
            continue
        outcomes = rep.get("outcomes", {})
        lines += [f"**{name}** ({fmt(rep.get('records', 0))} records):", ""]
        lines += [f"- {k}: {fmt(v)}" for k, v in outcomes.items()]
        lines += [""]

    lines += [
        "## Known limitations",
        "",
        "- Name matching across collections fails for homonyms and generic seed names. Examples seen during"
        " collection: the seed 'Lotus Temple' (Delhi) matched the Golden Lotus tank in Madurai; 'Khyal' (a"
        " music form) matched a modern poem; 'Gopala' (a Pala king) matched an editor named Gopala Bhatta;"
        " 'Francis Xavier' matched a nun named after him. Dynasty seeds require a polity word next to the name,"
        " which removed matches such as 'Nanda' for Krishna's foster-father.",
        "- Devanagari text tagged Hindi by the Internet Archive may be Sanskrit; script alone cannot tell them apart.",
        "- Wellcome contributes pictures only: its Indian manuscripts are catalogued under Sanskrit titles, which"
        " seed-name searches do not reach.",
        "- Internet Archive items with no year in their date or title are left out, because their public-domain"
        " mark cannot be checked; items dated 1950 or later are left out too.",
        "- The neighbour selection's drift sample (`results/probes/neighbour_select_v1.md`) awaits the author's"
        " hand check; hand-scan decisions made during collection are marked 'pending author review' in"
        " `data/seeds/curated/`.",
        "",
        "## Disclosure",
        "",
        "Documents are collected, not generated: no synthetic or augmented text. Museum and library records keep"
        " their own fields as text; Wikipedia text comes from the TextExtracts API with revision IDs recorded"
        " (decision 0003).",
        "",
    ]
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({len(lines)} lines)")


if __name__ == "__main__":
    main()
