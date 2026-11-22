"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { Load, MarginNote, Names, Stamp, fmt } from "@/components/ui";
import { api, get, type ImageRef } from "@/lib/api";
import { DOC_TYPES, LANGUAGES, LICENCES, SOURCES, plural } from "@/lib/names";
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
            </div>
            <aside>
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
