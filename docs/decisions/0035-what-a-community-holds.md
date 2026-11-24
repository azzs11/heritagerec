# 0035: Showing what a graph community holds, and where and when it lies

- Status: accepted (author, 2026-11-23: "0035 okay")
- Date: 2026-11-23

## Context

The graph page's overview draws the 52 communities that share facts with one another as equal grey dots named by
their most connected member, and shelves the other 116 (`data/explorer/v1/communities.json.gz`, 168 communities of
10 or more nodes). A reader cannot tell what a community is about without opening it. "Chamba State" names a
community of 1,022 nodes; colouring that dot as a polity would say something false about the other 1,021, so a
single colour per community is ruled out.

What the data allows (23 Nov 2026): every node has a kind and, for entities, a type; 2,350 of the 3,539 entities in
those 168 communities have coordinates (66%); periods are graph nodes, so each community's centuries can be counted.

## How a reader uses it

A reader opens the overview to answer "what is in this graph, and where do I start?". They need, at a glance,
which communities are about places, which about people and dynasties, which about traditions; where in India each
lives; and which period it belongs to. Then they open one.

## Options considered

| Option | For | Against |
| --- | --- | --- |
| A. Keep grey dots | Honest; no work | Says nothing until opened |
| B. One colour per community, from its label entity's type | Easy | False for mixed communities (above) |
| C. A **composition ring** per community: the node split into arcs by the share of sites and places, people and polities, culture and style, other entities, and documents (the site's validated type colours, with a legend and the shares in words on focus) | Honest about mixture; reads at a glance; uses colours readers already know from the atlas and neighbourhoods | Small rings need a minimum size to read; a table view is needed for screen readers (as for every canvas, 0028) |
| D. **Arrange by place**: each community placed at the median of its members' coordinates on India's outline, with a toggle back to the network layout | Answers "where does this live?", ties the graph to the atlas, and makes regional clusters (Karnataka, Delhi, Tamil Nadu) visible | A third of entities have no coordinates; pan-Indian communities have no meaningful centre and must be shown apart ("across India") |
| E. **Arrange by time**: each community on a century axis by its members' median century, its span as a bar | Answers "when?"; the corpus spans the 24th century BCE to now | Many members lack a period; communities spanning millennia read as long bars with little meaning |
| F. Name each community by its three most connected members, not one | Cheap; says more than one name | Longer labels collide more |

## Recommendation

C with F, and D as a second arrangement behind a toggle ("as a network", "on the map"). The ring says what a
community holds; the map arrangement says where; three names say what it is about. E is left out: period
coverage is too uneven to draw honestly, and the atlas already filters by century.

Data: the explorer build (`src/explorer/build.py`) adds to each community its counts by kind and type group, its
median coordinates and the share of members with coordinates, and its three top members; the report gives how many
communities have no centre. Tests cover the counts and the median.

## Decision

As recommended.

## Implementation (24 Nov 2026)

- Data (`src/explorer/build.py`, tests in `tests/test_explorer.py`): each community gains `composition` (counts by
  the interface's colour groups, documents apart), `top_labels` (its three most connected members) and a `centre`:
  the median of its placed members, only when at least 3 are placed and the middle half of their latitudes and of
  their longitudes each spans 3 degrees or less (about 330 km); otherwise `spread` says "across India" or "too few
  placed". How many fall in each is in `results/explorer/explorer_v1.json` (`spread_of_10_or_more`). The nodes file
  is unchanged byte for byte.
- Interface (`web/app/graph/CommunityMap.tsx`): rings drawn in SVG, each a focusable button whose label states the
  three names, what it holds and where it lies; "As a network" (ForceAtlas2 from a fixed circle) and "On the map"
  (centres projected on India's graticule, no borders; communities with no centre stand in a side column). Rings
  glide between the two (320 ms, still under reduced motion). On the map, overlapping rings are pushed apart
  deterministically, and a ring moved further than its radius shows a hairline to its true point; only the chosen
  community's links are drawn. Every community is also listed as a text table.
- Found in testing and fixed: drawing the hovered ring on top moved it in the DOM between mouse-down and mouse-up,
  so the first click on a ring did nothing; only the chosen ring is now raised.

