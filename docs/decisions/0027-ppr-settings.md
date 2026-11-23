# 0027: Personalised PageRank settings for the graph lens

- Status: accepted (author, 2026-11-22: "best option")
- Date: 2026-11-22

## Context

Decisions 0007 and 0008 make personalised PageRank (PPR) from the query's linked entities the first graph system:
on the full graph, with very common hubs down-weighted by inverse frequency and the weight tuned on the 40 dev
queries. Four details were left open. `src/graph_retrieval/ppr.py` implements all of them as parameters and is
checked against networkx's PageRank on a small graph (`tests/test_ppr.py`).

## Choices

| Detail | Options | Proposed | Why |
| --- | --- | --- | --- |
| Direction of the walk | Follow statements only from subject to object; or both ways | Both ways | "Hampi is in Karnataka" should also lead from Karnataka to Hampi; a document is reached from its entity only by walking against the "about" edge |
| Several relations between one pair | Count each; or count the pair once | Once | A pair joined by both "replaces" and "replaced by" is not twice as related |
| Hub down-weighting | A step to a node of degree d weighted by d^-p, with p = 0 (none), 0.5 or 1 (inverse frequency) | p = 1 as the default, as 0007 says; p chosen on dev among 0, 0.5 and 1; p = 0 always reported beside it | The core graph's connectivity runs through hubs (`results/explorer/explorer_v1.md`) |
| Restart probability | 0.1, 0.15, 0.3 | 0.15 by default (Page et al. 1999; Haveliwala 2002); chosen on dev | The usual value; a higher restart keeps the walk near the seeds |

Seeds come from the query linker (decision 0026). When a name matches several entities, the name's weight is split
equally among them. A query with no linked entity gets an empty graph ranking, and that is reported, not filled in.

## Decision

The proposed settings: walk in both directions, each pair of nodes counted once, hub power 1 by default and chosen
on dev among 0, 0.5 and 1, restart 0.15 by default and chosen on dev among 0.1, 0.15 and 0.3; the untuned run is
always reported.

## Consequences

- Runs are written as TREC files like every other system, from a TSV of query ids and seeds.
- The tuning grid is small (3 × 3) and runs on dev only; the chosen values are named in the analysis plan before
  it is frozen.
