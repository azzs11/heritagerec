# 0032: Coverage audit: which lists, how the sample is drawn, how entries are matched to Wikidata

- Status: accepted (author, 2026-11-23: "yes fine"). Madhya Pradesh is the Hindi-belt state list. A
  local-language article column is added. Tamil Nadu and Haryana state lists are optional, depending on what the
  author can save from a browser in India.
- Date: 2026-11-23
- Follows: 0031 (step 1, the coverage audit)

## Context

Decision 0031 sets up a coverage audit: about 300 entries drawn from official lists built outside Wikidata and
Wikipedia, each matched to Wikidata by hand. About 150 come from Karnataka, about 100 from one Hindi-belt state
(its own list plus ASI), about 50 from the rest of India (ASI), and the UNESCO intangible list for India is taken
in full.

This record chooses the lists, the Hindi-belt state, the way the lists are turned into rows, and the matching
procedure. The sources were checked on 23 November 2026:

| List | Publisher | Version found | Entries | Format | Notes |
| --- | --- | --- | --- | --- | --- |
| Centrally protected monuments, state- and circle-wise | Archaeological Survey of India, `asi.nic.in/pdf/CPM_List.pdf` | PDF created 8 Apr 2025 | 3,698 (stated total); Karnataka 506, Madhya Pradesh 291, Uttar Pradesh 743, Rajasthan 163, Bihar 70 | 142 pages, text layer; rows of serial number, monument, locality, district, by state and circle | Row text wraps over several lines; needs a careful parser |
| Protected monuments and sites of Karnataka | Dept. of Archaeology, Museums and Heritage, Karnataka, `archaeology.karnataka.gov.in/storage/pdf-files/monument list final english.pdf` | PDF created 17 Oct 2020 | 844 state-protected, plus 609 counted as ASI (stated totals) | 176 pages, text layer; rows by division, district, taluk and locality, with the state and ASI monuments in side-by-side columns and G.O. numbers | The 609 ASI figure differs from ASI's own 506; probably sites counted separately, to be checked. The side-by-side columns make parsing harder |
| Protected monuments of Madhya Pradesh | Directorate of Archaeology, Archives and Museums, MP | Live page returned 404 on 23 Nov 2026; Internet Archive copy of 20 Oct 2021 | 497 rows (counted) | Clean HTML table: name, district, place and tehsil, zone, period (century), category | Period and category columns come free; the archived date is the version |
| Protected monuments of Uttar Pradesh | UP State Archaeology Department | No official list found online | n/a | n/a | Only Wikipedia and exam-notes copies found |
| Protected monuments of Rajasthan | Schedules of the Rajasthan Monuments Act, 1961 (indiacode.nic.in) | 1961 | not counted | Act text | Dates from 1961; later additions not included. Wikipedia cites a revised list of 342 from Rajasthan Tourism, with no official source found |
| Protected monuments of Bihar | Only through ASI's archived state-protected pages | 2013 archive | 30 (Wikipedia's count) | n/a | Too small to be the state list |
| Protected sites and monuments of Haryana | Dept. of Archaeology and Museums, Haryana, `archaeologyharyana.nic.in/sites-and-monuments` | not read | not read | not read | Connection refused from outside India on 23 Nov 2026 |
| Protected monuments of Tamil Nadu | Tamil Nadu State Department of Archaeology, `tnarch.gov.in/monuments-subnames` | not read | 109 per Wikipedia; a 2024–25 policy note says 105 | not read | Timed out from outside India on 23 Nov 2026 |
| Intangible cultural heritage of India | UNESCO | to be fetched | to be counted | Web pages | Small; taken in full |

The raw files are kept in the scratchpad with their SHA-256 hashes (ASI `47f3253a…`, Karnataka `dfcf123a…`,
MP archive `a8b7ace1…`). They move to `data/raw/coverage_audit_v1/` once this record is accepted.

## Options considered

The Hindi-belt state:

| Option | For | Against |
| --- | --- | --- |
| A. Madhya Pradesh: the state's own table (497) plus the ASI list for MP (291) | Official, clean table with period and category; Hindi-speaking; MP is thin in Wikipedia outside Khajuraho, Sanchi and Mandu | The current page is gone; the version is a 2021 archive copy |
| B. Uttar Pradesh: ASI list only (743) | The largest ASI state; Hindi-speaking | No state list found, so state-protected coverage is not measured for the Hindi belt |
| C. Rajasthan: the 1961 Act schedules plus the ASI list (163) | Legal source | 1961 schedule; later notifications missing |
| D. MP state list, with the ASI draw spread over UP, MP, Bihar and Rajasthan | One clean state list; the ASI part covers the wider Hindi belt | Slightly more strata |

How the lists become rows:

| Option | For | Against |
| --- | --- | --- |
| A. A parser per list turns every entry into a row (name, locality, district, state, list, list ID), checked against each list's stated totals; the draw is made from those rows | Reproducible; the per-state comparison (0031) needs the full ASI list anyway; totals catch parser errors | Three parsers, and the Karnataka layout is awkward |
| B. Draw page and line numbers, then transcribe only the drawn entries by hand | No parser | Not reproducible by others; uneven entries per page bias the draw |
| C. Use the Wikipedia list pages | Already tabular | Ruled out by 0031: written by the same community as Wikidata |

Matching an entry to Wikidata:

| Option | For | Against |
| --- | --- | --- |
| A. Fully automatic (name search plus place filter) | Fast | False "no item" results inflate the gap; Indian monument names vary a lot |
| B. Script proposes up to 5 candidates per entry (Wikidata search in en and hi or kn, plus items with an ASI ID in the same district, plus items within the locality by P131); the author picks one or marks "no item" with the search trail filled in; 10% re-checked | Search is reproducible and logged; a person makes the call; follows 0031 | About 300 decisions for the author |
| C. The author searches by hand from scratch | No tooling | Slow, and the trail is not reproducible |

## Recommendation

- **Hindi belt: D.** Use the MP state list (2021 archive, dated as such) for the state-protected part. Spread the
  Hindi-belt ASI draw over UP, MP, Bihar and Rajasthan in proportion to their ASI counts.
- **Rows: A.** Each parser must reproduce the stated totals (ASI 3,698 and each state's count; Karnataka 844;
  MP 497). If it does not, the gap is written in the report, never forced.
- **Matching: B.**
- **Draw, seeded, about 300 entries in all:**
  - Karnataka: 75 from the state list and 75 from ASI, spread across the Bangalore, Dharwad and Hampi circles
    in proportion to their counts.
  - Hindi belt: 50 from the MP state list and 50 from ASI (UP, MP, Bihar, Rajasthan).
  - Rest of India: 50 from ASI, in proportion to state counts.
  - UNESCO intangible heritage for India: every element.
- **Full-frame comparison, besides the sample.** Wikidata items with an ASI ID (P1371), counted per state with
  a SPARQL count, against the ASI per-state totals. This gives state-level coverage for all 3,698 entries, not
  just the sample.
- **The sheet for the author.** One row per entry: list, ID, name, locality, district, up to 5 candidates (QID,
  label, description, link). The author fills in two columns:
  - `match`: a QID, or `none`;
  - `searched`: what else was tried.

  A small script then fills in each matched item's ASI ID, en/hi/kn articles, article length, statement count,
  sitelinks and corpus degree.

## Decision

As recommended, with these additions from the author's review:

- **Local-language article.** Each entry also records whether an article exists in its state's main
  language (ta for Tamil Nadu, te for Andhra Pradesh and Telangana, ml for Kerala, mr for Maharashtra, bn for
  West Bengal, and so on; the state-to-language table goes in the audit code). This comes from the same
  sitelinks, so the audit measures local-language coverage across India, not only Hindi and Kannada.
- **Tamil Nadu and Haryana state lists are optional.** If the author can save the official pages from a
  browser in India, each becomes a further stratum of about 25 entries. Tamil Nadu falls under the rest of
  India, Haryana under the Hindi belt. Otherwise they are left out and the record says so.
- **Tamil is not a query or corpus language in this study.** RQ3, the query quotas and the judge validation
  stay en/hi/kn. The audit's Tamil and other local-language rates go into the Limitations paragraph.

## Notes

- Licence. Government lists of names and places are facts. Republishing the gap list (entry, list ID, source URL,
  search trail) is planned, but not the PDFs themselves. The raw PDFs stay on Zenodo only if their terms allow;
  otherwise only their URLs and hashes are published.

## Addendum, 23 Nov 2026: what "covered" means

- Status: accepted (author, 2026-11-23: "yep").

Found while building the fill step (`src/coverage_audit/fill.py`): Wikidata holds monument codes (P1371) for 7,745
items, and per state the ASI codes match the ASI list almost one for one. The items seem to have been bulk-created
from the Wiki Loves Monuments lists, and many carry little more than the code. The per-state comparison is
generated into `results/coverage_audit/coverage_v1.md`.

So "has a Wikidata item" is close to 100% for listed monuments and says little about coverage. The audit reports
existence and also how rich each matched item is: an English description; labels in Hindi, Kannada and the local
language; coordinates; an image; statement and sitelink counts; Wikipedia articles (en, hi, kn, local) and their
lengths; whether the item is in corpus v1, and its degree in the core graph. The coverage tiers of 0031 (sitelinks
and statements) already rest on richness and are unchanged. The author's matching is the same.

