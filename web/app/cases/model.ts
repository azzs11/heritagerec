// One shape for a result from either lens, so the collation can treat both readings alike.

import { label, type GraphRank, type ImageRef, type PathView, type SearchView, type Word } from "@/lib/api";

export type Lens = "text" | "graph";

export interface Reading {
  id: string;
  rank: number;
  score: number;
  title: string;
  language: string;
  source: string;
  kind: string | null;
  image?: ImageRef;
  snippet?: Word[] | null;
  path?: PathView | null;
}

/** The record id says where a document came from: "wikipedia:hi:123", "met:456", "cleveland:789". */
export function origin(id: string): { source: string; language: string } {
  const [source = "", second = ""] = id.split(":");
  return { source, language: source === "wikipedia" ? second : "en" };
}

export function fromText(r: SearchView): Reading[] {
  return r.results.map((x) => ({
    id: x.doc_id,
    rank: x.rank,
    score: x.score,
    title: x.title ?? x.doc_id,
    language: x.language,
    source: x.source ?? origin(x.doc_id).source,
    kind: x.doc_type,
    image: x.image,
    snippet: x.snippet,
  }));
}

export function fromGraph(r: GraphRank): Reading[] {
  return r.results.map((x) => ({
    id: x.document.id,
    rank: x.rank,
    score: x.score,
    title: label(x.document.labels, x.document.id),
    ...origin(x.document.id),
    kind: x.document.type,
    image: x.document.image,
    path: x.path,
  }));
}

export function seedString(seeds: Record<string, number>): string {
  return Object.entries(seeds)
    .map(([q, w]) => (w === 1 ? q : `${q}:${Number(w.toFixed(4))}`))
    .join(";");
}

export function parseSeeds(text: string): Record<string, number> {
  const out: Record<string, number> = {};
  for (const part of text.split(";").map((p) => p.trim()).filter(Boolean)) {
    const [q, w] = part.split(":");
    if (q) out[q] = (out[q] ?? 0) + (w ? Number(w) || 1 : 1);
  }
  return out;
}

/** Both rankings of a case as CSV, every row the lenses returned (not only those shown), for a reader's own analysis. */
export function rankingCsv(q: string, textSystem: string, graphSystem: string, text: Reading[], graph: Reading[]): string {
  const cell = (v: string | number | null | undefined) => {
    const t = v == null ? "" : String(v);
    return /[",\n]/.test(t) ? `"${t.replace(/"/g, '""')}"` : t;
  };
  const head = ["query", "lens", "system", "rank", "doc_id", "title", "language", "source", "kind", "score"];
  const rows = [
    ...text.map((r) => ["text", textSystem, r] as const),
    ...graph.map((r) => ["graph", graphSystem, r] as const),
  ].map(([lens, system, r]) => [q, lens, system, r.rank, r.id, r.title, r.language, r.source, r.kind, r.score].map(cell).join(","));
  return [head.join(","), ...rows].join("\n") + "\n";
}
