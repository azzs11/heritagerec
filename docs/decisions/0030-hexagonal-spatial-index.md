# 0030: A hexagonal spatial index (Uber's H3) for the atlas, the graph, ranking and recommendation

- Status: proposed (the author asked to study Uber's hexagon system and use it for recommendations and ranking)
- Date: 2026-11-22

## Context

H3 is Uber's open hexagonal grid of the Earth (Apache-2.0; Python `h3` 4.5, JavaScript `h3-js` 4.5, checked
22 Nov 2026). Every point falls in one hexagon per resolution; resolutions nest; each hexagon has six neighbours at
equal distance, so "the hexagons within k steps" (a k-ring, `grid_disk`) is a clean, symmetric notion of nearness.
Uber built it to group and compare places (supply, demand, prices, travel times) on a grid where every neighbour is
the same distance away, which square grids do not give.

Measured on the 4,937 placed entities that are not hubs (22 Nov 2026):

| Resolution | Hexagon edge | Cells holding places | Most places in one cell | Places with a neighbour within one ring |
| --- | --- | --- | --- | --- |
| 4 | about 26 km | 1,010 | 131 | 4,903 |
| 5 | about 10 km | 1,930 | 99 | 4,557 |
| 6 | about 3.7 km | 2,785 | 80 | 3,819 |

So nearness reaches almost every place, while the core graph without its hubs falls into 8,140 communities
(`results/explorer/explorer_v1.md`). Space joins what the facts leave apart, which is what the planned geography
layer (decision 0006, week 6) is for.

The specification sets two limits: the headline RQ1 result uses the core Wikidata layer only, and every other edge
layer is reported as an addition beside it; the graph holds structured facts and entity links, never text
similarity. A proximity layer built from coordinates is neither text similarity nor a Wikidata statement, so it
belongs in its own labelled layer.

## Options

| Option | What it does | For | Against |
| --- | --- | --- | --- |
| A. Display only (current, `d3-hexbin`) | Screen-space hexagons for density on the atlas | Already built | Hexagons change with the window; no stable cells; nothing else can use them |
| B. H3 on the atlas | Geodesic hexagons with stable ids; the resolution follows the zoom; a hexagon can be chosen and its rings shown ("within 1 ring, 2 rings…") | Real cells that the server, the graph and ranking share; concentric rings make nearness visible | A small library in the browser and the server |
| C. A proximity edge layer | `near` edges between places in the same or adjacent resolution-5 cells, with the ring distance kept; its own layer, reported beside the core | Joins what the facts leave apart; tests whether space helps beyond facts (an RQ1 ablation) | Must never be mixed into the headline core result; a dense region (99 places in one cell) needs the same hub care as any other |
| D. Spatial signals in ranking | For LambdaMART: ring distance between the query's linked place and a document's place, same cell or not, documents within k rings; for fusion: a candidate list of documents about places within k rings of the query's places, scored by distance decay | Lets the learned ranker decide how much nearness matters, with SHAP showing it | Needs the linker's places (0026), and judged queries to learn from |
| E. Concentric recommendations | "More like this" for a document with a place: documents about places in its own hexagon first, then ring 1, ring 2…, each ring a band; a signal in the hybrid recommender (decision 0009), fused by reciprocal rank fusion with the graph and text signals | Exactly the "hexagonal" recommendation: nearby first, widening outward, explained by the ring it came from | Space alone ignores period and style; it must be one signal among several, never the only one |

## Recommendation

**B, C, D and E together**, with C kept strictly as its own layer:

- B replaces the screen-space hexagons on the atlas with H3 cells, and adds a ring view to the drawer.
- C becomes the proximity part of the geography layer in week 6, reported as "core + proximity" beside "core",
  never as the headline.
- D adds three spatial features to LambdaMART and one spatial candidate list to fusion.
- E adds the concentric signal to the recommender of decision 0009, shown in the interface ring by ring.

Resolution 5 (about 10 km) is the default for C, D and E, since it gives almost every place a neighbour without
merging whole districts; resolutions 4 and 6 are compared on dev, and the choice is named in the analysis plan.
`h3` and `h3-js` are pinned at releases at least two weeks old.

## Decision

Waiting for the author.
