"""Tests for the coverage-audit list parsers (src/coverage_audit/lists.py, decision 0032)."""

import json

import pytest

from src.coverage_audit.lists import REPORT, _groups, _heading, check_mp, clean

SUMMARY = {
    "states": {
        "Karnataka": {"total": 506, "circles": {"Bangalore Circle": 133, "Dharwad Circle": 282, "Hampi Circle": 91}},
        "Odisha": {"total": 81, "circles": {"Bhubaneswar Circle": 41, "Puri Circle": 40}},
        "Goa": {"total": 21, "circles": {"Goa Circle": 21}},
        "N.C.T. Delhi": {"total": 172, "circles": {"Delhi Circle": 172}},
    },
    "total": 780,
}


def heading(text, current=None):
    current = current or {"state": None, "circle": None}
    _heading(text, SUMMARY, current)
    return current


def test_heading_sets_state_and_its_only_circle():
    assert heading("7. List of Centrally Protected Monuments / Sites under the jurisdiction of Goa (Goa Circle)") == {
        "state": "Goa",
        "circle": "Goa Circle",
    }
    # The itemised pages write "N.C.T. of Delhi"; the summary's spelling is used.
    assert heading("List of ... under the jurisdiction of N.C.T. of Delhi (Delhi Circle)")["state"] == "N.C.T. Delhi"


def test_heading_of_a_several_circle_state_takes_the_circle_that_follows():
    text = (
        "12. List of Centrally Protected Monuments / Sites under the jurisdiction of "
        "Karnataka (Bangalore Circle, Dharwad Circle and Hampi Circle) Bangalore Circle"
    )
    current = heading(text)
    assert current == {"state": "Karnataka", "circle": "Bangalore Circle"}
    assert heading("Dharwad Circle", current)["circle"] == "Dharwad Circle"
    # Odisha's heading names only its first circle, the second comes in brackets later.
    current = heading("18. List of ... under the jurisdiction of Odisha (Bhubaneswar Circle)")
    assert current["circle"] == "Bhubaneswar Circle"
    assert heading("(Puri Circle)", current)["circle"] == "Puri Circle"


def test_heading_refuses_a_circle_of_another_state():
    current = heading("under the jurisdiction of Goa (Goa Circle)")
    with pytest.raises(ValueError):
        heading("Hampi Circle", current)
    with pytest.raises(ValueError):
        heading("under the jurisdiction of Atlantis (Sea Circle)")


def test_groups_join_values_closer_than_the_tolerance():
    # A column edge drawn as three lines a few points apart is one edge.
    assert _groups([72, 77, 93, 98, 104, 175], 12) == [[72, 77], [93, 98, 104], [175]]


def test_clean_collapses_whitespace():
    assert clean("Hill Fort and\nbuildings  therein ") == "Hill Fort and buildings therein"
    assert clean(None) == ""


def test_mp_check_reports_gaps_and_repeats():
    rows = [{"list_id": f"mp:{n}", "name": "x"} for n in (1, 2, 4, 4)]
    checks = {c["what"]: c for c in check_mp(rows)}
    assert checks["rows against the last serial number"] == {
        "what": "rows against the last serial number",
        "stated": 4,
        "parsed": 4,
    }
    assert checks["serial numbers missing"]["ids"] == [3]
    assert checks["repeated serial numbers"]["parsed"] == 1


@pytest.mark.skipif(not REPORT.with_suffix(".json").exists(), reason="lists not parsed yet")
def test_parsed_lists_match_the_figures_the_lists_state():
    report = json.loads(REPORT.with_suffix(".json").read_text())
    lists = report["lists"]
    # ASI and Madhya Pradesh agree with every figure they state.
    assert lists["asi_cpm"]["rows"] == 3698 and lists["asi_cpm"]["mismatches"] == 0
    assert lists["mp_state"]["rows"] == 497 and lists["mp_state"]["mismatches"] == 0
    # Karnataka's itemised pages disagree with its own summary; every difference is one the PDF prints
    # (see docs/data_notes.md section 12), and they add up to the gap.
    checks = {c["what"]: c for c in lists["karnataka_state"]["checks"]}
    assert checks["total"]["stated"] == 844
    district_gap = sum(
        c["stated"] - c["parsed"] for what, c in checks.items() if what.startswith("district") and c["stated"]
    )
    assert checks["total"]["stated"] - checks["total"]["parsed"] == district_gap
    assert checks["serial numbers missing from the listing, Kolar"]["ids"] == [2, 3, 4, 14]
