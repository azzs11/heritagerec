"""Coverage tiers of entities: rich, middle, sparse (decision 0031, step 3).

An entity's coverage score is the mean of two percentile ranks among the corpus's document entities: its
statement count and its total sitelink count on Wikidata. Tertiles of that score over the document entities give
the cut points; any entity, in the corpus or not, is placed by the same ranks.

These tiers are PROVISIONAL: 0031 fixes them on the frozen snapshot (week 9). Here the statement counts come from
the saved core-graph responses (data/raw/graph_core_v1/) and the sitelink counts from one fetch, saved untouched
under data/raw/tiers_v1/. They are used now only to check the sparse-tier quotas of the query split.

Usage:
    uv run python -m src.queries.tiers           cut points and the tier of every document entity
Outputs:
    results/queries/tiers_provisional_v1.json
"""

import bisect
import gzip
import json
from functools import lru_cache

from src.corpus.wikimedia import ROOT, Wikimedia

RAW_GRAPH = ROOT / "data/raw/graph_core_v1"
RAW = ROOT / "data/raw/tiers_v1"
EDGES = ROOT / "data/graph/core_v1/edges.tsv.gz"
REPORT = ROOT / "results/queries/tiers_provisional_v1.json"
API = "https://www.wikidata.org/w/api.php"
TIERS = ("sparse", "middle", "rich")


def document_entities() -> list[str]:
    out = set()
    with gzip.open(EDGES, "rt", encoding="utf-8") as f:
        next(f)
        for line in f:
            source, relation, target, *_ = line.split("\t")
            if relation == "about":
                out.add(target)
    return sorted(out)


def saved_statements() -> dict[str, int]:
    """Statement counts from the core graph's saved wbgetentities responses."""
    out = {}
    for path in sorted(RAW_GRAPH.glob("entities_*.json.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as f:
            for qid, entity in json.load(f).get("entities", {}).items():
                out[qid] = sum(len(v) for v in entity.get("claims", {}).values())
    return out


def fetch(wm: Wikimedia, qids: list[str], props: str) -> dict:
    out = {}
    for i in range(0, len(qids), 50):
        data = wm.get_json(
            "tiers_entities",
            API,
            {"action": "wbgetentities", "ids": "|".join(qids[i : i + 50]), "props": props, "format": "json"},
        )
        out.update(data.get("entities", {}))
    return out


def percentile(sorted_values: list[int], value: int) -> float:
    """Share of the reference values at or below this one (a mid-rank for ties)."""
    lo = bisect.bisect_left(sorted_values, value)
    hi = bisect.bisect_right(sorted_values, value)
    return (lo + hi) / 2 / len(sorted_values)


class Tiers:
    def __init__(self, statements: dict[str, int], sitelinks: dict[str, int]):
        qids = sorted(set(statements) & set(sitelinks))
        self.statements = sorted(statements[q] for q in qids)
        self.sitelinks = sorted(sitelinks[q] for q in qids)
        scores = sorted(self.score(statements[q], sitelinks[q]) for q in qids)
        self.cuts = (scores[len(scores) // 3], scores[2 * len(scores) // 3])
        self.n = len(qids)

    def score(self, statements: int, sitelinks: int) -> float:
        return (percentile(self.statements, statements) + percentile(self.sitelinks, sitelinks)) / 2

    def tier(self, statements: int, sitelinks: int) -> str:
        s = self.score(statements, sitelinks)
        return "sparse" if s < self.cuts[0] else ("middle" if s < self.cuts[1] else "rich")


@lru_cache(maxsize=1)
def build() -> tuple[Tiers, Wikimedia]:
    wm = Wikimedia(RAW, pause=1.0)
    docs = document_entities()
    statements = saved_statements()
    sitelinks = {q: len(e.get("sitelinks", {})) for q, e in fetch(wm, docs, "sitelinks").items() if "missing" not in e}
    return Tiers({q: statements[q] for q in docs if q in statements}, sitelinks), wm


def tier_of(qids: list[str]) -> dict[str, dict]:
    """Tier, statements and sitelinks of any entities (fetched if not in the saved responses)."""
    tiers, wm = build()
    ents = fetch(wm, sorted(set(qids)), "claims|sitelinks")
    out = {}
    for q in qids:
        e = ents.get(q, {})
        if not e or "missing" in e:
            out[q] = {"tier": "", "statements": None, "sitelinks": None}
            continue
        st = sum(len(v) for v in e.get("claims", {}).values())
        sl = len(e.get("sitelinks", {}))
        out[q] = {"tier": tiers.tier(st, sl), "statements": st, "sitelinks": sl}
    return out


def main() -> None:
    tiers, wm = build()
    report = {
        "provisional": True,
        "note": "Fixed on the frozen snapshot at week 9 (decision 0031); these cut points are for the query split only.",
        "document_entities": tiers.n,
        "score_cuts": [round(c, 4) for c in tiers.cuts],
        "statements_median": tiers.statements[len(tiers.statements) // 2],
        "sitelinks_median": tiers.sitelinks[len(tiers.sitelinks) // 2],
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2) + "\n")
    print(report, f"; Wikidata calls {wm.fetched} fetched, {wm.reused} reused")


if __name__ == "__main__":
    main()
