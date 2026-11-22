// Client for the HeritageRec server (server/app.py). Every number the interface shows comes through here or
// from a result file the ledger lists; nothing is computed or typed in on this side.

export type Labels = Partial<Record<"en" | "hi" | "kn", string>>;

export interface NodeCard {
  id: string;
  kind: "document" | "entity" | "connector" | "period";
  type: string | null;
  labels: Labels;
  degree: number;
  hub: boolean;
  community: number | null;
  documents: number;
  lat?: number;
  lon?: number;
  image?: ImageRef;
}

export interface ImageRef {
  thumb: string;
  full: string;
  width: number | null;
  height: number | null;
  licence: string;
  credit: string;
  page: string | null;
  source: string;
}

export interface GraphEdge {
  source: string;
  target: string;
  relation: string;
  relation_label: string;
  layer: string;
  revision: string;
}

export interface Bundle {
  relation: string;
  relation_label: string;
  direction: "in" | "out";
  kind: NodeCard["kind"];
  count: number;
  sample: NodeCard[];
}

export interface EgoView {
  center: string;
  budget: number;
  nodes: NodeCard[];
  edges: GraphEdge[];
  bundles: Bundle[];
  neighbours: number;
  shown: number;
  center_is_hub: boolean;
}

export interface Community {
  id: number;
  size: number;
  documents: number;
  entities: number;
  placed: number;
  label: string | null;
  top: string[];
}

export interface Overview {
  min_size: number;
  communities: Community[];
  links: { a: number; b: number; edges: number }[];
  others: { communities: number; nodes: number };
  hubs: string[];
}

export interface PathView {
  from: string;
  to: string;
  through_hubs: boolean | null;
  length: number | null;
  paths: { nodes: NodeCard[]; edges: GraphEdge[] }[];
}

export interface Place {
  id: string;
  lat: number;
  lon: number;
  type: string | null;
  labels: Labels;
  hub: boolean;
  documents: number;
}

export interface Shared {
  node: NodeCard;
  members: string[];
}

export interface NearView {
  point: { lat: number; lon: number };
  places: (NodeCard & { distance_km: number })[];
  links: GraphEdge[];
  shared: Shared[];
  shared_edges: GraphEdge[];
  periods: Shared[];
  documents_about_several: Shared[];
  documents_per_place: Record<string, number>;
}

export interface Word {
  word: string;
  match: boolean;
}

export interface SearchResult {
  rank: number;
  doc_id: string;
  score: number;
  best_passage: string;
  title: string | null;
  source: string | null;
  doc_type: string | null;
  language: string;
  snippet: Word[] | null;
  image?: ImageRef;
}

export interface SearchView {
  system: "bm25" | "bm25_rm3";
  language: string;
  query: string;
  detected: { language: string; letters_by_script: Record<string, number> };
  settings: Record<string, Record<string, number>>;
  passages_retrieved: number;
  passage_depth: number;
  results: SearchResult[];
  linked: Linked;
  top_match: { query_words: number; in_best_passage: number; missing: string[] } | null;
}

export interface Linked {
  mentions: { text: string; method: "exact" | "romanised" | "fuzzy"; score: number; candidates: NodeCard[] }[];
  seeds: Record<string, number>;
}

export interface TermPart {
  term: string;
  multiplier: number;
  bm25_weight: number;
  contribution: number;
}

export interface Explanation {
  system: string;
  language: string;
  doc_id: string;
  query_tokens: string[];
  terms: { term: string; multiplier: number }[];
  rank: number | null;
  passages_in_document: number | null;
  passages_retrieved: { passage: string; score: number }[];
  passage_depth: number;
  winner: null | {
    passage: string;
    score: number;
    terms: TermPart[];
    check: { recomputed: number; lucene: number; matches: boolean };
    text?: Word[];
  };
  note?: string;
}

export interface GraphRank {
  seeds: NodeCard[];
  settings: { restart: number; hub_power: number; decision: string };
  results: { rank: number; score: number; document: NodeCard; path: PathView | null }[];
  walk_spends_time_at: { node: NodeCard; share: number }[];
}

export interface DocumentView {
  id: string;
  title: string;
  language: string;
  doc_type: string;
  source: string;
  url: string;
  licence: string;
  period_start: number | null;
  period_end: number | null;
  fetched_at: string;
  sha256: string;
  raw_ref: string;
  words: number;
  passages: number;
  entities: NodeCard[];
  in_graph: boolean;
  image?: ImageRef;
  get_it: { label: string; url: string }[];
}

export interface PartStatus {
  status: "ok" | "missing" | "not built yet";
  reason?: string;
  fix?: string;
  see?: string;
  [key: string]: unknown;
}

export interface Health {
  corpus: PartStatus;
  graph: PartStatus;
  keyword: PartStatus;
  planned: Record<string, PartStatus>;
}

export interface CorpusStats {
  source_file: string;
  built: string;
  commit: string;
  snapshot: Record<string, unknown>;
  by_source: Record<string, number>;
  by_language: Record<string, number>;
  by_doc_type: Record<string, number>;
  duplicates_merged: number;
}

export interface LedgerRow {
  file: string;
  bytes: number;
  built?: string;
  commit?: string;
  readable?: boolean;
}

/** A part of the system that is missing or not built: the interface shows the reason and the fix. */
export class Unavailable extends Error {
  constructor(
    public part: string,
    public reason: string,
    public fix: string,
  ) {
    super(`${part}: ${reason}`);
  }
}

/** The server refused the input (400, 404, 422): shown to the reader as is. */
export class Refused extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

// In development the server runs on its own port; the release serves the site and the API from one origin.
export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? (process.env.NODE_ENV === "development" ? "http://127.0.0.1:8000" : "");

function detailText(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((d) => (d as { msg?: string }).msg ?? String(d)).join("; ");
  return JSON.stringify(detail);
}

export async function get<T>(path: string, params?: Record<string, string | number | undefined>): Promise<T> {
  const url = new URL(API_BASE + path, typeof window === "undefined" ? "http://localhost" : window.location.href);
  for (const [k, v] of Object.entries(params ?? {})) if (v !== undefined && v !== "") url.searchParams.set(k, String(v));
  let res: Response;
  try {
    res = await fetch(url.toString());
  } catch {
    throw new Unavailable(
      "server",
      "the interface server is not answering",
      "start it from the repository root: uv run python -m server",
    );
  }
  if (res.ok) return (await res.json()) as T;
  const body = await res.json().catch(() => ({ detail: res.statusText }));
  if (res.status === 503 && body.detail && typeof body.detail === "object" && "part" in body.detail) {
    const d = body.detail as { part: string; reason: string; fix?: string };
    throw new Unavailable(d.part, d.reason, d.fix ?? "");
  }
  throw new Refused(res.status, detailText(body.detail));
}

export const enc = (id: string) => encodeURIComponent(id);

export const api = {
  health: () => get<Health>("/api/health"),
  corpusStats: () => get<CorpusStats>("/api/corpus/stats"),
  ledger: () => get<LedgerRow[]>("/api/ledger"),
  overview: (minSize = 10) => get<Overview>("/api/graph/overview", { min_size: minSize }),
  ego: (id: string, budget?: number, relations?: string) =>
    get<EgoView>(`/api/graph/ego/${enc(id)}`, { budget, relations }),
  node: (id: string) => get<NodeCard>(`/api/graph/node/${enc(id)}`),
  path: (source: string, target: string) => get<PathView>("/api/graph/path", { source, target }),
  rank: (seeds: string, hubPower: number, restart: number, k = 10) =>
    get<GraphRank>("/api/graph/rank", { seeds, hub_power: hubPower, restart, k }),
  suggest: (q: string) => get<(NodeCard & { closeness: number })[]>("/api/suggest", { q }),
  find: (q: string) => get<NodeCard[]>("/api/graph/find", { q }),
  places: () => get<Place[]>("/api/atlas/places"),
  near: (lat: number, lon: number, k = 25) => get<NearView>("/api/atlas/near", { lat, lon, k }),
  analyse: (q: string, lang?: string) => get<{ query: string; language: string; tokens: string[] }>("/api/analyse", { q, lang }),
  search: (q: string, system: string, lang?: string, k = 10) => get<SearchView>("/api/search", { q, system, lang, k }),
  explain: (q: string, doc: string, system: string, lang?: string) =>
    get<Explanation>("/api/explain", { q, doc, system, lang }),
  document: (id: string) => get<DocumentView>(`/api/documents/${enc(id)}`),
};

export function label(labels: Labels, fallback: string): string {
  return labels.en ?? labels.hi ?? labels.kn ?? fallback;
}

/** How a fact reads when walked from `from` to the next node: forward ("founded by →") or backward ("← founded by"). */
export function stepLabel(edge: GraphEdge, from: string): string {
  return edge.source === from ? `${edge.relation_label} →` : `← ${edge.relation_label}`;
}

/** A link that downloads a record as a file, with its attribution written in. */
export function downloadUrl(id: string, format: "txt" | "json"): string {
  return `${API_BASE}/api/documents/${enc(id)}/download?format=${format}`;
}
