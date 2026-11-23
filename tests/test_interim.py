"""Tests for the interim checkpoint report (src/benchmark/interim.py)."""

import json

from src.benchmark import interim


def test_missing_parts_say_what_they_wait_for_and_present_parts_come_from_their_files(tmp_path, monkeypatch):
    sources = {k: tmp_path / f"{k}.json" for k in interim.SOURCES}
    monkeypatch.setattr(interim, "SOURCES", sources)
    monkeypatch.setattr(interim, "ROOT", tmp_path)
    (tmp_path / "graph.json").write_text(
        json.dumps({"stats": {"nodes": 24006, "edges": 42990, "nodes_by_kind": {"document": 14485}}})
    )
    (tmp_path / "baselines.json").write_text(
        json.dumps(
            {
                "settings": {"primary": "nDCG@10"},
                "queries_scored": 39,
                "queries_without_relevant_judgement": ["q017"],
                "systems": {
                    "bm25_dev_v1": {
                        "measures": {"nDCG@10": {"mean": 0.41234, "ci95": [0.3, 0.5]}},
                        "unjudged_in_top10": 0,
                    }
                },
            }
        )
    )
    report = interim.gather()
    text = interim.markdown(report)
    assert text.count("INTERIM") == 1 and "dev split only" in text
    assert "24,006 nodes and 42,990 edges" in text
    assert "| bm25_dev_v1 | 0.412 [0.300, 0.500] | 0 |" in text
    assert "39 queries scored (1 without a relevant document)" in text
    assert "Not available yet: waits for `snapshot.json`" in text
    assert report["available"] == {k: k in ("graph", "baselines") for k in sources}
