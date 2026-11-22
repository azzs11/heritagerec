"use client";

import Link from "next/link";
import type { ReactNode } from "react";

import type { Route } from "@/lib/elsewhere";
import { useTrail, type Step } from "@/lib/trail";

import s from "./Wayfinding.module.css";

const GLYPH: Record<Step["kind"], string> = { search: "⌕", document: "▤", entity: "◆", place: "●" };
const KIND: Record<Step["kind"], string> = { search: "search", document: "document", entity: "entity", place: "place" };

/** The reader's own path through the archive, drawn like a path in the graph; any step leads back. */
export function Trail() {
  const [steps, clear] = useTrail();
  if (steps.length < 2) return null;
  return (
    <nav className={s.trail} aria-label="Your path through the archive">
      <span className={s.trailName}>your path</span>
      <ol>
        {steps.map((x, i) => (
          <li key={`${x.href}|${i}`}>
            <Link href={x.href} title={`${KIND[x.kind]}: ${x.label}`} aria-current={i === steps.length - 1 ? "step" : undefined}>
              <span className={`${s.glyph} ${s[`g_${x.kind}`]}`} aria-hidden>
                {GLYPH[x.kind]}
              </span>
              <span className={s.stepLabel}>{x.label}</span>
            </Link>
          </li>
        ))}
      </ol>
      <button className={s.clear} onClick={clear}>
        clear
      </button>
    </nav>
  );
}

/** Every "nothing here", "not found" and "something failed" moment, in one voice: what, why, what next. */
export function Notice({
  tone = "empty",
  title,
  children,
  actions,
}: {
  tone?: "empty" | "partial" | "error";
  title: ReactNode;
  children?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <section className={`${s.notice} ${s[`n_${tone}`]}`} role={tone === "error" ? "alert" : "status"}>
      <h2 className={s.noticeTitle}>{title}</h2>
      {children ? <div className={s.noticeBody}>{children}</div> : null}
      {actions ? <div className={s.actions}>{actions}</div> : null}
    </section>
  );
}

/** Where else to look, as plain links with a reason each. */
export function Elsewhere({ routes, title = "Search the same words elsewhere" }: { routes: Route[]; title?: string }) {
  return (
    <div className={s.elsewhere}>
      <h3 className={s.small}>{title}</h3>
      <ul>
        {routes.map((r) => (
          <li key={r.name}>
            <a href={r.url} target="_blank" rel="noreferrer">
              {r.name} <span aria-hidden>↗</span>
            </a>
            <span className={s.why}>{r.why}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Where to go from here: the next steps a page offers, so no page is a dead end. */
export function NextSteps({ steps, title = "From here" }: { steps: { label: ReactNode; href: string; hint?: ReactNode }[]; title?: string }) {
  if (!steps.length) return null;
  return (
    <nav className={s.next} aria-label={title}>
      <h3 className={s.small}>{title}</h3>
      <ul>
        {steps.map((x) => (
          <li key={x.href}>
            <Link href={x.href}>
              <span className={s.nextLabel}>{x.label}</span>
              {x.hint ? <span className={s.why}>{x.hint}</span> : null}
              <span className={s.arrow} aria-hidden>
                →
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
