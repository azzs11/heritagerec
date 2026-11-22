"""Tests for the query entity linker (src/graph_retrieval/linker.py) on the real gazetteer."""

import pytest

from src.graph_retrieval.linker import link, load, normalise, romanisations


def names(result):
    g = load()
    return [
        (m["text"], m["method"], sorted(g.labels[c]["labels"].get("en", c) for c in m["candidates"]))
        for m in result["mentions"]
    ]


def test_normalising_keeps_indian_scripts_whole():
    assert normalise("जामा मस्जिद, दिल्ली!") == "जामा मस्जिद दिल्ली"
    assert normalise("ಬೇಲೂರು") == "ಬೇಲೂರು"
    assert normalise("Jama Masjid (Delhi)") == "jama masjid delhi"


def test_hindi_names_are_also_written_in_latin_letters():
    assert "belur" in romanisations("बेलूर")
    assert romanisations("Belur") == set()


@pytest.mark.parametrize(
    "query, expected",
    [
        ("Hoysala temples Belur", [("hoysala", "exact", ["Hoysala Empire"]), ("belur", "exact", ["Belur"])]),
        ("मुगल किला आगरा", [("मुगल", "exact", ["Mughal Empire"]), ("आगरा", "exact", ["Agra"])]),
        ("ಹಂಪೆ ದೇವಾಲಯ", [("ಹಂಪೆ", "exact", ["Hampi"])]),
        ("agra fort", [("agra fort", "exact", ["Agra Fort"])]),
        ("belur halebid", [("belur", "exact", ["Belur"]), ("halebid", "fuzzy", ["Halebidu"])]),
    ],
)
def test_links_in_three_scripts_and_with_a_typo(query, expected):
    assert names(link(query)) == expected


def test_generic_and_short_words_do_not_link():
    assert link("fort")["mentions"] == []
    assert link("up and down the ghats")["mentions"] == []


def test_an_ambiguous_name_splits_its_weight():
    r = link("taj mahal")
    (m,) = r["mentions"]
    assert len(m["candidates"]) == 2
    assert sum(r["seeds"].values()) == pytest.approx(1.0)
    assert all(w == pytest.approx(0.5) for w in r["seeds"].values())


def test_a_stricter_threshold_turns_the_fuzzy_match_off():
    assert [m["method"] for m in link("halebid", fuzzy_threshold=99)["mentions"]] == []
