"""Link the entities a query names to the graph's entities (decision 0026, option B).

Closed world: only the gazetteer's entities can be linked, since only they can start a walk in the graph. Three
ways to match, tried in this order on the query's words, longest names first and without overlap:

1. exact: the name, in any of English, Hindi or Kannada, as written (after normalisation);
2. romanised: a Hindi or Kannada name written in Latin letters (IAST with the diacritics removed, and also
   without the final silent "a" Hindi transliteration adds: बेलूर -> belura -> belur);
3. fuzzy: for a span of at least FUZZY_MIN_CHARS letters left unmatched, the closest name of the same script and
   word count, if its similarity reaches FUZZY_THRESHOLD (RapidFuzz ratio; set on the dev queries).

A name matching several entities makes all of them seeds, the span's weight split equally (decision 0027).

Normalisation keeps letters, combining marks and digits of every script (Python's \\w drops Devanagari and Kannada
vowel signs, which would break names apart), case-folds, and turns everything else into spaces.

Two rules found in the gazetteer (recorded in docs/data_notes.md): Latin-script names shorter than four letters
are matched only when they are an entity's main label and the entity is a place (Goa, Leh, Diu; not aliases such
as "up" or "boy"); and the generic word "fort", the whole name of four entities, is never matched on its own.

Usage:
    uv run python -m src.graph_retrieval.linker "Hoysala temples at Belur"
"""

import argparse
import gzip
import json
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from functools import lru_cache

from src.corpus.wikimedia import ROOT

GAZETTEER = ROOT / "data/gazetteer/gazetteer_v1.jsonl.gz"
MAX_WORDS = 6
FUZZY_THRESHOLD = 90.0
FUZZY_MIN_CHARS = 5
SHORT_LATIN = 4
GENERIC = {"fort"}
SCRIPTS = {"deva": (0x0900, 0x097F), "knda": (0x0C80, 0x0CFF)}


def normalise(text: str) -> str:
    text = unicodedata.normalize("NFC", text).casefold()
    kept = [ch if unicodedata.category(ch)[0] in "LMN" else " " for ch in text]
    return " ".join("".join(kept).split())


def script(text: str) -> str:
    for name, (lo, hi) in SCRIPTS.items():
        if any(lo <= ord(ch) <= hi for ch in text):
            return name
    return "latn"


def ascii_fold(text: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch))


def romanisations(name: str) -> set[str]:
    """Latin spellings of a Devanagari or Kannada name, as a reader might type them."""
    from indic_transliteration import sanscript
    from indic_transliteration.sanscript import transliterate

    sc = script(name)
    if sc == "latn":
        return set()
    iast = transliterate(name, sanscript.DEVANAGARI if sc == "deva" else sanscript.KANNADA, sanscript.IAST)
    base = normalise(ascii_fold(iast))
    out = {base}
    if sc == "deva":
        # Hindi drops the final inherent vowel that transliteration writes ("belura" is said "belur").
        out.add(
            " ".join(w[:-1] if len(w) > 3 and w.endswith("a") and w[-2] not in "aeiou" else w for w in base.split())
        )
    return {o for o in out if o}


@dataclass
class Gazetteer:
    exact: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    romanised: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    by_shape: dict[tuple[str, int], list[str]] = field(default_factory=lambda: defaultdict(list))
    labels: dict[str, dict] = field(default_factory=dict)

    def add(self, key: str, qid: str, table: dict) -> None:
        if not key or key in GENERIC:
            return
        table[key].add(qid)


def allowed_latin(key: str, is_main_label: bool, etype: str) -> bool:
    return len(key.replace(" ", "")) >= SHORT_LATIN or (is_main_label and etype == "place")


@lru_cache(maxsize=1)
def load(path=GAZETTEER) -> Gazetteer:
    g = Gazetteer()
    for line in gzip.open(path, "rt", encoding="utf-8"):
        e = json.loads(line)
        qid, etype = e["qid"], e["type"]
        g.labels[qid] = {"labels": e.get("label", {}), "type": etype}
        for lang in ("en", "hi", "kn"):
            main = normalise(e.get("label", {}).get(lang, ""))
            for name in e["names"].get(lang, []):
                base = re.sub(r"\s*\([^)]*\)\s*$", "", name)  # "Pala dynasty (Kamarupa)" -> "Pala dynasty"
                key = normalise(base)
                if script(key) == "latn" and not allowed_latin(key, key == main, etype):
                    continue
                g.add(key, qid, g.exact)
                for r in romanisations(base):
                    if allowed_latin(r, False, etype):
                        g.add(r, qid, g.romanised)
    for table in (g.exact, g.romanised):
        for key in table:
            g.by_shape[(script(key), len(key.split()))].append(key)
    for shape in g.by_shape:
        g.by_shape[shape] = sorted(set(g.by_shape[shape]))
    return g


def link(text: str, gaz: Gazetteer | None = None, fuzzy_threshold: float = FUZZY_THRESHOLD) -> dict:
    """Mentions found in the text, each with its candidates, and the seed weights for PageRank."""
    from rapidfuzz import fuzz, process

    g = gaz or load()
    words = normalise(text).split()
    taken = [False] * len(words)
    mentions = []

    def take(i: int, size: int, method: str, key: str, qids: set[str], score: float) -> None:
        taken[i : i + size] = [True] * size
        mentions.append(
            {
                "text": " ".join(words[i : i + size]),
                "start": i,
                "words": size,
                "method": method,
                "matched": key,
                "score": score,
                "candidates": sorted(qids),
            }
        )

    for method, table in (("exact", g.exact), ("romanised", g.romanised)):
        for size in range(min(MAX_WORDS, len(words)), 0, -1):
            for i in range(len(words) - size + 1):
                if any(taken[i : i + size]):
                    continue
                key = " ".join(words[i : i + size])
                if key in table:
                    take(i, size, method, key, table[key], 100.0)

    for size in range(min(3, len(words)), 0, -1):
        for i in range(len(words) - size + 1):
            if any(taken[i : i + size]):
                continue
            span = " ".join(words[i : i + size])
            if len(span.replace(" ", "")) < FUZZY_MIN_CHARS:
                continue
            pool = g.by_shape.get((script(span), size), [])
            best = process.extractOne(span, pool, scorer=fuzz.ratio, score_cutoff=fuzzy_threshold)
            if best:
                key, score, _ = best
                qids = g.exact.get(key) or g.romanised.get(key) or set()
                take(i, size, "fuzzy", key, qids, round(float(score), 1))

    mentions.sort(key=lambda m: m["start"])
    seeds: dict[str, float] = {}
    for m in mentions:
        share = 1.0 / len(m["candidates"])
        for q in m["candidates"]:
            seeds[q] = seeds.get(q, 0.0) + share
    return {"text": text, "words": words, "mentions": mentions, "seeds": seeds}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("text", nargs="+")
    a = p.parse_args()
    out = link(" ".join(a.text))
    g = load()
    for m in out["mentions"]:
        names = [g.labels[q]["labels"].get("en") or q for q in m["candidates"]]
        print(f"{m['method']:9} {m['score']:5.1f}  {m['text']!r} -> {', '.join(names)}")


if __name__ == "__main__":
    main()
