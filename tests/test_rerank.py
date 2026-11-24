"""Tests for the reranker's passage choice and MaxP (src/retrieval/rerank.py); no model needed."""

from src.retrieval.rerank import first_passages, max_passage, passage_number, prepare, read_run


def test_first_passages_are_taken_in_reading_order_not_file_order():
    ps = [("d#10", "j"), ("d#2", "c"), ("d#0", "a"), ("d#1", "b")]
    assert [p for p, _ in first_passages(ps, k=3)] == ["d#0", "d#1", "d#2"]
    assert passage_number("wikipedia:en:7051661#12") == 12


def test_maxp_keeps_each_documents_best_passage_and_breaks_ties_by_id():
    assert max_passage({"b": [0.1, 0.9], "a": [0.9], "c": []}) == [("a", 0.9), ("b", 0.9)]


def test_prepare_writes_the_fused_top_candidates(tmp_path, monkeypatch):
    import src.retrieval.rerank as rr

    monkeypatch.setattr(rr, "ROOT", tmp_path)
    run = tmp_path / "rrf_dev_v1.trec"
    run.write_text("".join(f"q1 Q0 d{i} {i} {1 / i:.4f} rrf\n" for i in range(1, 80)))
    assert len(read_run(run, 50)["q1"]) == 50
    prepare(run, "dev")
    lines = (tmp_path / "data/rerank/dev_candidates_v1.tsv").read_text().splitlines()
    assert len(lines) == 50 and lines[0] == "q1\td1\t1"
