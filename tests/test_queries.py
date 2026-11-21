"""Tests for the query grid, prompts and generator-trial sheet in src/queries/ (no network, no models)."""

import csv
import json
import random
from collections import Counter

from src.corpus.link_objects import ALL_TYPES, Gazetteer
from src.queries import generator_trial, grid
from src.queries.prompts import backstory_prompt, query_prompt


def trial_cells():
    return grid.sample_cells(random.Random(grid.TRIAL_SEED), grid.trial_slots())


def test_trial_cells_are_reproducible_and_balanced():
    cells = trial_cells()
    assert cells == trial_cells()
    assert len(cells) == 30
    assert Counter(c["language"] for c in cells) == {"en": 10, "hi": 10, "kn": 10}
    assert set(Counter(c["query_type"] for c in cells).values()) <= {7, 8}
    # every area appears three times in 30 cells, every region four or five times
    assert set(Counter(c["area"] for c in cells).values()) == {3}
    assert set(Counter(c["region"] for c in cells).values()) <= {4, 5}


def test_real_style_cells_have_a_fitting_role():
    for c in trial_cells():
        if c["style"] != "plain":
            assert c["role"] in grid.STYLE_ROLES[c["style"]]
        assert c["purpose"] in grid.ROLES[c["role"]]


def test_no_entity_name_enters_through_the_grid():
    words = list(grid.ROLES) + [p for v in grid.ROLES.values() for p in v] + grid.AREAS + grid.REGIONS + grid.PERIODS
    found = Gazetteer().find(" . ".join(words), ALL_TYPES, derived=False)
    assert {c["qid"] for _, cands in found for c in cands} <= {"Q668"}  # India, the corpus scope


def test_prompts_carry_the_cell():
    cell = {**trial_cells()[0], "role": "undergraduate student", "region": "pan-India", "language": "kn"}
    p = backstory_prompt(cell)
    assert "an undergraduate student" in p and "across India" in p
    q = query_prompt(cell, "A student wants X.")
    assert q.startswith("A student wants X.") and "Kannada script" in q


def test_sheet_hides_the_model_and_summary_recovers_it(tmp_path, monkeypatch):
    monkeypatch.setattr(generator_trial, "OUTPUTS", tmp_path / "outputs.jsonl")
    monkeypatch.setattr(generator_trial, "SHEET", tmp_path / "sheet.csv")
    monkeypatch.setattr(generator_trial, "SUMMARY", tmp_path / "summary")
    cells = trial_cells()[:4]
    with open(generator_trial.OUTPUTS, "w", encoding="utf-8") as f:
        for model in ("org/a", "org/b"):
            for i, c in enumerate(cells):
                row = {
                    "cell_id": f"c{i}",
                    "cell": c,
                    "model": model,
                    "revision": "abc123",
                    "backstory": "b",
                    "query": "q",
                }
                f.write(json.dumps(row) + "\n")
    generator_trial.sheet()
    rows = list(csv.DictReader(open(generator_trial.SHEET, encoding="utf-8")))
    assert len(rows) == 8 and "model" not in rows[0]
    assert "org/a" not in generator_trial.SHEET.read_text()
    # Rate model a's items 3 and b's items 1, through the key the summary rebuilds.
    key = dict(generator_trial.shuffled(generator_trial.load_outputs()))
    for row in rows:
        row.update(fluency="3" if key[row["item"]]["model"] == "org/a" else "1", fits_backstory="yes", right_type="no")
    with open(generator_trial.SHEET, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    generator_trial.summary()
    report = json.loads((tmp_path / "summary.json").read_text())
    assert report["ratings"]["org/a"]["all"]["mean_fluency"] == 3.0
    assert report["ratings"]["org/b"]["all"]["mean_fluency"] == 1.0
    assert report["ratings"]["org/a"]["all"]["right_type"] == 0.0
