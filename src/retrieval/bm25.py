"""BM25 and BM25+RM3 over the shared passages, one Lucene index per language (decisions 0008, 0023).

Each language is analysed by its own rules, at index time and at query time alike: English with Porter
stemming and stop words, Hindi with Lucene's Hindi analyser, Kannada with Lucene's standard word splitting
and no stemming or stop words (Pyserini has no Kannada analyser). A query searches the index of its own
language; documents score as their best passage (MaxP).

Usage:
    uv run python -m src.retrieval.bm25 index
    uv run python -m src.retrieval.bm25 search --queries data/queries/dev_v1.tsv [--rm3]

Queries are a TSV file: query id, language (en, hi or kn), query text.

Output:
    data/indexes/bm25_v1/{en,hi,kn}/          Lucene indexes (not in git; rebuilt from the passages)
    results/retrieval/bm25_index_v1.json      passages indexed and index statistics per language
    results/retrieval/runs/<name>.trec        TREC run files, top 100 documents per query
"""

import argparse
import csv
import gzip
import json
import os
import shutil
import subprocess
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

from src.corpus.wikimedia import ROOT

PASSAGES = ROOT / "data/passages/passages_v1.jsonl.gz"
INPUT_DIR = ROOT / "data/passages/pyserini_input"
INDEX_DIR = ROOT / "data/indexes/bm25_v1"
REPORT = ROOT / "results/retrieval/bm25_index_v1.json"
RUNS = ROOT / "results/retrieval/runs"
LANGS = ("en", "hi", "kn")
# Indexer flags and the matching query-side analyser for each language. Kept together so they cannot drift.
INDEX_FLAGS = {
    "en": ["-language", "en"],
    "hi": ["-language", "hi"],
    "kn": ["-language", "en", "-stemmer", "none", "-keepStopwords"],
}
QUERY_ANALYZER = {
    "en": {"language": "en"},
    "hi": {"language": "hi"},
    "kn": {"language": "en", "stemming": False, "stopwords": False},
}
BM25 = {"k1": 0.9, "b": 0.4}  # Anserini defaults
RM3 = {"fb_terms": 10, "fb_docs": 10, "original_query_weight": 0.5}  # Anserini defaults
PASSAGE_DEPTH = 3000  # passages retrieved per query before folding into documents
DOC_DEPTH = 100  # documents kept per query (Recall@100 is a reported metric)


def java_env() -> dict:
    load_dotenv(ROOT / ".env")
    if not os.environ.get("JAVA_HOME"):
        raise SystemExit("Set JAVA_HOME in .env to a Java 21 JDK (see .env.example)")
    return dict(os.environ)


def max_passage(hits: list[tuple[str, float]], depth: int = DOC_DEPTH) -> list[tuple[str, float]]:
    """Fold passage hits ("doc#i", score) into documents scored by their best passage, best first.

    Ties keep the order Lucene returned, which is deterministic for a fixed index.
    """
    best: dict[str, float] = {}
    for pid, score in hits:
        doc = pid.rsplit("#", 1)[0]
        if doc not in best or score > best[doc]:
            best[doc] = score
    order = {doc: i for i, doc in enumerate(dict.fromkeys(pid.rsplit("#", 1)[0] for pid, _ in hits))}
    return sorted(best.items(), key=lambda kv: (-kv[1], order[kv[0]]))[:depth]


def index() -> None:
    env = java_env()
    counts = defaultdict(int)
    if INPUT_DIR.exists():
        shutil.rmtree(INPUT_DIR)
    files = {}
    for lang in LANGS:
        (INPUT_DIR / lang).mkdir(parents=True)
        files[lang] = open(INPUT_DIR / lang / "passages.jsonl", "w", encoding="utf-8")
    for line in gzip.open(PASSAGES, "rt", encoding="utf-8"):
        p = json.loads(line)
        files[p["language"]].write(json.dumps({"id": p["id"], "contents": p["contents"]}, ensure_ascii=False) + "\n")
        counts[p["language"]] += 1
    for f in files.values():
        f.close()

    for lang in LANGS:
        out = INDEX_DIR / lang
        if out.exists():
            shutil.rmtree(out)
        cmd = [sys.executable, "-m", "pyserini.index.lucene", "-collection", "JsonCollection",
               "-generator", "DefaultLuceneDocumentGenerator", "-input", str(INPUT_DIR / lang),
               "-index", str(out), "-threads", "4", "-storePositions", "-storeDocvectors", "-storeRaw",
               *INDEX_FLAGS[lang]]  # fmt: skip
        subprocess.run(cmd, check=True, env=env)
    shutil.rmtree(INPUT_DIR)  # a temporary copy; the passage file is the source

    from pyserini.index.lucene import LuceneIndexReader

    stats = {lang: LuceneIndexReader(str(INDEX_DIR / lang)).stats() for lang in LANGS}
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    manifest = json.load(open(ROOT / "data/passages/manifest_v1.json", encoding="utf-8"))
    report = {
        "built": datetime.now(UTC).date().isoformat(),
        "commit": commit,
        "passages_sha256": manifest["passages"]["sha256"],
        "index_flags": INDEX_FLAGS,
        "passages_written": dict(counts),
        "index_stats": stats,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


def searchers(rm3: bool) -> dict:
    java_env()
    from pyserini.analysis import get_lucene_analyzer
    from pyserini.search.lucene import LuceneSearcher

    out = {}
    for lang in LANGS:
        s = LuceneSearcher(str(INDEX_DIR / lang))
        s.set_analyzer(get_lucene_analyzer(**QUERY_ANALYZER[lang]))
        s.set_bm25(**BM25)
        if rm3:
            s.set_rm3(**RM3)
        out[lang] = s
    return out


def search(queries_path: Path, rm3: bool) -> None:
    by_lang = searchers(rm3)
    name = f"bm25{'_rm3' if rm3 else ''}_{queries_path.stem}"
    rows = list(csv.reader(open(queries_path, encoding="utf-8"), delimiter="\t"))
    RUNS.mkdir(parents=True, exist_ok=True)
    with open(RUNS / f"{name}.trec", "w", encoding="utf-8") as f:
        for qid, lang, text in rows:
            hits = [(h.docid, h.score) for h in by_lang[lang].search(text, k=PASSAGE_DEPTH)]
            for rank, (doc, score) in enumerate(max_passage(hits), 1):
                f.write(f"{qid} Q0 {doc} {rank} {score:.6f} {name}\n")
    print(f"wrote {(RUNS / f'{name}.trec').relative_to(ROOT)} ({len(rows)} queries)")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["index", "search"])
    parser.add_argument("--queries", type=Path)
    parser.add_argument("--rm3", action="store_true")
    args = parser.parse_args()
    if args.command == "index":
        index()
    else:
        if not args.queries:
            raise SystemExit("search needs --queries")
        search(args.queries, args.rm3)


if __name__ == "__main__":
    main()
