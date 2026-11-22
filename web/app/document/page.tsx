"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { Load, MarginNote, Names, Stamp, fmt } from "@/components/ui";
import { NextSteps } from "@/components/Wayfinding";
import { api, downloadUrl, get, label, type DocumentView as Doc, type ImageRef } from "@/lib/api";
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
  const id = useSearchParams().get("id") ?? "";
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
              <Passages id={d.id} lang={d.language} />
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

function Passages({ id, lang }: { id: string; lang: string }) {
  const [offset, setOffset] = useState(0);
  const page = useResource(
    () => get<PassagePage>(`/api/documents/${encodeURIComponent(id)}/passages`, { offset, limit: PAGE }),
    `p|${id}|${offset}`,
  );
  return (
    <Load res={page} what="the passages">
      {(p) => (
        <>
          <ol className={s.passages} start={p.offset + 1}>
            {p.passages.map((x) => (
              <li key={x.id} lang={lang}>
                <span className={s.pid}>#{x.id.split("#").pop()}</span>
                {x.contents.split("\n").slice(1).join(" ") || x.contents}
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
        <a href={page} rel="noreferrer">
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
        </a>
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
      <p className={s.licenceNote}>
        {LICENCES[d.licence] ?? "Open licence"}
        {d.licence.includes("/by") ? ": keep the source and licence with any copy." : ": free to use."}
      </p>
    </section>
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
