"""Keyword search and its explanation, stage by stage, with a check that the explanation adds up (decision 0025).

BM25 in Lucene scores a passage as the sum of one weight per query term (a repeated term counts once per
occurrence); RM3 scores it as the sum of each expansion term's weight times that term's BM25 weight. Both were
checked to match Lucene's scores exactly on the corpus v1 indexes (22 Nov 2026). The explanation recomputes the
score from these parts and reports whether it matches; a mismatch is shown, never hidden.
"""

import re
import unicodedata
from collections import Counter

from server.components import Corpus, Keyword
from src.retrieval.bm25 import DOC_DEPTH, PASSAGE_DEPTH, max_passage
from src.retrieval.passages import passages

SNIPPET_WORDS = 60
CHECK_TOLERANCE = 1e-3  # relative; Lucene scores in float32
SCRIPTS = {"hi": (0x0900, 0x097F), "kn": (0x0C80, 0x0CFF)}


def detect_language(text: str) -> dict:
    """The script most letters are in: Devanagari is read as Hindi, Kannada as Kannada, anything else as English.

    Sanskrit or Marathi in Devanagari cannot be told apart from Hindi by script, so the reader can override this.
    """
    counts = Counter()
    for ch in text:
        if not unicodedata.category(ch).startswith("L") and not unicodedata.category(ch).startswith("M"):
            continue
        code = ord(ch)
        lang = next((lang for lang, (lo, hi) in SCRIPTS.items() if lo <= code <= hi), "en")
        counts[lang] += 1
    lang = max(("en", "hi", "kn"), key=lambda x: (counts[x], x == "en")) if counts else "en"
    return {
        "language": lang,
        "letters_by_script": {"latin_or_other": counts["en"], "hi": counts["hi"], "kn": counts["kn"]},
    }


def analyse(kw: Keyword, text: str, lang: str) -> list[str]:
    with kw.lock:
        return list(kw.analyzers[lang].analyze(text))


def query_terms(kw: Keyword, text: str, lang: str, rm3: bool) -> dict[str, float]:
    """Each term's multiplier in the score: occurrences for BM25, expansion weight for RM3."""
    if not rm3:
        return dict(Counter(analyse(kw, text, lang)))
    with kw.lock:
        feedback = kw.expanders[lang].get_feedback_terms(text) or {}  # None when nothing is retrieved
    return {t: float(w) for t, w in feedback.items()}


def passage_hits(kw: Keyword, text: str, lang: str, rm3: bool) -> list[tuple[str, float]]:
    searcher = kw.expanders[lang] if rm3 else kw.searchers[lang]
    with kw.lock:
        return [(h.docid, float(h.score)) for h in searcher.search(text, k=PASSAGE_DEPTH)]


def best_passages(hits: list[tuple[str, float]]) -> dict[str, tuple[str, float]]:
    best: dict[str, tuple[str, float]] = {}
    for pid, score in hits:
        doc = pid.rsplit("#", 1)[0]
        if doc not in best or score > best[doc][1]:
            best[doc] = (pid, score)
    return best


def passage_text(corpus: Corpus | None, pid: str) -> str | None:
    if corpus is None:
        return None
    doc, i = pid.rsplit("#", 1)
    record = corpus.records.get(doc)
    if record is None:
        return None
    parts = passages(record)
    idx = int(i)
    return parts[idx]["contents"] if idx < len(parts) else None


def marked_words(kw: Keyword, text: str, lang: str, terms: set[str], limit: int = SNIPPET_WORDS) -> list[dict]:
    """The passage body word by word, each marked when its analysed form is one of the query's terms.

    The window starts a little before the first match, so a reader sees why the passage was chosen.
    """
    body = text.split("\n", 1)[1] if "\n" in text else text
    words = body.split()
    with kw.lock:
        forms = [list(kw.analyzers[lang].analyze(w)) for w in words]
    hits = [i for i, f in enumerate(forms) if terms.intersection(f)]
    start = max(0, (hits[0] if hits else 0) - 8)
    window = range(start, min(len(words), start + limit))
    return [{"word": words[i], "match": bool(terms.intersection(forms[i]))} for i in window]


def search(kw: Keyword, corpus: Corpus | None, text: str, lang: str, rm3: bool, k: int) -> dict:
    hits = passage_hits(kw, text, lang, rm3)
    docs = max_passage(hits, depth=min(k, DOC_DEPTH))
    best = best_passages(hits)
    terms = set(query_terms(kw, text, lang, rm3))
    results = []
    for rank, (doc, score) in enumerate(docs, 1):
        pid = best[doc][0]
        record = corpus.records.get(doc) if corpus else None
        content = passage_text(corpus, pid)
        results.append(
            {
                "rank": rank,
                "doc_id": doc,
                "score": score,
                "best_passage": pid,
                "title": record["title"] if record else None,
                "source": record["source"] if record else None,
                "doc_type": record["doc_type"] if record else None,
                "language": record["language"] if record else lang,
                "snippet": marked_words(kw, content, lang, terms) if content else None,
            }
        )
    return {
        "system": "bm25_rm3" if rm3 else "bm25",
        "language": lang,
        "settings": {"bm25": kw.bm25, **({"rm3": kw.rm3} if rm3 else {})},
        "passages_retrieved": len(hits),
        "passage_depth": PASSAGE_DEPTH,
        "results": results,
    }


def explain(kw: Keyword, corpus: Corpus | None, text: str, lang: str, doc_id: str, rm3: bool) -> dict:
    """Why a document ranks where it does: query terms, its passages among the hits, and the winner's score by term."""
    tokens = analyse(kw, text, lang)
    terms = query_terms(kw, text, lang, rm3)
    hits = passage_hits(kw, text, lang, rm3)
    ranking = max_passage(hits, depth=len(hits))
    rank = next((i for i, (d, _) in enumerate(ranking, 1) if d == doc_id), None)
    own = [(pid, s) for pid, s in hits if pid.rsplit("#", 1)[0] == doc_id]
    record = corpus.records.get(doc_id) if corpus else None
    total = len(passages(record)) if record else None
    out = {
        "system": "bm25_rm3" if rm3 else "bm25",
        "language": lang,
        "doc_id": doc_id,
        "query_tokens": tokens,
        "terms": [{"term": t, "multiplier": m} for t, m in terms.items()],
        "rank": rank,
        "passages_in_document": total,
        "passages_retrieved": [{"passage": pid, "score": s} for pid, s in own],
        "passage_depth": PASSAGE_DEPTH,
    }
    if not own:
        out["winner"] = None
        out["note"] = f"No passage of this document is among the first {PASSAGE_DEPTH} passages for this query."
        return out
    winner, score = own[0]
    with kw.lock:
        weights = {
            t: float(kw.readers[lang].compute_bm25_term_weight(winner, t, analyzer=None, **kw.bm25)) for t in terms
        }
    parts = [
        {"term": t, "multiplier": m, "bm25_weight": weights[t], "contribution": m * weights[t]}
        for t, m in sorted(terms.items(), key=lambda tm: -tm[1] * weights[tm[0]])
    ]
    recomputed = sum(p["contribution"] for p in parts)
    out["winner"] = {
        "passage": winner,
        "score": score,
        "terms": parts,
        "check": {
            "recomputed": recomputed,
            "lucene": score,
            "matches": abs(recomputed - score) <= CHECK_TOLERANCE * max(1.0, abs(score)),
        },
    }
    content = passage_text(corpus, winner)
    if content:
        out["winner"]["text"] = marked_words(kw, content, lang, set(terms), limit=150)
    return out


def safe_query(text: str) -> str:
    """Lucene's query parser is not used (queries go in as bag-of-words), but control characters are dropped."""
    return re.sub(r"[\x00-\x1f\x7f]", " ", text).strip()
