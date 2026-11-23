"use client";

import * as Dialog from "@radix-ui/react-dialog";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState } from "react";

import { Load, MarginNote, Names, Stamp, fmt } from "@/components/ui";
import { HexRings } from "@/components/HexRings";
import { LiveGraph, groupOf, type LiveEdge, type LiveNode } from "@/components/LiveGraph";
import { NextSteps } from "@/components/Wayfinding";
import { api, downloadUrl, get, label, type DocumentView as Doc, type ImageRef } from "@/lib/api";
import { bibtex, plainCitation } from "@/lib/cite";
import { DOC_TYPES, LANGUAGES, LICENCES, SOURCES, plural } from "@/lib/names";
import { useTrailStep } from "@/lib/trail";
import { useResource } from "@/lib/useResource";

import s from "./document.module.css";

interface PassagePage {
  doc_id: string;
  total: number;
  offset: number;
  passages: { id: string; contents: string }[];
}

const PAGE = 6;

export default function DocumentPage() {
  return (
    <Suspense fallback={<p className="page">Opening the document…</p>}>
      <DocumentView />
    </Suspense>
  );
}

function DocumentView() {
  const params = useSearchParams();
  const id = params.get("id") ?? "";
  const asked = params.get("q") ?? "";
  const doc = useResource(id ? () => api.document(id) : null, `doc|${id}`);
  useTrailStep(doc.state === "ready" ? { kind: "document", label: doc.data.title, href: `/document/?id=${encodeURIComponent(id)}` } : null);
  if (!id) return <p className="page">No document was named. Open one from a case or the graph.</p>;
  return (
    <article className="page">
      <Load res={doc} what="the record">
        {(d) => (
          <div className="folio">
            <div>
              <p className={s.meta}>
                {DOC_TYPES[d.doc_type] ?? d.doc_type} · {SOURCES[d.source] ?? d.source}
              </p>
              <h1 className={s.title} lang={d.language}>
                {d.title}
              </h1>
              {d.image ? <ObjectImage image={d.image} title={d.title} fallback={d.url} /> : null}
              <Stamp
                rows={[
                  ["language", LANGUAGES[d.language] ?? d.language],
                  [
                    "period",
                    d.period_start != null ? `${d.period_start}${d.period_end != null && d.period_end !== d.period_start ? `–${d.period_end}` : ""}` : "not recorded",
                  ],
                  ["length", `${fmt(d.words)} ${plural(d.words, "word", "words")}, ${fmt(d.passages)} ${plural(d.passages, "passage", "passages")}`],
                  [
                    "licence",
                    <a key="l" href={d.licence} rel="noreferrer">
                      {LICENCES[d.licence] ?? d.licence.replace(/^https?:\/\//, "")}
                    </a>,
                  ],
                  [
                    "source",
                    <a key="u" href={d.url} rel="noreferrer">
                      original page
                    </a>,
                  ],
                  ["fetched", d.fetched_at.slice(0, 10)],
                  ["checksum", <code key="c">{d.sha256.slice(0, 16)}…</code>],
                  ["record id", <code key="i">{d.id}</code>],
                ]}
              />
              <h2 className={s.h2}>What the graph says it is about</h2>
              {d.entities.length ? (
                <ul className={s.entities}>
                  {d.entities.map((e) => (
                    <li key={e.id}>
                      <Link href={`/graph/?node=${encodeURIComponent(e.id)}`}>
                        <Names labels={e.labels} fallback={e.id} />
                      </Link>
                      {e.type ? <span className={s.etype}>{e.type}</span> : null}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className={s.muted}>No entity is linked to this record.</p>
              )}
              {d.in_graph ? (
                <p>
                  <Link href={`/graph/?node=${encodeURIComponent(d.id)}`}>See this document in the graph →</Link>
                </p>
              ) : null}
              <h2 className={s.h2}>The text, as the search engines see it</h2>
              <Passages id={d.id} lang={d.language} asked={asked} />
              {d.in_graph ? <InGraph d={d} /> : null}
              <NextSteps steps={nextSteps(d)} />
            </div>
            <aside className={s.side}>
              <TakeIt d={d} />
              <MarginNote>
                <p>
                  Every document is split into passages of 150 words that overlap by half, each starting with the title.
                  Keyword and neural systems all read these same passages, and a document scores as its best one.
                </p>
                <p>The checksum is of the record as collected; the source page may have changed since.</p>
              </MarginNote>
            </aside>
          </div>
        )}
      </Load>
    </article>
  );
}

/**
 * Marks the words of the reader's search in a passage. Matching is by spelling (a word is marked when it begins with
 * the first five letters of a search word), not by the search engine's stems, and the page says so.
 */
function marked(text: string, words: string[]) {
  if (!words.length) return text;
  const stems = words.map((w) => w.toLocaleLowerCase().slice(0, 5));
  return text.split(/(\s+)/).map((tok, i) => {
    const bare = tok.toLocaleLowerCase().replace(/[^\p{L}\p{M}\p{N}]/gu, "");
    return bare && stems.some((st) => bare.startsWith(st)) ? <mark key={i}>{tok}</mark> : tok;
  });
}

function Passages({ id, lang, asked }: { id: string; lang: string; asked: string }) {
  const words = asked.split(/\s+/).filter((w) => w.length >= 3);
  const [offset, setOffset] = useState(0);
  const page = useResource(
    () => get<PassagePage>(`/api/documents/${encodeURIComponent(id)}/passages`, { offset, limit: PAGE }),
    `p|${id}|${offset}`,
  );
  return (
    <Load res={page} what="the passages">
      {(p) => (
        <>
          {words.length ? (
            <p className={s.askedNote}>
              Words of your search, <q>{asked}</q>, are marked by spelling.
            </p>
          ) : null}
          <ol className={s.passages} start={p.offset + 1}>
            {p.passages.map((x) => (
              <li key={x.id} lang={lang}>
                <span className={s.pid}>#{x.id.split("#").pop()}</span>
                {marked(x.contents.split("\n").slice(1).join(" ") || x.contents, words)}
              </li>
            ))}
          </ol>
          <nav className={s.pager} aria-label="Passages">
            <button disabled={p.offset === 0} onClick={() => setOffset(Math.max(0, p.offset - PAGE))}>
              ← earlier
            </button>
            <span className="num">
              {fmt(p.offset + 1)}–{fmt(Math.min(p.total, p.offset + PAGE))} of {fmt(p.total)}
            </span>
            <button disabled={p.offset + PAGE >= p.total} onClick={() => setOffset(p.offset + PAGE)}>
              later →
            </button>
          </nav>
        </>
      )}
    </Load>
  );
}

function ObjectImage({ image, title, fallback }: { image: ImageRef; title: string; fallback: string }) {
  const [failed, setFailed] = useState(false);
  const page = image.page ?? fallback;
  return (
    <figure className={s.figure}>
      {failed ? (
        <p className={s.noImage}>
          The museum&apos;s server did not send the image. <a href={page}>See the object on the museum&apos;s site</a>.
        </p>
      ) : (
        <Dialog.Root>
          <Dialog.Trigger asChild>
            <button className={s.zoomable} aria-label={`Open ${title} full size`}>
              {/* Remote museum image in a static site: next/image's optimiser is not available here. */}
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={image.thumb}
                alt={title}
                referrerPolicy="no-referrer"
                width={image.width ?? undefined}
                height={image.height ?? undefined}
                onError={() => setFailed(true)}
              />
              <span className={s.zoomHint} aria-hidden>
                ⤢ full size
              </span>
            </button>
          </Dialog.Trigger>
          <Dialog.Portal>
            <Dialog.Overlay className={s.lightboxBack} />
            <Dialog.Content className={s.lightbox} aria-describedby={undefined}>
              <Dialog.Title className="visually-hidden">{title}</Dialog.Title>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={image.full} alt={title} referrerPolicy="no-referrer" />
              <p>
                {image.credit} ·{" "}
                <a href={page} target="_blank" rel="noreferrer">
                  at the museum ↗
                </a>
              </p>
              <Dialog.Close className={s.lightboxClose} aria-label="Close">
                ×
              </Dialog.Close>
            </Dialog.Content>
          </Dialog.Portal>
        </Dialog.Root>
      )}
      <figcaption>
        {image.credit}. Open licence:{" "}
        <a href={image.licence} rel="noreferrer">
          CC0
        </a>
        .
      </figcaption>
    </figure>
  );
}

/** Downloads and the original at its source: everything a reader needs to keep or cite the document. */
function TakeIt({ d }: { d: Doc }) {
  return (
    <section className={s.take} aria-label="Take it with you">
      <h2 className={s.takeTitle}>Take it with you</h2>
      <a className={s.dl} href={downloadUrl(d.id, "txt")} download>
        <span>Text</span>
        <small>.txt, with source and licence</small>
      </a>
      <a className={s.dl} href={downloadUrl(d.id, "json")} download>
        <span>Record</span>
        <small>.json, every field</small>
      </a>
      <ul className={s.getIt}>
        {d.get_it.map((x) => (
          <li key={x.url}>
            <a href={x.url} target="_blank" rel="noreferrer">
              {x.label} <span aria-hidden>↗</span>
            </a>
          </li>
        ))}
      </ul>
      <Cite d={d} />
      <p className={s.licenceNote}>
        {LICENCES[d.licence] ?? "Open licence"}
        {d.licence.includes("/by") ? ": keep the source and licence with any copy." : ": free to use."}
      </p>
    </section>
  );
}

/** A citation to copy, plain or BibTeX: built from the record, with the snapshot record id (lib/cite.ts). */
function Cite({ d }: { d: Doc }) {
  const [copied, setCopied] = useState<string | null>(null);
  const forms = [
    { name: "Plain", text: plainCitation(d) },
    { name: "BibTeX", text: bibtex(d) },
  ];
  const copy = async (name: string, text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(name);
    } catch {
      setCopied(null); // no clipboard (an insecure page): the text stays selectable in the box
    }
  };
  return (
    <details className={s.cite}>
      <summary>Cite it</summary>
      {forms.map((f) => (
        <div key={f.name} className={s.citeForm}>
          <div className={s.citeHead}>
            <span>{f.name}</span>
            <button type="button" onClick={() => copy(f.name, f.text)}>
              {copied === f.name ? "Copied" : "Copy"}
            </button>
          </div>
          <textarea readOnly value={f.text} rows={f.name === "BibTeX" ? 7 : 4} aria-label={`${f.name} citation`} onFocus={(e) => e.currentTarget.select()} />
        </div>
      ))}
    </details>
  );
}

function nextSteps(d: Doc) {
  const ents = d.entities.filter((e) => e.kind !== "document");
  const placed = ents.find((e) => e.lat != null);
  const steps: { label: string; href: string; hint?: string }[] = [];
  if (ents.length) {
    steps.push({
      label: "More like this",
      href: `/cases/?q=${encodeURIComponent(d.title)}&seeds=${encodeURIComponent(ents.map((e) => e.id).join(";"))}`,
      hint: "both lenses, starting from what it is about",
    });
    steps.push({ label: `${label(ents[0]!.labels, ents[0]!.id)} in the graph`, href: `/graph/?node=${encodeURIComponent(ents[0]!.id)}`, hint: "its facts and neighbours" });
  }
  if (placed) steps.push({ label: "On the atlas", href: `/atlas/?lat=${placed.lat}&lon=${placed.lon}`, hint: `around ${label(placed.labels, placed.id)}` });
  if (!steps.length) steps.push({ label: "Search for it", href: `/cases/?q=${encodeURIComponent(d.title)}`, hint: "what the lenses find for its title" });
  return steps;
}

/** Where the document sits in the graph, and the documents a walk from its entities reaches first. */
function InGraph({ d }: { d: Doc }) {
  const ego = useResource(() => api.ego(d.id, 40, undefined, 2), `docego|${d.id}`);
  const ents = d.entities.filter((e) => e.kind !== "document").map((e) => e.id);
  const close = useResource(ents.length ? () => api.rank(ents.join(";"), 1, 0.15, 8) : null, `close|${ents.join(";")}`);
  const picture = useMemo(() => {
    if (ego.state !== "ready") return null;
    const v = ego.data;
    const nodes: LiveNode[] = v.nodes.map((n) => ({
      id: n.id,
      label: label(n.labels, n.id),
      group: groupOf(n.kind, n.type),
      size: n.id === d.id ? 12 : n.kind === "document" ? (n.image ? 6 : 3.5) : 4 + Math.min(6, Math.sqrt(n.degree)),
      hub: n.hub || n.id === d.id,
      image: n.kind === "document" ? n.image : undefined,
    }));
    const pairs = new Map<string, LiveEdge>();
    for (const e of v.edges) {
      const k = e.source < e.target ? `${e.source}|${e.target}` : `${e.target}|${e.source}`;
      pairs.set(k, { id: k, source: e.source, target: e.target, label: e.relation_label });
    }
    return { nodes, edges: [...pairs.values()] };
  }, [ego, d.id]);
  const closeDocs = close.state === "ready" ? close.data.results.filter((x) => x.document.id !== d.id).slice(0, 6) : [];
  return (
    <section className={s.inGraph}>
      <h2 className={s.h2}>In the graph</h2>
      {picture && picture.nodes.length > 1 ? (
        <div className={s.miniGraph}>
          <LiveGraph nodes={picture.nodes} edges={picture.edges} selected={d.id} onSelect={() => {}} focusOnSelect={false} ariaLabel={`${d.title} and its neighbours in the graph`} />
          <Link className={s.openGraph} href={`/graph/?node=${encodeURIComponent(d.id)}`}>
            Open in the graph →
          </Link>
        </div>
      ) : null}
      {closeDocs.length ? (
        <>
          <h3 className={s.h3}>Close in the graph</h3>
          <p className={s.muted}>
            Documents a walk from what this one is about reaches first (personalised PageRank). Not yet the recommender,
            which comes later.
          </p>
          <ul className={s.close}>
            {closeDocs.map((x) => (
              <li key={x.document.id}>
                <Link href={`/document/?id=${encodeURIComponent(x.document.id)}`}>
                  {x.document.image ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={x.document.image.thumb} alt="" loading="lazy" referrerPolicy="no-referrer" onError={(e) => (e.currentTarget.style.display = "none")} />
                  ) : (
                    <span className={s.closeMark} aria-hidden>
                      {x.document.id.startsWith("wikipedia:hi") ? "हि" : x.document.id.startsWith("wikipedia:kn") ? "ಕ" : "En"}
                    </span>
                  )}
                  <span>{label(x.document.labels, x.document.id)}</span>
                </Link>
              </li>
            ))}
          </ul>
        </>
      ) : null}
      <NearbyRings id={d.id} />
    </section>
  );
}

/** Concentric recommendations (decision 0030): documents about places in this one's hexagon, then each ring out. */
function NearbyRings({ id }: { id: string }) {
  const r = useResource(() => api.documentRings(id, 2), `docrings|${id}`);
  if (r.state !== "ready" || !r.data.rings.length) return null;
  const from = (r.data.places ?? []).map((p) => label(p.labels, p.id)).join(", ");
  return (
    <HexRings
      title={<>Nearby, ring by ring{from ? <span className={s.muted}> · from {from}</span> : null}</>}
      unit="documents"
      bands={r.data.rings.map((b) => ({
        ring: b.ring,
        total: b.total,
        items: (b.documents ?? []).slice(0, 5).map((x) => (
          <Link key={x.id} className={s.ringChip} href={`/document/?id=${encodeURIComponent(x.id)}`} title={`about ${label(x.place.labels, x.place.id)}`}>
            {label(x.labels, x.id)}
          </Link>
        )),
      }))}
    />
  );
}
