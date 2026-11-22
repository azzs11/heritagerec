# 0029: Where the graph lives, how it is queried, and how it is drawn (Neo4j or not)

- Status: proposed (the author asked why the graph does not use Neo4j; options for the author)
- Date: 2026-11-22

## Context

The core graph (24,006 nodes, 42,990 edges) is built from files (`data/graph/core_v1/`, decision 0020), loaded into
memory by the server, ranked by personalised PageRank on a scipy sparse matrix (decision 0027, checked against
networkx), and drawn with sigma.js (decision 0025). That choice was made for drawing, but where the graph is stored
and queried was never compared formally. The author asked why Neo4j is not used. This record makes the comparison.

Three separate questions: where the graph is stored, how the systems query it (PageRank, SimRank, meta-path counts
for LambdaMART), and how the interface draws it.

Licences and state, checked 22 Nov 2026:

| Tool | Licence | State | Note |
| --- | --- | --- | --- |
| Neo4j Community (database) | GPL-3.0 | Active | Runs as a separate Java server |
| Neo4j Graph Data Science | GPL-3.0 (community) | Active | Has PageRank, including personalised |
| Neo4j Visualization Library (NVL) | Proprietary | Active | May only be used with Neo4j Aura or Neo4j's commercial products: excluded |
| neovis.js | Apache-2.0 | Active | Draws Neo4j query results with vis-network (canvas, not WebGL); the browser connects to the database directly |
| Kùzu (embedded graph database) | MIT | Archived October 2025 | Excluded |
| DuckDB with the DuckPGQ extension | MIT | Active | Graph queries (SQL/PGQ) over tables in one file |
| networkx and scipy | BSD | Active | In use: PageRank as sparse matrix power iteration |
| sigma.js | MIT | v3 in use; v4 released 8 Oct 2026 | WebGL; built for large graphs in the browser |
| Cosmograph | CC BY-NC 4.0 | Active | NonCommercial: excluded |

## Options

| Option | For | Against |
| --- | --- | --- |
| A. Files + networkx/scipy + sigma.js (current) | One command rebuilds everything from the raw responses; byte-identical builds; PageRank in about 0.1 s and checked against networkx; no server to run or secure; fits the free hosting tier | No ad-hoc query language; meta-paths written as sparse matrix products rather than Cypher |
| B. Neo4j Community + Graph Data Science, drawn with neovis.js | Cypher for exploring and for meta-path patterns; a well-known tool | A second server (Java, 1-2 GB of memory) to run and keep in step with the files; results depend on database state, so reproducing a number needs the database rebuilt the same way; GPL-3.0; neovis draws on canvas and needs the browser to reach the database, which a public site should not allow; Neo4j's own drawing library is not licensed for this project |
| C. A, plus a Neo4j export at release | Keeps A's reproducibility; researchers who prefer Cypher load the same graph into their own Neo4j with one command (`neo4j-admin database import` CSVs and a script) | One more file set to generate and test |
| D. DuckDB + DuckPGQ as the store, sigma.js to draw | One embedded file; graph queries in SQL/PGQ; no server | The extension is young; PageRank still needs scipy; adds a query layer the current systems do not need |

What comparable work does: graph IR papers that report PageRank or meta-path features (for example PathSim, Sun et
al. 2011) compute them as matrix operations; Neo4j is common in applications and demos, less so in reproducible IR
experiments, where the number must come from a script on a tagged commit.

## Recommendation

**C.** Keep the graph in files and the computation in scipy and networkx, which is the stronger choice for a study
whose every number must be rebuilt by one command; keep sigma.js (WebGL) for drawing, since Neo4j's own library is
not licensed for an open project and neovis.js is slower and would expose the database. Add a Neo4j export to the
release so that anyone who prefers Cypher can load the identical graph into Neo4j, with a test that the export and
the files hold the same nodes and edges.

Separately, sigma.js 4 should be tried once it has been out for a few months; the upgrade is contained in
`web/components/LiveGraph.tsx`.

## Decision

Waiting for the author.
