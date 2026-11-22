# 0028: Interface, second version: page by page, interactions, motion and the live graph

- Status: proposed (plan for the author before building)
- Date: 2026-11-22

## Context

The author's review of the redesign (decision 0025, 22 Nov): the collection-first home works; the search page
looks dull and off; the graph is far too small and not dynamic; the interface lacks considered interactions,
transitions and visual appeal across pages. What the screens show:

- **Search.** The first screen is spent on two explanation steps, so results start below the fold. The two lenses
  sit side by side but are never compared. Snippets carry raw Wikipedia section markup ("== Location =="). No
  thumbnails, no facets, no keyboard flow. Suggestion chips with dashed red borders look unfinished.
- **Graph.** The overview draws 168 equally black dots; about 120 communities share no edge, and the layout pushes
  them into an empty-looking arc while the connected core is squeezed into the middle with overlapping labels. A
  neighbourhood shows one step only (the Hoysala Empire: 14 nodes, a star). The layout is computed once, out of
  sight, then drawn frozen; expanding rebuilds the picture from scratch; there is no hover, focus or camera motion,
  and every node is the same colour.
- **Everywhere.** No motion, no transitions between pages, no shaped loading states, few images outside the home
  page.

## Principles

1. **Content first.** Objects, places, passages and facts carry the page; words about the site stay short.
2. **Motion explains cause.** Things move only to show what changed and why: a result sliding to its new rank
   when the system changes, new graph nodes growing out of the node that was expanded, the walk travelling along a
   path. Durations 120, 200 and 320 ms; one easing curve; everything still when the reader asks for reduced motion.
3. **Fast feedback.** Every action answers within 100 ms (skeletons shaped like the content they replace).
4. **Keyboard and screen reader first.** A command palette, list navigation with keys, every canvas mirrored by a
   text view, focus never lost in a drawer.
5. **Honest states.** Not built, not measured and missing stay visible, as now.

## Global

| Element | What it does |
| --- | --- |
| Command palette (⌘K or /) | Find documents, entities and pages from anywhere; recent cases; actions (switch theme, notes) |
| Page transitions | React `<ViewTransition>` (React 19.3): cross-fade between pages; an object's image morphs from its tile into the document page's hero |
| Drawers | One accessible drawer pattern (Radix Dialog) for the working of a ranking, a node's details, a place |
| Loading | Skeletons in the shape of results, tiles and panels; no spinners |
| Entity types | One categorical palette for the six entity types (site, polity, person, style, place, culture), validated for colour blindness with the dataviz validator, with a legend and icons, so identity never rests on colour alone. Used only in graph and map marks; the four pigments keep their meanings |
| Icons | Lucide, small set: entity types, document types, actions |

## Page by page

### Home
1. Search with live suggestions as one types (entities and documents, in three scripts).
2. **A thread from the graph**, chosen at random on each visit from real data: an object, the entity it is about,
   and a site joined to it by a fact, drawn as three linked cards that reveal one after another.
3. The collection wall, now with filters (century, museum, kind of object), hover lift, and a quick look.
4. Three doors (Search, Atlas, Graph), each with a small live picture: a ranking, the dot map, a neighbourhood.
5. What this is, as now.

### Search (the largest change)
```
┌ query ───────────────────────── [lang] [BM25|RM3] ──┐   sticky
│ read → candidates → two lenses → fusion → verdict   │   pipeline strip; each step opens its detail
├ facets: language · kind · source · century ─────────┤
│  TEXT LENS              spine        GRAPH LENS      │
│  1 Chennakeshava ●──────────────────● 4              │   lines join a document found by both lenses
│  2 Sacred Ensembles ●───────┐        1 Hoysala Kingdom│   ranks animate when the system or seeds change
│  3 Architecture of India     └──────● 2               │
└──────────────────────────────────────────────────────┘
```
- Results on the first screen; the explanation steps become a slim **pipeline strip** that opens on demand.
- The **agreement spine**: a line between the two columns joins every document both lenses found, so agreement
  and disagreement are seen at a glance; a document found by one lens only is marked as such.
- Result cards: thumbnail for objects, kind and language marks, period, source; snippet cleaned of wiki markup
  (display only; the markup itself is recorded for week-5 cleaning).
- "Why here?" opens the working in a side drawer: the term bars grow in, the sum check ticks when it adds up.
- Graph lens: start points chosen automatically by the query linker (decision 0026) once built; until then the
  current picker, restyled as plain chips.
- Keys: j and k move between results, Enter opens, w opens the working, / returns to the query.

### Graph (the second largest change)
- **Live layout.** ForceAtlas2 runs in a web worker and the reader sees the graph settle; it stops when still.
- **Growing, not rebuilding.** Expanding a node keeps every placed node where it is; the new neighbours grow out of
  the clicked node and settle.
- **Two steps by default**, within the budget, so a neighbourhood shows its shape rather than a star.
- **Colour and pictures.** Nodes coloured by entity type with a legend; documents with an open image drawn as small
  thumbnails (sigma's node-image program); centuries and other hubs as hollow rings.
- **Focus.** Hover dims everything but the node and its neighbours; selecting flies the camera to it; edge labels on
  hover; curved edges where two facts join the same pair.
- **Paths.** The walk travels along the path as a moving pulse, step by step.
- **Overview, redrawn honestly.** The connected core as a live graph; the communities that touch nothing else as a
  sorted shelf of small cards beside it (name, size, a few members), instead of an empty ring of dots.
- Breadcrumbs of the nodes visited; a minimap; a search that flies to a node.

### Atlas
- Density at low zoom (hexagonal bins), dots at high zoom, labels by zoom level; the drop to dots is animated.
- Selecting a place flies to it; its drawer shows the place card, **photographs of objects linked to it**, the
  graph of what ties it, and its documents.
- A century slider fades places in and out; dots coloured by entity type with a legend.

### Document
- Hero image (opens full size in a lightbox), credit and licence; reading view in the serif.
- Arriving from a search, the query's words are marked in every passage.
- "In the graph": a small live neighbourhood. "Close in the graph": documents ranked by PageRank from this
  document's own entities, labelled as such (the recommender of decision 0009 comes later).
- Provenance as a short timeline: fetched, revision, checksum.

### Lab, Ledger, Guide
- Lab: each check a card with a live pass or fail mark that animates in; the measured runs as charts when they exist.
- Ledger: a searchable, sortable table; a drawer previews a result file.
- Guide: an interactive tour that highlights the real elements on the real pages; the written guide stays.

## Tools (all MIT, ISC or BSD; versions pinned at least two weeks old)

| Need | Tool |
| --- | --- |
| Motion for sequences and list reordering | Motion (`motion`) |
| Page transitions | React `<ViewTransition>` |
| Accessible drawer, dialog, tooltip, popover | Radix UI primitives |
| Command palette | cmdk |
| Icons | lucide-react |
| Live graph layout | graphology ForceAtlas2 web worker |
| Images and curves in the graph | @sigma/node-image and @sigma/edge-curve (the image program's current release needs sigma 4: either its sigma 3 release or an upgrade to sigma 4 after checking the changes) |
| Map density | d3-hexbin; d3-transition for map motion |

## Testing

- End-to-end flows for every interaction above (keys, drawers, expanding, paths, filters), on desktop and phone.
- Screenshot comparison for the stable pages; a reduced-motion run in which nothing animates.
- Performance budget: largest paint under 2.5 s and input delay under 200 ms on the local build, measured by a
  script, written to `results/interface/`.
- axe on every page in both themes, as now.

## Order of work

1. Query linker (decision 0026): it makes the graph lens start by itself and gives Search real comparisons.
2. Search, with the global drawer, palette and transitions.
3. Graph.
4. Atlas.
5. Home and Document.
6. Lab, Ledger, Guide; then a motion and polish pass across pages; then the tests above.

## Decision

Waiting for the author.
