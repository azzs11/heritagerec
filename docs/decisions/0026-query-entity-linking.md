# 0026: Linking the entities a query names

- Status: accepted (author, 2026-11-22: "B or whatever you think is the best option")
- Date: 2026-11-22

## Context

Every graph system starts from the entities a query names: personalised PageRank uses them as seeds, meta-paths
and SimRank start from them, and the entity-expanded BM25 control adds their names (specification Section 4). The
specification also asks for the share of queries with a linkable entity. Nothing links queries yet, so the graph
lens is empty.

Two facts shape the choice:

- **Only entities in our graph matter.** A seed outside the graph cannot start a walk. The gazetteer
  (`data/gazetteer/gazetteer_v1.jsonl.gz`) already holds the graph's 8,451 entities with their Wikidata labels and
  aliases: English names for 8,419, Hindi for 4,511, Kannada for 2,246 (counted 22 Nov 2026).
- **Queries come in three languages**, typed in their own scripts, and some Hindi and Kannada queries may write
  names in Latin letters.

Licences and state, checked 22 Nov 2026:

| Tool | Licence | Languages | State |
| --- | --- | --- | --- |
| ReFinED (Amazon) | Apache-2.0 | English | Maintained; links to all of Wikidata |
| mGENRE (Meta) | CC BY-NC 4.0 | Many | NonCommercial: excluded by the licence rule |
| BELA (Meta) | MIT | 98 | Repository archived; training needs LDC data |
| OpenTapioca | Apache-2.0 | Mainly English | Needs a Solr index of Wikidata |
| RapidFuzz | MIT | Any | Fuzzy string matching library |
| indic-transliteration | MIT | Indian scripts to Latin | Transliteration library |

## Options considered

| Option | For | Against |
| --- | --- | --- |
| A. Gazetteer, exact names: the longest name in the query that matches an entity's label or alias in any of the three languages, after the same normalisation as object linking | Closed world, so every link can seed the graph; no model; fully reproducible; the matcher already exists for English (`src/corpus/link_objects.py`) | Misses misspellings and names written in another script |
| B. A, plus names written in Latin letters (each Hindi and Kannada name also indexed in its standard romanisation) and a fuzzy fallback for near misses (RapidFuzz, one similarity threshold set on dev) | Catches "Hampi" in a Hindi query and small typos, which the Lab's perturbations will test; still closed world and reproducible | One threshold to set; a fuzzy match can link the wrong entity |
| C. ReFinED for English queries, A for Hindi and Kannada | A published neural linker for English | Open world: many links land outside the graph; two methods for three languages makes RQ3 harder to read |
| D. An LLM marks the names, then A or B links them | Good at spotting names in long questions | The query generator's model inside a system risks favouring its own wording; the judge's model may not be used inside a system at all |

Ambiguous names (a name shared by a town and its temple, for instance) are handled the same way in A and B: every
entity the name matches becomes a seed, and the span's weight is split equally among them. No hand rule picks one,
and PPR spreads from all of them.

## Recommendation

**B.** It keeps the linker closed world and reproducible, and it covers the cases the Lab is designed to test
(transliteration, typos). Its quality is measured, not assumed:

- The author marks the entities in the 40 dev queries (a small sheet, blind to the linker's output).
- Precision, recall and F1 of the links on those queries, overall and per language; the fuzzy threshold is set on
  the same dev queries, and the exact-only result (option A) is reported beside it.
- The share of dev and test queries with at least one link is reported, as the specification asks.

## Decision

Option B, as recommended: gazetteer matching in English, Hindi and Kannada, Hindi and Kannada names also
indexed in Latin letters, and a RapidFuzz fallback with one threshold set on the dev queries. The exact-only
version (option A) is reported beside it.

## Consequences

- New: `src/graph_retrieval/linker.py`, a labelling sheet for the 40 dev queries, and the linking report.
- `rapidfuzz` and `indic-transliteration` are added to `pyproject.toml`.
