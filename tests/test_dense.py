"""Tests for the dense baselines in src/retrieval/dense.py that need no GPU, model download or vectors."""

import json
import re

import pytest

from src.retrieval.dense import BGE_WEIGHTS, MODELS, check_passages, chunks, combine, truncated


def test_the_four_models_of_decision_0024_at_pinned_revisions():
    assert set(MODELS) == {"minilm_l6", "minilm_l12_multi", "e5_large", "bge_m3"}
    assert all(re.fullmatch(r"[0-9a-f]{40}", m.revision) for m in MODELS.values())
    assert MODELS["minilm_l6"].max_length == MODELS["minilm_l12_multi"].max_length == 128
    assert MODELS["e5_large"].max_length == MODELS["bge_m3"].max_length == 512


def test_only_e5_gets_prefixes():
    assert (MODELS["e5_large"].query_prefix, MODELS["e5_large"].passage_prefix) == ("query: ", "passage: ")
    others = [m for name, m in MODELS.items() if name != "e5_large"]
    assert all(m.query_prefix == m.passage_prefix == "" for m in others)


def test_chunks_cover_every_passage_once():
    assert chunks(25, 10) == [(0, 10), (10, 20), (20, 25)]
    assert chunks(20, 10) == [(0, 10), (10, 20)]
    assert chunks(0, 10) == []


def test_truncation_counts_only_passages_over_the_limit():
    counts = truncated([5, 129, 128, 300], ["en", "hi", "kn", "kn"], 128)
    assert counts == {"en": 0, "hi": 1, "kn": 1}
    with pytest.raises(ValueError):
        truncated([1, 2], ["en"], 128)


def test_bge_weights_are_the_model_card_weights():
    assert BGE_WEIGHTS == {"dense": 0.4, "sparse": 0.2, "colbert": 0.4}
    assert combine(1.0, 0.0, 0.0) == pytest.approx(0.4)
    assert combine(1.0, 1.0, 1.0) == pytest.approx(1.0)


def test_a_passage_file_other_than_the_manifest_is_refused(tmp_path):
    passages = tmp_path / "passages.jsonl.gz"
    passages.write_bytes(b"not the real file")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"passages": {"sha256": "0" * 64}}))
    with pytest.raises(SystemExit):
        check_passages(passages, manifest)
