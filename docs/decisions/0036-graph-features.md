# 0036: Graph features for ranking: meta-paths, SimRank on candidates, entity overlap and Horn's index

- Status: decided under the author's delegation (24 Nov 2026: "make decisions like a senior dev"); the author may
  overrule before any test run
- Date: 2026-11-24

## Context

The specification (Section 6) lists the graph features LambdaMART learns from: the PageRank score, SimRank to the
top seed documents, meta-path counts ("shares dynasty, site, style, place, tradition"), entity overlap and Horn's
index of shared entities. Decision 0007 runs SimRank over each query's candidate set, with hubs down-weighted by
inverse frequency. What each feature counts, over which relations, was left open.

The core graph's relations (`results/graph/core_v1.json`): about, in period, located in (P131), part of (P361),
architectural style (P149), location (P276), replaces and replaced by (P1365, P1366), has part (P527), capital (P36),
family (P53), genre (P136), founded by (P112), commissioned by (P88), creator (P170), architect (P84), movement
(P135), notable work (P800).

Comparable work: meta-path similarity counts typed paths between two nodes (PathSim, Sun et al., VLDB 2011); SimRank
(Jeh and Widom, KDD 2002) scores two nodes as similar when their neighbours are, decay C = 0.8 and about five
iterations in the original; Horn's index (Horn, 1966) is an overlap index of two abundance distributions, used in
the conference version of this project.

## Options considered

Meta-path families:

| Option | For | Against |
| --- | --- | --- |
| A. One count over all relations | Simple | Loses what the specification asks for: which kind of link is shared |
| B. One count per family, each relation in one family: place (P131, P276), site (P361, P527), style (P149, P135), tradition (P136), dynasty and patrons (P53, P88, P112, P170, P84, P36, P1365, P1366), period (in period) | The specification's five plus period; LambdaMART and SHAP can then say which family carries the ranking (RQ2) | Six features from sparse relations: many zeros |
| C. B, with every family also counting two-hop paths | More signal | Hub explosion (0007), slow |

How a shared node counts:

| Option | For | Against |
| --- | --- | --- |
| A. 1 per shared node | Simple | Sharing "India" or "18th century" counts as much as sharing "Hoysala Empire" |
| B. 1 / log(1 + degree) per shared node, hubs included at their small weight | Inverse frequency, as 0007 sets for the graph; a common node still counts a little | One formula to state |

SimRank:

| Option | For | Against |
| --- | --- | --- |
| A. Exact SimRank on the whole graph | Exact | Does not scale (0007) |
| B. Exact SimRank on each query's subgraph: the candidates, up to 25 seed documents (documents about the query's entities), their entities, and those entities' one-hop neighbours other than hubs; undirected; C = 0.8, 5 iterations; the feature is a candidate's highest SimRank to any seed document | 0007's choice; exact within the subgraph; small enough for a dense matrix | A candidate outside the subgraph's reach scores 0 |
| C. Monte Carlo SimRank | Whole graph | Approximation error to report; more code |

## Decision

Meta-paths B (one family per relation, one hop: a document's entities and their neighbours against the query's
seed entities and theirs), counting B (1 / log(1 + degree)), SimRank B. Also: entity overlap (how many of the
document's entities are seed entities) and Horn's index between the document's and the seeds' neighbour counts.
Hubs are never removed from the counts, only weighted down, except as SimRank subgraph members, where a hub would pull
in thousands of nodes.

## Consequences

- `src/graph_retrieval/features.py` computes the features for every (query, candidate document) pair of the runs
  given, written to `data/features/<split>_graph_v1.tsv` with the settings in a report.
- A query with no linked entity gets zero graph features, and LambdaMART learns from the text features for it.
- The features sit beside the text features (BM25, dense, reranker scores, document length, language match) in the
  learning-to-rank table (decision 0037).
