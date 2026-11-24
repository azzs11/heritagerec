"""Tests for the Commons photographs of entities (src/explorer/commons_images.py, decision 0034); no network."""

from urllib.parse import quote

from src.explorer.commons_images import MAX_TITLE_CHARS, batches, first_sentence, image_record, plain, short_artist


def test_credits_are_plain_text_without_signature_links():
    assert plain('<a href="x">Dineshkannambadi</a> (<a href="t">talk</a>)') == "Dineshkannambadi"
    assert plain("Name ( talk | contribs )") == "Name"
    assert plain("A &amp; B") == "A & B" and plain(None) == ""


def test_a_long_note_is_cut_to_the_name_and_initials_are_not_sentence_ends():
    assert first_sentence("Timothy A. Gonsalves. Feel free to use") == "Timothy A. Gonsalves"
    assert short_artist("P. Madhusudan") == "P. Madhusudan"  # short: kept as it stands
    note = "This Photo was taken by Timothy A. Gonsalves . Feel free to use my photos, but please mention me as the author."
    assert short_artist(note) == "Timothy A. Gonsalves"
    long = "x" * 200
    assert short_artist(long).endswith("…") and len(short_artist(long)) == 80


def test_batches_respect_the_title_limit_and_the_url_length():
    files = [f"f{i}.jpg" for i in range(120)]
    assert [len(b) for b in batches(files)] == [50, 50, 20]
    huge = ["Anonymous - " + "Page from Tales of a Parrot " * 6 + f"{i}.tiff" for i in range(60)]
    for b in batches(huge):
        assert sum(len(quote(f"File:{f}")) + 3 for f in b) <= MAX_TITLE_CHARS or len(b) == 1
    assert sum(len(b) for b in batches(huge)) == 60


def page(meta, **info):
    return {
        "title": "File:Belur.jpg",
        "imageinfo": [
            {
                "url": "https://u/full.jpg",
                "thumburl": "https://u/t.jpg",
                "descriptionurl": "https://c/File:Belur.jpg",
                "extmetadata": meta,
                **info,
            }
        ],
    }


def test_a_file_is_kept_only_with_a_machine_readable_licence():
    v = lambda x: {"value": x}  # noqa: E731
    rec, why = image_record(
        page(
            {"LicenseShortName": v("CC BY-SA 4.0"), "LicenseUrl": v("https://cc/by-sa/4.0"), "Artist": v("<b>Ann</b>")}
        )
    )
    assert why == "ok" and rec["credit"] == "Photo: Ann · CC BY-SA 4.0" and rec["file"] == "Belur.jpg"
    assert image_record(page({"LicenseShortName": v("Public domain")}))[1] == "ok"  # no link needed for PD
    assert image_record(page({"LicenseShortName": v("CC BY 4.0")}))[1] == "licence without a link"
    assert image_record(page({}))[1] == "no machine-readable licence"
    assert image_record({"title": "File:x", "missing": True})[1] == "file missing on Commons"
