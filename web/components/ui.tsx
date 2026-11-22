"use client";

import { useId, useState, type ReactNode } from "react";

import type { Labels, Word } from "@/lib/api";
import type { Resource } from "@/lib/useResource";

import s from "./ui.module.css";

/** One meaning per colour: measured (verdigris), not built or failed check (turmeric), missing (turmeric, ruled). */
export function Seal({ kind, children }: { kind: "measured" | "pending" | "missing" | "text" | "graph"; children: ReactNode }) {
  return <span className={`${s.seal} ${s[`seal_${kind}`]}`}>{children}</span>;
}

/** What a reader sees when a part of the system is missing or not built: the reason and the fix, never a blank. */
export function MissingSlip({ part, reason, fix, title }: { part: string; reason: string; fix?: string; title?: string }) {
  return (
    <div className={s.slip} role="status">
      <div className={s.slipHead}>
        <Seal kind="pending">{title ?? "not available"}</Seal>
        <span className="mono">{part}</span>
      </div>
      <p className={s.slipReason}>{reason}</p>
      {fix ? (
        <p className={s.slipFix}>
          <span className="label">to fix</span> <code>{fix}</code>
        </p>
      ) : null}
    </div>
  );
}

/** Renders loading, missing, refused and failed states the same way on every page. */
export function Load<T>({ res, children, what }: { res: Resource<T>; children: (data: T) => ReactNode; what: string }) {
  switch (res.state) {
    case "loading":
      return (
        <p className={s.loading} aria-live="polite">
          <span className={s.loadingMark} aria-hidden /> Reading {what}…
        </p>
      );
    case "unavailable":
      return <MissingSlip part={res.error.part} reason={res.error.reason} fix={res.error.fix} />;
    case "refused":
      return (
        <p className={s.refused} role="alert">
          <Seal kind="pending">refused</Seal> {res.error.message}
        </p>
      );
    case "failed":
      return (
        <p className={s.refused} role="alert">
          <Seal kind="pending">error</Seal> {res.error.message}
        </p>
      );
    case "ready":
      return <>{children(res.data)}</>;
  }
}

/** "What am I looking at?": a plain-language note beside a panel, open on request. */
export function MarginNote({ title = "What am I looking at?", children }: { title?: string; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  return (
    <div className={s.note}>
      <button className={s.noteButton} aria-expanded={open} aria-controls={id} onClick={() => setOpen(!open)}>
        <span aria-hidden>{open ? "–" : "?"}</span> {title}
      </button>
      <div id={id} hidden={!open} className={s.noteBody}>
        {children}
      </div>
    </div>
  );
}

/** A name in each script the record has, side by side, none ranked above the others. */
export function Names({ labels, fallback, size = "inline" }: { labels: Labels; fallback: string; size?: "inline" | "title" }) {
  const parts = (["en", "hi", "kn"] as const).filter((l) => labels[l]);
  if (!parts.length) return <span className="mono">{fallback}</span>;
  return (
    <span className={size === "title" ? s.namesTitle : s.names}>
      {parts.map((l, i) => (
        <span key={l} lang={l} className={i ? s.nameOther : undefined}>
          {labels[l]}
        </span>
      ))}
    </span>
  );
}

/** Where a thing comes from: source, licence, revision or checksum, in a stamp. */
export function Stamp({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <dl className={s.stamp}>
      {rows.map(([k, v]) => (
        <div key={k}>
          <dt className="label">{k}</dt>
          <dd>{v}</dd>
        </div>
      ))}
    </dl>
  );
}

/** A passage with the words the query matched marked in ink, the way a reader would mark a page. */
export function Evidence({ words, lang }: { words: Word[]; lang?: string }) {
  return (
    <p className={s.evidence} lang={lang}>
      {words.map((w, i) => (
        <span key={i}>
          {w.match ? <mark className={s.mark}>{w.word}</mark> : w.word}{" "}
        </span>
      ))}
      <span className={s.ellipsis} aria-hidden>
        …
      </span>
    </p>
  );
}

/** A number with the file it was read from, so every figure can be traced. */
export function Figure({ value, caption, source }: { value: ReactNode; caption: ReactNode; source: string }) {
  return (
    <figure className={s.figure}>
      <div className={`${s.figureValue} num`}>{value}</div>
      <figcaption>
        {caption}
        <span className={s.figureSource}>
          from <code>{source}</code>
        </span>
      </figcaption>
    </figure>
  );
}

export function fmt(n: number, digits = 0): string {
  return n.toLocaleString("en-IN", { maximumFractionDigits: digits, minimumFractionDigits: digits });
}
