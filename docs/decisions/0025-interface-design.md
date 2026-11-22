# 0025: The HeritageRec interface: design angle, graph views, explanations, self-testing and hosting

- Status: accepted (author, 2026-11-22: chose the angle and removing the old interface; asked for the best
  option to be taken on every other point, as recorded below)
- Date: 2026-11-22

## Context

Decision 0012 (now accepted) asks for a demo with explanations and a graph explorer. The author wants more than
a demo: a reader should see the knowledge graph, how each ranking is made and how recommendations are made, and
the interface should test and break itself in the open. Three rules shape everything below:

- Every number on screen is read from a file a script produced, never typed in. A stage that is not built or
  measured yet is shown as such, with its decision record, never filled with placeholder data.
- What exists on 22 Nov 2026: corpus v1 (14,485 documents), the core graph (24,006 nodes, 42,990 edges),
  passages and BM25/RM3 indexes, the data card. Not yet: dense runs (Kaggle), PPR and the other graph systems,
  fusion, reranking, queries and judgements. The interface switches each part on when its result files exist.
- No record carries coordinates yet (planned for week-5 cleaning), but the raw Wikidata responses already on
  disk hold P625 coordinates for 4,481 of the 8,858 corpus entities (counted 22 Nov 2026). No new download is
  needed.

The conference version's interface (`api/`, `frontend/`, `src/8_streamlit_app/`, `src/8_dashboard/`,
`run_app.py`) serves the old 303-document corpus.

## Options and choices

### 1. Design angle (author's choice)

| Option | For | Against |
| --- | --- | --- |
| A. Case file + atlas | Fits the research question, which is a contest: each search is a case heard by a text lens and a graph lens; the atlas tells the corpus as a story | Most design work |
| B. Field atlas only | Strong first impression | Search and ranking become secondary |
| C. Retrieval game | Playful | Risks mixing with blind validation judging |
| D. Plain search page | Fast | Forgettable; explains little |

**Chosen: A.** Four places, one visual language:

- **Story** (front page): a scroll-driven account of the corpus. Where the documents come from, which sources
  and languages, the places the corpus cannot fill (from the data card), and the question being tested. Each
  figure links to its source file.
- **Atlas**: India drawn as an ink map; entities with coordinates as marks. Clicking a place opens the heritage
  near it (nearest entities, not a fixed radius, so sparse regions still answer), the graph that connects them
  (shared dynasty, style, century, administrative place), and the documents about them.
- **Cases**: search. Text lens and graph lens side by side, the path from the query's entities to each graph
  result drawn out, and a verdict only where the benchmark has measured one.
- **Ledger and Lab**: every number with its file and commit, and the tests that try to break the system.

Visual language: archival print, not app chrome. Paper and lamp-black ink, with indigo, lac red, turmeric and
verdigris as the only accents, each with one meaning (text lens, graph lens, warning, measured). Latin,
Devanagari and Kannada are set as equals: Source Serif 4, Noto Serif Devanagari, Noto Serif Kannada, with IBM
Plex Mono for evidence (all SIL Open Font Licence). Components are taken from the archive: evidence slips
(passage excerpts with the matched terms marked and the score in the margin), provenance stamps (source,
licence, revision), margin notes that explain a panel when asked, a path ribbon, a period rail of centuries.
None of these: gradient hero sections, glass cards, emoji icons, stock illustrations, mandala or temple
clichés. A dark "night archive" theme is defined from the same tokens.

### 2. What to do with the old interface (author's choice)

Removed entirely; git history and the `v0-icicacs-2026` tag keep it. The new interface is built clean.

### 3. Stack and hosting

| Option | For | Against |
| --- | --- | --- |
| A. Next.js (static export) + FastAPI in one Docker image on Hugging Face Spaces (free CPU tier) | React's graph and map libraries; live BM25 needs Java, which a Docker Space can hold; the same image runs locally with one command | Two languages |
| B. SvelteKit + FastAPI | Light; good for scroll stories | Smaller ecosystem for WebGL graphs |
| C. Astro static site on GitHub Pages | Free and fast | No live search, only precomputed results |
| D. Streamlit or Gradio | Quickest | Looks like every ML demo; little control over interaction |

**Chosen: A.** New folders: `server/` (FastAPI, reads corpus v1, the graph and the indexes) and `web/` (Next.js,
TypeScript, statically exported and served by the server). Free-tier memory is checked by a script against the
real index and graph sizes before deploying.

### 4. Drawing the graph, and how much of it is visible

| Option | For | Against |
| --- | --- | --- |
| A. Whole graph in 3D (the old `react-force-graph-3d`) | Striking | A hairball at 24K nodes; unreadable; heavy |
| B. Whole graph in 2D WebGL | Shows scale | Still unreadable; hubs dominate |
| C. Level of detail: an overview of communities, then ego and path views that grow on demand, under a node budget | Readable at every step; scales; matches how the systems use the graph | Needs a builder for communities and an API for neighbourhoods |

**Chosen: C**, drawn with sigma.js and graphology (WebGL, MIT), layout in a web worker.

- **Overview**: communities of the core graph (networkx Louvain, fixed seed, so the same graph gives the same
  communities) as single marks, sized by documents; clicking one opens it.
- **Ego view**: one entity and its neighbours; each click expands one more hop. A node budget (default 150,
  raised when the device can carry it) is never exceeded: when a step would exceed it, the most connected
  neighbours collapse into a bundle mark ("+N more through Mughal Empire"). Hubs (top degree percentile,
  computed by the builder from the graph, as in decision 0007) are always bundled, never drawn as spokes.
- **Path view**: from a query's linked entities to a result, the paths that carry the graph score.
- **Filters**: edge layer (core now; hyperlinks, Getty AAT, geography and mentions as they are built), relation,
  node kind, and a period rail over the century nodes.
- Every visible edge carries its provenance: relation, layer, source (Wikidata revision).

### 5. Map

| Option | For | Against |
| --- | --- | --- |
| A. MapLibre GL with a hosted basemap | Familiar slippy map | Tile terms and keys; generic look; boundary depiction not under our control |
| B. d3-geo on canvas with one boundary file in the repo | Full control of the drawn look; offline; light for a few thousand marks | Hand-built zoom and labels |

**Chosen: B** (d3, ISC). India's boundary follows the official Survey of India depiction; the boundary file and
its licence are checked before use and recorded in `docs/data_notes.md`. Entities without coordinates are never
placed by guesswork; the atlas states how many are unplaced, from the builder's report.

### 6. Showing how a ranking is made

| Option | For | Against |
| --- | --- | --- |
| A. Final list only | Simple | Explains nothing |
| B. Score per result | Little work | A score alone is not an explanation |
| C. Every stage, each with its real intermediate output, checked against the final score | Shows the actual mechanism; checkable | Most work |

**Chosen: C.** A case page shows the stages in order, each as computed:

1. Query analysis: the tokens each language's analyser produced; the entities the linker found.
2. Candidates from each system. BM25: per-term contributions to the winning passage (from Lucene's term
   statistics); RM3: the expansion terms and weights; MaxP: all passages of the document with their scores,
   the winner marked. Dense: the best passage and its similarity (dense scores do not split into terms, and the
   page says so). Graph (PPR): the seed entities and the paths that carry the score.
3. Fusion: each system's rank and its reciprocal rank fusion share.
4. Reranker and LambdaMART: score change, and SHAP contributions per feature for LambdaMART.

A stage that is not built shows its decision record and "not built yet". **Explanation check:** for BM25, the
term contributions must add up to the score the system returned; if they do not, the page shows a warning and
the Lab records a failure. The same check is added for every later stage that can be decomposed.

Recommendations ("more like this" on any document, decision 0009) are shown the same way: each signal's list,
the fusion, then what the diversity step changed across document types.

### 7. Self-testing in the open (the Lab)

| Option | For | Against |
| --- | --- | --- |
| A. Unit tests in CI only | Standard | Invisible to readers |
| B. A. plus a public Lab page that runs and records stress tests against the real systems | Shows where each system breaks; failures become cases a reader can open | More work |

**Chosen: B.**

- **Known-item sanity check, runnable now:** a seeded sample of documents is searched by its own title; success
  at rank 1 and reciprocal rank are computed with ranx. Labelled as a check that the indexes work, not as a
  benchmark result (titles also open every passage, so this is easy on purpose).
- **Perturbations**, applied by seeded, deterministic rules to the sanity sample now and to dev queries once
  they exist (never test queries before the analysis plan): typos, romanised Hindi and Kannada, entity names
  swapped into another script from the gazetteer, diacritics stripped, truncation, one-word and empty queries,
  hub-entity queries. Measured by rank-biased overlap with the unperturbed list and by known-item success.
- **Failure gallery:** the worst cases collected automatically from each run, each opening its case page.
- **Engineering breaks:** property-based fuzzing of every server endpoint (Hypothesis), the server started with
  an index or the graph missing (the interface must degrade and say why), slow-network states, and latency at
  the median and 95th percentile measured by a script.
- Every Lab number is written by a script to `results/interface/` with its commit, like any other result.

### 8. Testing the interface itself

pytest for the server; Vitest for components; Playwright end-to-end against the real local server and data
(no mocked API); axe accessibility checks on every page; screenshot comparison for the key views; a performance
budget on page weight and first render. All run in CI; the frontend gets its own lint and type check.

### 9. Getting started

- A guided first case: five short steps over a real query, explaining each panel, skippable, offered once.
- Margin notes: every panel has "what am I looking at?", in plain language.
- Quickstart in the README: one command with Docker, or two with uv and npm; a troubleshooting table (Java not
  found, indexes not built, port in use, memory, missing result files and what the interface shows then).

## Phasing (one branch each, each merged before the next starts)

1. `refactor/remove-old-ui`: remove the old interface; fix CI, READMEs, the top-level README.
2. `feature/explorer-data`: coordinates from the raw responses, communities, hub percentile, the atlas and
   graph files the interface reads, a build report, tests.
3. `feature/interface-server`: FastAPI over corpus v1, graph and BM25, with the explanation endpoints and the
   degraded modes; tests and fuzzing.
4. `feature/interface-web`: design tokens and components first, then Story, Atlas, Cases, graph views,
   Ledger; Playwright and axe.
5. `feature/interface-lab`: the sanity check, perturbations, failure gallery, latency.
6. `feature/interface-release`: Dockerfile, the Space, Quickstart and troubleshooting.

Later systems (dense, PPR and the other graph methods, fusion, reranker, LambdaMART, the recommender) appear in
the interface when their run files exist; no interface change should be needed beyond their explanation panel.

## Consequences

- The specification's must-ship versus proposed table moves the demo and graph explorer to accepted, as an
  addition that does not move the phase 1 gates.
- The 15-query validation judging sheet (phase 2) is built later in the same visual language, blind to systems.
- CI gains the web checks; `.github/workflows/tests.yml` stops linting `api/`.
