"""Tests for passage splitting and best-passage scoring in src/retrieval/ (no Java, no index)."""

from src.retrieval.bm25 import INDEX_FLAGS, LANGS, QUERY_ANALYZER, max_passage
from src.retrieval.passages import passages, windows


def test_windows_cover_every_word_with_the_stride():
    words = [str(i) for i in range(320)]
    w = windows(words, size=150, stride=75)
    assert [x[0] for x in w] == ["0", "75", "150", "225"]
    assert w[-1][-1] == "319" and len(w[-1]) == 95
    assert windows(words[:150], 150, 75) == [words[:150]]
    assert windows(words[:151], 150, 75)[1] == words[75:151]
    assert windows([], 150, 75) == [[]]


def test_passages_carry_title_doc_and_language():
    record = {"id": "wikipedia:kn:1", "title": "ಹಂಪೆ", "language": "kn", "text": " ".join(["ಪದ"] * 200)}
    ps = passages(record)
    assert [p["id"] for p in ps] == ["wikipedia:kn:1#0", "wikipedia:kn:1#1"]
    assert all(p["contents"].startswith("ಹಂಪೆ\n") and p["doc_id"] == "wikipedia:kn:1" for p in ps)
    assert passages({**record, "text": ""})[0]["contents"] == "ಹಂಪೆ"


def test_max_passage_scores_a_document_by_its_best_passage():
    hits = [("a#3", 9.0), ("b#0", 8.0), ("a#1", 7.0), ("c#2", 8.0), ("met:5#0", 1.0)]
    assert max_passage(hits) == [("a", 9.0), ("b", 8.0), ("c", 8.0), ("met:5", 1.0)]
    assert max_passage(hits, depth=2) == [("a", 9.0), ("b", 8.0)]


def test_every_language_has_index_and_query_rules():
    assert set(INDEX_FLAGS) == set(QUERY_ANALYZER) == set(LANGS)
    # Kannada is indexed and queried the same way: no stemming, no stop words.
    assert "-keepStopwords" in INDEX_FLAGS["kn"] and QUERY_ANALYZER["kn"]["stopwords"] is False
