# 0020: How the core Wikidata graph is built

- Status: accepted (author chose the options below on 2026-11-21)
- Date: 2026-11-21

## Context

Decision 0006 makes the Wikidata layer the headline graph for RQ1, and decision
0007 limits it to the corpus entities (seeds plus one hop) with hubs down-weighted
at retrieval time. That leaves three questions open: which nodes the statements
may point to, how the statements are fetched, and which relations go in.

Corpus v1 has 14,485 records. They point to 8,858 distinct Wikidata entities
through their `entity_ids`, and every record has at least one. Free-text mentions
are not in `entity_ids`; they belong to the mentions layer (decision 0017).

Comparable work builds on a fixed KG snapshot plus the entities that documents are
linked to: entity query feature expansion (Dalton et al., SIGIR 2014) and EsdRank
(Xiong and Callan, CIKM 2015) on Freebase; knowledge-graph recommenders such as
KGAT (Wang et al., KDD 2019) take the items' one-hop Freebase neighbourhood and
drop rare entities. None of them adds text-similarity edges to the KG.

## Options considered

Nodes the statements may point to:

| Option | For | Against |
| --- | --- | --- |
| A. Closed: both ends among the 8,858 corpus entities | Exactly the 0007 extent | Loses connectors with no document, such as an architectural style with no article in the corpus |
| B. A, plus targets that link two or more corpus entities | Keeps the connectors that can join documents; a node with a single link adds nothing to PPR between documents | One rule to state and report |
| C. Every target of an outgoing statement | Most facts | Many leaves with one link each, which inflate the node counts |
| D. C, plus incoming statements | Most coverage | The neighbour probe (19 Nov) showed incoming "genre" alone brought 689 entities, 358 of them people, mostly off-topic |

Fetching:

| Option | For | Against |
| --- | --- | --- |
| A. `wbgetentities` API, 50 entities per request | Full entity JSON with each entity's revision ID; raw responses saved like every other collector | Larger raw files than SPARQL |
| B. SPARQL with the existing client | Reuses the probe code | No revision IDs; the query service can lag behind live Wikidata |
| C. Full Wikidata dump | Exact snapshot | Over 100 GB; breaks the laptop rule |

Relations added to the 16 from the neighbour probe:

| Option | For | Against |
| --- | --- | --- |
| Derived period nodes (centuries) | Already in the specification ("in period"); connects objects and sites across sources | Wikidata's century precision is stored loosely |
| P31 instance of | Helps concept queries | Very large class hubs |
| P140 religion | Real facts | A few giant hubs |
| P1435 heritage designation | Real facts | One giant hub that mirrors how the seeds were chosen, so it leaks the sampling design into the graph |

## Decision

- **Nodes: option B.** The outgoing statements of the 8,858 corpus entities are
  fetched. A target with no document is kept only when it is linked from two or
  more distinct corpus entities. Kept connectors are not expanded further: their
  own statements are not fetched.
- **Fetching: option A**, `wbgetentities` with claims, labels (en, hi, kn) and
  revision info. Every response is saved untouched under `data/raw/graph_core_v1/`.
- **Relations:** the 16 probe relations (P131, P276, P361, P527, P88, P84, P112,
  P53, P36, P149, P136, P135, P1365, P1366, P800, P170), plus derived century
  nodes. P31, P140 and P1435 are not edges. P31 classes are kept as a node
  attribute so node types can be reported.

Rules for statements and periods:

- Only "truthy" values are used, as in the query service's `wdt:` prefix: preferred-rank values
  if a property has any, otherwise normal-rank values; deprecated values,
  "unknown value" and "no value" are skipped.
- Documents link to their entities through an `about` edge (from `entity_ids`).
- Century edges (`in period`) come from a record's own `period_start` and
  `period_end`, and from an entity's inception (P571), start (P580), end (P582)
  and dissolution (P576) dates. A node links to every century its dates span.
  Dates less precise than a century are skipped.

## Consequences

- Output: `data/graph/core_v1/nodes.jsonl.gz` and `edges.tsv.gz`, with columns `source`,
  `relation`, `target`, `layer` and `origin`, plus the Wikidata revision behind each
  statement edge. The files are sorted and byte-identical on rebuild, and later layers
  (decision 0006) add rows with their own `layer` value.
- Statistics (`results/graph/core_v1.json` and `.md`) report nodes by kind and type, edges by
  relation, degrees, components, the share of documents in the largest
  component, the top hubs, and the number of connectors kept and dropped. They are
  generated into the data card.
- Statement edges to the corpus's source institutions (Cleveland, Met, Art Institute
  of Chicago, Wellcome Collection, Internet Archive) are skipped. Museum objects' own
  Wikidata items name their holding museum, which made the Cleveland Museum of Art the
  top hub and linked objects by source rather than by heritage (author, 21 Nov 2026;
  `docs/data_notes.md`, section 9).
- Hub down-weighting (0007) is applied by the retrieval code, not stored in the
  graph.
