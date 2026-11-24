# 0033: The entity-expanded BM25 control: how the entities' names are added

- Status: accepted (author, 2026-11-23: "0033 & 0034, let's do that")
- Date: 2026-11-23

## Context

RQ1 asks whether graph structure beats text. A graph system starts from the entities a query names, so part of its
advantage may be only that it knows those entities. The specification (Section 6) fixes the control that removes
this easy explanation: BM25 with the query expanded by the linked entities' labels and aliases in English, Hindi and
Kannada (decision 0008). The linker is decision 0026, the same one the graph runs use, so both systems see the same
entities. If this control matches the graph, the paper says the gain came from knowing the entities, not from the
structure (0008).

Three choices are left open: how the names are weighted against the query's own words, which index they search
(this matters for RQ3, because the graph crosses languages through Wikidata IDs), and how many aliases go in.

Comparable work: entity query feature expansion (Dalton, Dietz and Allan, SIGIR 2014) adds entity names and
aliases as weighted query features; Xiong and Callan (ICTIR 2015) expand queries with Freebase entities' names and
descriptions and report that weighting matters more than which names are added. Both weight the expansion against
the original query and tune the weight on held-out queries.

## Options considered

Weighting the names:

| Option | For | Against |
| --- | --- | --- |
| A. Append every name to the query text, equal weight | Simplest; no parameter | Many aliases swamp a short query; a long alias list decides the ranking |
| B. Weighted query: the original words weight 1, the names together weight α (Lucene boosts through Pyserini's query builder), α chosen on dev among 0.25, 0.5, 1 | The standard form (Dalton et al.); one parameter, tuned on dev like PPR's hub power | One more dev choice to report |
| C. Two BM25 searches (query; names), fused by reciprocal rank | No weight to tune | A different kind of system (fusion), harder to read as "BM25 plus entities" |

Which index the names search:

| Option | For | Against |
| --- | --- | --- |
| A. The query's own language index only | Matches the plain BM25 baseline | A Hindi query's English entity names never reach English documents, so the control cannot cross languages and RQ3 is unfair to it |
| B. Every language index, each searched with the query (if in that language) plus the names in that language; the three rankings merged by each document's best score per index, normalised (min-max per index) | The control crosses languages through the same entities the graph uses, so RQ3 compares like with like | Score normalisation across indexes is a choice of its own |
| C. B, but merged by reciprocal rank fusion | No score normalisation | Fusion again |

How many aliases:

| Option | For | Against |
| --- | --- | --- |
| A. Every label and alias in the gazetteer | Most recall | Some aliases are noisy (the linker already keeps short Latin aliases out for that reason, 0026) |
| B. Labels plus aliases, after the linker's own filters (no short Latin aliases unless the main label of a place) | Same names the linker trusts; no new rule | A few useful short aliases lost |

## Recommendation

Weighting B (α on dev among 0.25, 0.5 and 1, the untuned α = 1 reported beside it), indexes B, aliases B. The
control then knows exactly the entities the graph knows, in every language, and differs from the graph only in
having no structure, which is what RQ1 and RQ3 need it to isolate.

## Decision

As recommended: weighting B, indexes B, aliases B.

## Implementation (23 Nov 2026)

`src/retrieval/entity_bm25.py`, tests in `tests/test_entity_bm25.py`. Details the record left open, settled so the
control stays fair:

- Weights: query terms at 1; each name term at alpha x (query terms / name terms), so the names together weigh
  alpha times the query whatever the number of aliases. In an index of another language, the names alone.
- Names: exactly the linker's trusted names (the linker now keeps them per entity and language, `Gazetteer.names`).
- Merge: min-max per index gives each index's top document 1.0, so ties are broken by rank within the index, then
  the query's own language first, then a fixed order, then id. A tie-break by id alone put English first every
  time, a language bias found in the first trial and fixed before any run.
- A query that links to no entity is plain BM25 in its own language.
- Runs: `bm25_ent_a025`, `a050`, `a100` on dev (`scripts/run_dev_runs.sh`); every query's entities and names are
  written beside the run.
