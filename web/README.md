# web

The HeritageRec interface (decisions 0012, 0025): a Next.js site, exported as static files, that reads only the
server in `server/`. Its angle is a case file with an atlas: the Story tells the corpus and the question, Cases put
a query to the text lens and the graph lens with every step of the ranking shown, the Graph and the Atlas show the
knowledge graph at a readable level of detail, the Ledger traces every number to its file and commit, and the Lab
shows where the system breaks.

Nothing here computes or types in a number: every figure comes from a server route or a result file. A part that
is missing or not built is shown as such, with its reason and fix or its decision record.

## Run it

From the repository root, with the server running (`uv run python -m server`):

    cd web
    npm ci
    npm run dev        # http://localhost:3000; talks to the server on http://127.0.0.1:8000

Set `NEXT_PUBLIC_API_BASE` to use a server elsewhere. `npm run build` writes the static site to `web/out/`.

## Check it

| Command | What it checks |
| --- | --- |
| `npm run typecheck` | TypeScript, strict |
| `npm run lint` | ESLint with the Next.js rules (including React's hook rules) |
| `npm test` | Unit tests (Vitest): the API client's error handling, shared components |
| `npm run e2e` | End-to-end (Playwright) on desktop and phone widths, against the real server and data: every page loads without console errors, passes axe (no serious or critical violations), never scrolls sideways; a case's explanation adds up; a hub is folded; the atlas answers; a refused query says why. Starts both servers unless they are running. Needs `npx playwright install chromium` once |

## Layout

| Path | What it holds |
| --- | --- |
| `app/` | One folder per page: Story (`page.tsx`), `atlas/`, `cases/`, `graph/`, `document/`, `ledger/`, `lab/`, `guide/` |
| `components/` | The design system: seals, missing-part slips, margin notes, names in three scripts, provenance stamps, evidence slips, bar lists, the graph canvas (sigma.js) |
| `lib/` | The typed API client, the loading hook, stored per-viewer settings, display names |
| `tests/` | `unit/` (Vitest) and `e2e/` (Playwright) |

## Design

A working collection instrument rather than an essay: the home page is a search box over a wall of real objects
(open-licence images from The Met and the Cleveland Museum of Art, shown from the museums' own servers with their
credit lines), and each page has the layout its job needs: Search as a two-lens instrument, the Atlas and the Graph
full-bleed with a side drawer, the Ledger as dense tables. Explanations appear when the reader turns on Notes.

Four pigments, each with one meaning: indigo for the text lens, lac red for the graph lens, turmeric for anything
not built, not measured or failing a check, verdigris for what is running or verified. Type is Noto Sans for the
interface and Noto Serif for reading, chosen because their Latin, Devanagari and Kannada are drawn as one family;
IBM Plex Mono for evidence (all SIL Open Font Licence, bundled, no font requests at run time). A dark theme is
defined from the same tokens. Colour contrast is checked by axe in both themes.

The Met's image server sometimes answers automated or unfamiliar visitors with a bot check instead of the picture;
the wall then drops that tile, and a document page says so and links to the object on the museum's site.

The atlas draws no political boundaries: India's boundary must follow the Survey of India's depiction and its
boundary data needs a licence (see decision 0025). The places themselves, as dots, make the map.

The graph is never drawn whole: communities first, then neighbourhoods under a budget, with hubs and overflow
folded into bundles, and every edge carrying its Wikidata revision.
