"""Tests for the graph runs' seed file (src/graph_retrieval/query_seeds.py, decisions 0026, 0027)."""

import json
import sys

from src.graph_retrieval import query_seeds
from src.graph_retrieval.ppr import parse_seeds


def test_seed_cell_is_sorted_and_readable_by_the_ppr_runner():
    cell = query_seeds.seeds_cell({"Q2": 0.5, "Q1": 1.0})
    assert cell == "Q1:1.000000;Q2:0.500000"
    assert parse_seeds(cell) == {"Q1": 1.0, "Q2": 0.5}
    assert query_seeds.seeds_cell({}) == ""


def test_seeds_file_has_one_line_per_query_and_empty_seeds_when_nothing_links(tmp_path, monkeypatch):
    monkeypatch.setattr(query_seeds, "REPORTS", tmp_path)
    monkeypatch.setattr(query_seeds, "ROOT", tmp_path)
    queries = tmp_path / "dev_v1.tsv"
    queries.write_text("q1\ten\tHoysala temples at Belur\nq2\ten\thow were these made\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["query_seeds", "--queries", str(queries)])
    query_seeds.main()
    lines = (tmp_path / "dev_v1_seeds.tsv").read_text(encoding="utf-8").splitlines()
    assert [line.split("\t")[0] for line in lines] == ["q1", "q2"]
    assert parse_seeds(lines[0].split("\t")[1])  # Hoysala and Belur link
    assert lines[1] == "q2\t"  # nothing links: the graph run returns nothing, scored zero
    report = json.loads((tmp_path / "seeds_dev_v1.json").read_text())
    assert report["queries"] == 2 and report["with_seeds"] == 1
