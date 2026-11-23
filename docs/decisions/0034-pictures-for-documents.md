# 0034: A picture for every document: Commons photographs where they exist, a data portrait everywhere

- Status: proposed (waiting for the author)
- Date: 2026-11-23

## Context

A reader scans a list of results by picture before words: a tourist looks for the temple they saw, a student for
the painting in their textbook. Today only museum objects with an open image have one; every other result shows a
script letter ("En", "हि", "ಕ").

Counted on 23 Nov 2026 from the saved graph responses and `data/explorer/v1/images.jsonl.gz`:

| | Count |
| --- | --- |
| Documents | 14,485 |
| Documents with no picture now | 8,460 |
| Entities with a Wikidata image (P18) | 5,884 of 8,858 |
| Wikipedia articles whose entity has a P18 image | 4,899 of 7,904 |
| Documents without a picture whose entity has a P18 image | 5,427 |

So photographs can reach about two in three of the documents that lack a picture, never all of them: about 3,000
(inscriptions, manuscripts, many books, entities nobody has photographed) would still have none.

Wikimedia Commons files are all freely licensed, but most need attribution (CC BY, CC BY-SA), and the author and
licence differ per file; they come from the Commons API (`extmetadata`: Artist, LicenseShortName, LicenseUrl).

## How a reader uses it

- Scanning results: a small picture beside each result, recognisable at 64 px.
- On the document page: a larger picture with its credit under it.
- Reusing it: the credit must travel with the picture (the "Cite it" and download panels say so).

## Options considered

| Option | For | Against |
| --- | --- | --- |
| A. Wikidata P18 photograph of the document's main entity, thumbnail from Commons, credit and licence from the Commons API, shown under every use | Free licences only; the photograph is of the thing itself; one fetch per file, saved untouched like every other response | Covers about two in three; hotlinking depends on Commons; attribution must be shown everywhere the image is |
| B. Wikipedia's page image (PageImages API) | Chosen by editors as the article's lead | English Wikipedia's lead image can be a non-free local file (fair use), which this project cannot show; would need filtering to Commons files, which is option A by another road |
| C. No photographs; a **data portrait** for every document, drawn from its record: a locator dot on India's outline, its century on a timeline strip, its kind as a glyph, its script | Every document gets one, including the 3,000 no photograph covers; no licence risk; shows the facts the graph lens uses (place, period, kind), so a reader learns the lens's vocabulary while scanning | Not a photograph: a tourist still cannot recognise a building by it |
| D. A and C: the photograph where Commons has one, the data portrait otherwise, never a script letter | Every result has a picture; the portrait doubles as the photograph's caption strip (place, period, kind) | The most work: a Commons fetch plus a portrait component |
| E. Borrow a related museum object's image for a site | No new source | Shows the wrong thing as if it were the document; misleading |

## Recommendation

D. Steps, each with its tests and report:

1. `src/explorer/commons_images.py`: for every entity with P18, the Commons file's thumbnail URL, width, height,
   artist, licence short name and licence URL, fetched once and saved untouched under `data/raw/commons_v1/`;
   files without a machine-readable licence are left out and counted.
2. The server attaches the main entity's photograph to documents without one, with the credit.
3. A `Portrait` component draws the data portrait (locator dot, century strip, kind glyph, script), used wherever a
   result has no photograph and as a strip under every photograph.
4. Every displayed photograph carries "Photo: artist, licence" with links; the document page's downloads and
   citation name the photograph separately from the text.

## Decision

Waiting for the author.
