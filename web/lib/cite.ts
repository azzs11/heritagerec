// Ready-made citations for a document: a reader (a student, a researcher) should not have to assemble one by hand.
// Everything comes from the record; the snapshot record id is added so the citation points at the exact text used.

import type { DocumentView } from "./api";
import { LICENCES, SOURCES } from "./names";

type Citable = Pick<DocumentView, "id" | "title" | "source" | "url" | "licence" | "fetched_at" | "language">;

const WIKI_EDITION: Record<string, string> = { en: "English Wikipedia", hi: "Hindi Wikipedia", kn: "Kannada Wikipedia" };

function publisher(d: Citable): string {
  if (d.source === "wikipedia") return WIKI_EDITION[d.language] ?? "Wikipedia";
  return SOURCES[d.source] ?? d.source;
}

function licenceName(d: Citable): string {
  return LICENCES[d.licence] ?? d.licence;
}

/** The date the record was fetched, as YYYY-MM-DD: the "retrieved" date of the text the study used. */
function retrieved(d: Citable): string {
  return d.fetched_at.slice(0, 10);
}

export function plainCitation(d: Citable): string {
  // Wikipedia articles have no single author; "Wikipedia contributors" is the usual credit.
  const author = d.source === "wikipedia" ? "Wikipedia contributors. " : "";
  return (
    `${author}“${d.title}.” ${publisher(d)}. ${d.url} (retrieved ${retrieved(d)}; ${licenceName(d)}). ` +
    `Text as in the HeritageRec corpus v1, record ${d.id}.`
  );
}

/** BibTeX braces protect capitals and special characters; a key is built from the record id. */
export function bibtex(d: Citable): string {
  const key = `heritagerec_${d.id.replace(/[^A-Za-z0-9]+/g, "_")}`;
  const esc = (t: string) => t.replace(/([{}\\&%$#_])/g, "\\$1");
  const lines = [
    `@misc{${key},`,
    d.source === "wikipedia" ? `  author = {{Wikipedia contributors}},` : null,
    `  title = {{${esc(d.title)}}},`,
    `  howpublished = {${esc(publisher(d))}},`,
    `  url = {${d.url}},`,
    `  urldate = {${retrieved(d)}},`,
    `  note = {${esc(licenceName(d))}. Text as in the HeritageRec corpus v1, record ${esc(d.id)}},`,
    `}`,
  ];
  return lines.filter(Boolean).join("\n");
}
