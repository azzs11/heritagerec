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


# ---------------------------------------------------------------- benchmark cells, curation, split, tiers

from src.queries import curation  # noqa: E402
from src.queries.tiers import Tiers, percentile  # noqa: E402


def test_benchmark_cells_meet_the_quotas_and_are_reproducible():
    cells = grid.benchmark_cells()
    assert cells == grid.benchmark_cells()
    assert len(cells) == 600
    primary = [c for c in cells if c["rank"] == 0]
    quotas = Counter((c["language"], c["query_type"]) for c in primary)
    assert all(quotas[("en", t)] == 40 and quotas[("hi", t)] == 5 and quotas[("kn", t)] == 5 for t in grid.QUERY_TYPES)
    assert sum(c["style"] != "plain" for c in primary) == 40
    assert set(Counter(c["area"] for c in primary).values()) == {20}
    for c in cells:
        if c["style"] != "plain":
            assert c["role"] in grid.STYLE_ROLES[c["style"]]
    # A reserve keeps its slot's type, language and style but is a different information need.
    by_slot = {}
    for c in cells:
        by_slot.setdefault(c["slot"], []).append(c)
    for members in by_slot.values():
        assert len({(c["query_type"], c["language"], c["style"]) for c in members}) == 1
    assert sum(len({(c["role"], c["area"], c["region"], c["period"]) for c in m}) == 3 for m in by_slot.values()) > 190


def row(cell_id, rank, action="", target="", reason="", edited=""):
    slot = cell_id.split("-")[0]
    return {"cell_id": cell_id, "slot": slot, "rank": str(rank), "action": action, "edited_query": edited,
            "reason": reason, "target_entity": target, "notes": ""}  # fmt: skip


def test_curation_rows_are_checked():
    assert curation.check_rows([row("q001-0", 0, "keep", "Q42")]) == []
    assert curation.check_rows([row("q001-0", 0, "keep", "none")]) == []
    assert curation.check_rows([row("q001-0", 0, "keep", "")])  # target needed
    assert curation.check_rows([row("q001-0", 0, "edit", "Q42", reason="typo")])  # edited text needed
    assert curation.check_rows([row("q001-0", 0, "reject", "")])  # reason needed
    assert curation.check_rows([row("q001-0", 0, "maybe", "Q42")])


def test_reserves_request_the_next_rank_and_stop_after_two(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(curation, "SHEET", tmp_path / "curation.csv")
    monkeypatch.setattr(curation, "REQUESTS", tmp_path / "requests.json")
    monkeypatch.setattr(curation, "ROOT", tmp_path)
    rows = [
        {**row("q001-0", 0, "reject", reason="off topic"), **{k: "" for k in ("language",)}},
        row("q002-0", 0, "reject", reason="garbled"),
        row("q002-1", 1, "keep", "Q1"),
        row("q003-0", 0, "reject", reason="x"),
        row("q003-1", 1, "reject", reason="x"),
        row("q003-2", 2, "reject", reason="x"),
    ]
    curation.write_sheet([{k: r.get(k, "") for k in curation.COLUMNS} for r in rows])
    curation.reserves()
    assert json.loads((tmp_path / "requests.json").read_text()) == {"q001": 1}
    assert "q003" in capsys.readouterr().out


def test_split_takes_the_dev_quota_per_cell_and_mirrors_the_tiers():
    queries = []
    tiers = ["sparse", "middle", "rich", ""]
    for lang, n in grid.PER_TYPE.items():
        for t in grid.QUERY_TYPES:
            for i in range(n):
                queries.append(
                    {"qid": f"{lang}{t}{i}", "language": lang, "query_type": t, "coverage_tier": tiers[i % 4]}
                )
    out = curation.split(queries)
    assert out == curation.split(queries)
    dev = [q for q in queries if out[q["qid"]] == "dev"]
    assert len(dev) == 40
    assert Counter(q["language"] for q in dev) == {"en": 32, "hi": 4, "kn": 4}
    assert set(Counter(q["query_type"] for q in dev).values()) == {10}
    # 40 English queries per type, a quarter sparse: the 8 dev picks take 2 sparse each.
    assert sum(q["coverage_tier"] == "sparse" and q["language"] == "en" for q in dev) == 8


def test_tiers_rank_by_statements_and_sitelinks():
    assert percentile([1, 2, 3, 4], 2) == 0.375  # mid-rank
    tiers = Tiers({f"Q{i}": i for i in range(30)}, {f"Q{i}": i for i in range(30)})
    assert tiers.tier(0, 0) == "sparse"
    assert tiers.tier(15, 15) == "middle"
    assert tiers.tier(29, 29) == "rich"


def test_dev_tsv_has_no_header_and_no_stray_tabs(tmp_path):
    path = tmp_path / "dev.tsv"
    curation.write_tsv(path, [{"qid": "q001", "language": "kn", "text": "ಬೇಲೂರು\tದೇವಾಲಯ\nಶಿಲ್ಪ"}])
    assert path.read_text(encoding="utf-8") == "q001\tkn\tಬೇಲೂರು ದೇವಾಲಯ ಶಿಲ್ಪ\n"
