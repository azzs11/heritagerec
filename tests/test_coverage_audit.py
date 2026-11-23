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


# ---------------------------------------------------------------- sample and sheet (src/coverage_audit/sample.py)

from src.coverage_audit.sample import allocate, core_words, keep_candidate, place_name, rank  # noqa: E402


def test_allocation_is_proportional_and_sums_to_n():
    # Karnataka's ASI circles: 133, 282 and 91 monuments, 75 draws.
    out = allocate({"Bangalore Circle": 133, "Dharwad Circle": 282, "Hampi Circle": 91}, 75)
    assert sum(out.values()) == 75
    assert out == {"Bangalore Circle": 20, "Dharwad Circle": 42, "Hampi Circle": 13}
    assert allocate({"a": 1, "b": 1}, 1) == {"a": 1, "b": 0}  # a tie goes by name


def test_search_text_helpers():
    assert core_words("Temples of Brahmanatha and Satvai.") == "Brahmanatha Satvai"
    assert place_name("Samalkot, (Bhimavaram)") == "Samalkot"
    assert place_name("Virakuppam (Birakuppam)") == "Virakuppam"


def entity(qid, p31=(), p17=(), codes=(), desc=""):
    def claims(values):
        return [{"mainsnak": {"datavalue": {"value": {"id": v} if v.startswith("Q") else v}}} for v in values]

    return {
        "id": qid,
        "claims": {"P31": claims(p31), "P17": claims(p17), "P1371": claims(codes)},
        "descriptions": {"en": {"value": desc}} if desc else {},
    }


def test_candidates_drop_people_books_settlements_and_other_countries():
    assert keep_candidate(entity("Q1", p17=["Q668"], codes=["S-KA-45"]))
    assert not keep_candidate(entity("Q2", p31=["Q5"]))  # a person
    assert not keep_candidate(entity("Q3", p31=["Q571"]))  # a book
    assert not keep_candidate(entity("Q4", desc="village in Belgaum district, Karnataka, India"))
    assert not keep_candidate(entity("Q5", p17=["Q843"]))  # Pakistan
    assert not keep_candidate({"id": "Q6", "missing": ""})


def test_rank_prefers_the_entry_state_code_and_district():
    row = {"state": "Karnataka", "district": "Bidar"}
    own = entity("Q1", codes=["S-KA-111"])
    other = entity("Q2", codes=["S-AP-265"])
    described = entity("Q3", desc="fort in Bidar district")
    assert rank(own, row) > rank(described, row) > rank(other, row)


# ---------------------------------------------------------------- coverage facts (src/coverage_audit/fill.py)

from src.coverage_audit.fill import facts, wilson  # noqa: E402


def test_wilson_interval_bounds():
    assert wilson(0, 0) == (None, None)
    lo, hi = wilson(10, 10)
    assert hi == 1.0 and 0.6 < lo < 0.8  # all ten: the interval still allows misses
    lo, hi = wilson(0, 10)
    assert lo == 0.0 and hi < 0.35


def test_facts_reads_labels_articles_and_counts():
    entity = {
        "labels": {"en": {"value": "Tomb of pir Kazi"}, "kn": {"value": "ಪೀರ್ ಕಾಜಿ ಗೋರಿ"}},
        "descriptions": {},
        "claims": {
            "P1371": [{"mainsnak": {"datavalue": {"value": "S-KA-45"}}}],
            "P31": [{"mainsnak": {}}, {"mainsnak": {}}],
            "P625": [{"mainsnak": {}}],
        },
        "sitelinks": {"knwiki": {"title": "ಪೀರ್ ಕಾಜಿ"}, "commonswiki": {"title": "Category:X"}},
    }
    row = facts(entity, "kn", {"kn": {"ಪೀರ್ ಕಾಜಿ": 2048}})
    assert row["monument_code"] == "S-KA-45"
    assert row["statements"] == 4 and row["properties"] == 3
    assert row["sitelinks"] == 2 and row["wikipedias"] == 1  # Commons is not a Wikipedia
    assert row["label_kn"] is True and row["label_hi"] is False
    assert row["article_kn"] is True and row["article_kn_bytes"] == 2048
    assert row["article_en"] is False and row["has_coordinates"] is True and row["has_image"] is False
    assert row["label_local"] is True  # Karnataka's local language is Kannada
    # A state with no local-language edition gets empty local columns, not False.
    assert facts(entity, "", {})["article_local"] == ""
