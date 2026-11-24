"""Entity-expanded BM25: the control that tests whether the graph wins only because it knows the entities (0033).

For each query, the linker (decision 0026) finds the entities it names, the same ones the graph lens starts from.
Their names, exactly the names the linker trusts (labels and aliases in English, Hindi and Kannada, with its filters),
expand the query. Every language index is searched:

- the index of the query's own language with the query's words (weight 1) and the names in that language
  (weight alpha, shared over the names' terms, so that a long alias list never outweighs a short query);
- each other index with the names in its language only, so the control can cross languages through the same
  entities the graph uses, which RQ3 needs;

each index's documents (best passage, as in every BM25 run) are scaled to 0-1 by min-max, and the lists merged by
score. A query that links to no entity is plain BM25 in its own language: with nothing to expand, the control and the
baseline coincide. alpha is chosen on dev among 0.25, 0.5 and 1; the untuned alpha = 1 is reported beside it.

Usage:
    uv run python -m src.retrieval.entity_bm25 --queries data/queries/dev_v1.tsv [--alpha 0.5]
Output:
    results/retrieval/runs/bm25_ent_a<alpha>_<stem>.trec, top 100 documents per query
    results/retrieval/bm25_ent_a<alpha>_<stem>.json: per query, the entities and the names used, per index
"""

import argparse
import csv
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from src.corpus.wikimedia import ROOT
from src.retrieval.bm25 import (
    BM25,
    DOC_DEPTH,
    INDEX_DIR,
    LANGS,
    PASSAGE_DEPTH,
    QUERY_ANALYZER,
    RUNS,
    java_env,
    max_passage,
)

ALPHAS = (0.25, 0.5, 1.0)


def weighted_terms(query_terms: list[str], name_terms: list[str], alpha: float) -> list[tuple[str, float]]:
    """(term, boost) pairs: query terms at 1; name terms sharing alpha times the query's weight between them.

    With no query terms (an index in another language), the names stand alone at weight 1 each, since min-max
    scaling per index removes any common factor.
    """
    out: list[tuple[str, float]] = [(t, 1.0) for t in dict.fromkeys(query_terms)]
    names = [t for t in dict.fromkeys(name_terms)]
    if not names:
        return out
    each = alpha * len(out) / len(names) if out else 1.0
    return out + [(t, each) for t in names]


def min_max(ranked: list[tuple[str, float]]) -> list[tuple[str, float]]:
    if not ranked:
        return []
    hi, lo = ranked[0][1], ranked[-1][1]
    span = hi - lo
    return [(d, (s - lo) / span if span > 0 else 1.0) for d, s in ranked]


def merge(per_index: dict[str, list[tuple[str, float]]], first: str, depth: int = DOC_DEPTH) -> list[tuple[str, float]]:
    """Each index's ranking scaled to 0-1, then merged by score.

    Min-max scaling gives every index's top document 1.0, so ties are common. They are broken by rank within the
    index, then the query's own language first and the others in a fixed order, then document id. A tie-break by id
    alone would put English first every time, which is a language bias in a control that tests crossing languages.
    """
    order = [first] + [lang for lang in LANGS if lang != first]
    rows = []
    for lang, ranked in per_index.items():
        for rank, (doc, s) in enumerate(min_max(ranked), 1):
            rows.append((-s, rank, order.index(lang) if lang in order else len(order), doc, s))
    best: dict[str, tuple] = {}
    for row in sorted(rows):
        best.setdefault(row[3], row)  # a document in two indexes keeps its better place
    return [(r[3], r[4]) for r in sorted(best.values())][:depth]


class Searcher:
    def __init__(self, alpha: float):
        java_env()
        from pyserini.analysis import Analyzer, get_lucene_analyzer
        from pyserini.search.lucene import LuceneSearcher
        from pyserini.search.lucene.querybuilder import (
            JBooleanClauseOccur,
            JTerm,
            JTermQuery,
            get_boolean_query_builder,
            get_boost_query,
        )

        self.alpha = alpha
        self.analyzers = {lang: Analyzer(get_lucene_analyzer(**QUERY_ANALYZER[lang])) for lang in LANGS}
        self.searchers = {}
        for lang in LANGS:
            s = LuceneSearcher(str(INDEX_DIR / lang))
            s.set_bm25(**BM25)
            self.searchers[lang] = s
        self._q = (JBooleanClauseOccur, JTerm, JTermQuery, get_boolean_query_builder, get_boost_query)

    def query(self, terms: list[tuple[str, float]]):
        occur, jterm, jtermquery, builder, boost = self._q
        b = builder()
        for t, w in terms:
            b.add(boost(jtermquery(jterm("contents", t)), w), occur.should.value)
        return b.build()

    def run(self, text: str, lang: str, names: dict[str, list[str]]) -> tuple[list[tuple[str, float]], dict]:
        used: dict[str, dict] = {}
        per_index: dict[str, list[tuple[str, float]]] = {}
        for index_lang in LANGS:
            analyse = self.analyzers[index_lang].analyze
            query_terms = analyse(text) if index_lang == lang else []
            name_terms = [t for n in names.get(index_lang, []) for t in analyse(n)]
            terms = weighted_terms(query_terms, name_terms, self.alpha)
            if not terms:
                continue
            hits = [(h.docid, h.score) for h in self.searchers[index_lang].search(self.query(terms), k=PASSAGE_DEPTH)]
            per_index[index_lang] = max_passage(hits)
            used[index_lang] = {"names": names.get(index_lang, []), "terms": len(terms)}
        return merge(per_index, lang), used


def entity_names(text: str) -> tuple[list[str], dict[str, list[str]]]:
    """The entities the linker finds in the query and their trusted names, pooled per language."""
    from src.graph_retrieval.linker import link, load

    g = load()
    seeds = list(link(text, g)["seeds"])
    names: dict[str, list[str]] = {}
    for q in seeds:
        for lang, ns in g.names.get(q, {}).items():
            names.setdefault(lang, [])
            names[lang] += [n for n in ns if n not in names[lang]]
    return seeds, names


def alpha_tag(alpha: float) -> str:
    return f"a{round(alpha * 100):03d}"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--queries", type=Path, required=True)
    p.add_argument("--alpha", type=float, default=0.5, choices=ALPHAS)
    a = p.parse_args()
    rows = list(csv.reader(open(a.queries, encoding="utf-8"), delimiter="\t"))
    searcher = Searcher(a.alpha)
    name = f"bm25_ent_{alpha_tag(a.alpha)}_{a.queries.stem}"
    RUNS.mkdir(parents=True, exist_ok=True)
    trace = {}
    with open(RUNS / f"{name}.trec", "w", encoding="utf-8") as f:
        for qid, lang, text in rows:
            seeds, names = entity_names(text)
            ranked, used = searcher.run(text, lang, names)
            trace[qid] = {"entities": seeds, "indexes": used}
            for rank, (doc, score) in enumerate(ranked, 1):
                f.write(f"{qid} Q0 {doc} {rank} {score:.6f} {name}\n")
    report = {
        "generated": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "commit": subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip(),
        "alpha": a.alpha,
        "bm25": BM25,
        "queries": len(rows),
        "queries_with_entities": sum(1 for t in trace.values() if t["entities"]),
        "per_query": trace,
    }
    (ROOT / "results/retrieval" / f"{name}.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(
        f"wrote {(RUNS / f'{name}.trec').relative_to(ROOT)} ({len(rows)} queries, {report['queries_with_entities']} expanded)"
    )


if __name__ == "__main__":
    main()
