"use client";

import Link from "next/link";
import { forwardRef, useState } from "react";

import { Portrait } from "@/components/Portrait";
import { label, stepLabel } from "@/lib/api";
import { DOC_TYPES, SOURCES } from "@/lib/names";

import type { Lens, Reading } from "./model";
import s from "./search.module.css";


/** One document as one lens read it: where it ranks, what it is, and the evidence for it. */
export const ResultCard = forwardRef<
  HTMLElement,
  {
    r: Reading;
    lens: Lens;
    top: number;
    counterpart: number | null;
    dimmed: boolean;
    lit: boolean;
    onHover: (id: string | null) => void;
    onWorking: () => void;
    query?: string;
  }
>(function ResultCard({ r, lens, top, counterpart, dimmed, lit, onHover, onWorking, query }, ref) {
  const [imageFailed, setImageFailed] = useState(false);
  const p = r.path?.paths[0];
  return (
    <article
      ref={ref}
      className={`${s.card} ${s[`card_${lens}`]} ${dimmed ? s.dimmed : ""} ${lit ? s.lit : ""}`}
      onMouseEnter={() => onHover(r.id)}
      onMouseLeave={() => onHover(null)}
      onFocus={() => onHover(r.id)}
      onBlur={() => onHover(null)}
      tabIndex={-1}
      data-doc={r.id}
      aria-label={`${lens === "text" ? "Text" : "Graph"} lens, rank ${r.rank}: ${r.title}`}
    >
      <span className={`${s.rank} num`}>{r.rank}</span>
      <div className={s.thumb} aria-hidden>
        {r.image && !imageFailed ? (
          // A Commons photograph shows an entity, so its title says which one and credits its author (decision 0034).
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={r.image.thumb}
            alt=""
            title={r.image.of ? `Photo of ${label(r.image.of_labels ?? {}, r.image.of)}. ${r.image.credit}` : r.image.credit}
            loading="lazy"
            referrerPolicy="no-referrer"
            onError={() => setImageFailed(true)}
          />
        ) : (
          <Portrait data={r.portrait} language={r.language} />
        )}
      </div>
      <div className={s.body}>
        <Link href={`/document/?id=${encodeURIComponent(r.id)}${query ? `&q=${encodeURIComponent(query)}` : ""}`} className={s.cardTitle} lang={r.language}>
          {r.title}
        </Link>
        <p className={s.meta}>
          {DOC_TYPES[r.kind ?? ""] ?? r.kind ?? "document"} · {SOURCES[r.source] ?? r.source}
          {counterpart != null ? (
            <span className={s.both}>
              {" "}
              · also {lens === "text" ? "graph" : "text"} #{counterpart}
            </span>
          ) : (
            <span className={s.only}> · only this lens</span>
          )}
        </p>
        {r.snippet ? (
          <p className={s.snippet} lang={r.language}>
            {r.snippet.map((w, i) => (
              <span key={i}>{w.match ? <mark>{w.word}</mark> : w.word} </span>
            ))}
          </p>
        ) : null}
        {p ? (
          <p className={s.chain}>
            {p.nodes.map((n, i) => (
              <span key={n.id}>
                {i && p.edges[i - 1] ? <em>{stepLabel(p.edges[i - 1]!, p.nodes[i - 1]!.id)}</em> : null}
                <b>{label(n.labels, n.id)}</b>
              </span>
            ))}
          </p>
        ) : null}
        <div className={s.foot}>
          <span className={s.bar} aria-hidden>
            <i style={{ width: `${Math.max(3, (100 * r.score) / (top || 1))}%` }} />
          </span>
          <button className={s.why} onClick={onWorking}>
            Working
          </button>
        </div>
      </div>
    </article>
  );
});
