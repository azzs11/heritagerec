"use client";

import * as Dialog from "@radix-ui/react-dialog";
import Link from "next/link";
import { motion, useReducedMotion } from "motion/react";

import { Evidence, Load, fmt } from "@/components/ui";
import { api, label, stepLabel, type Explanation } from "@/lib/api";
import { useResource } from "@/lib/useResource";

import type { Lens, Reading } from "./model";
import s from "./search.module.css";

/** Why a document is where it is, for either lens, in a drawer that keeps the results in view. */
export function WorkingDrawer({
  open,
  onClose,
  lens,
  r,
  q,
  system,
  lang,
  settings,
}: {
  open: boolean;
  onClose: () => void;
  lens: Lens;
  r: Reading | null;
  q: string;
  system: string;
  lang?: string;
  settings: { restart: number; hub: number; seeds: string[] };
}) {
  return (
    <Dialog.Root open={open} onOpenChange={(o) => !o && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className={s.overlay} />
        <Dialog.Content className={s.drawer} aria-describedby={undefined}>
          <div className={s.drawerHead}>
            <Dialog.Title className={s.drawerTitle}>
              <span className={lens === "text" ? s.tagText : s.tagGraph}>{lens === "text" ? "text lens" : "graph lens"}</span>
              {r ? ` #${r.rank} · ${r.title}` : ""}
            </Dialog.Title>
            <Dialog.Close className={s.close} aria-label="Close">
              ×
            </Dialog.Close>
          </div>
          {r && lens === "text" ? <TextWorking q={q} doc={r.id} system={system} lang={lang} /> : null}
          {r && lens === "graph" ? <GraphWorking r={r} settings={settings} /> : null}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function TextWorking({ q, doc, system, lang }: { q: string; doc: string; system: string; lang?: string }) {
  const res = useResource(() => api.explain(q, doc, system, lang), `ex|${q}|${doc}|${system}|${lang}`);
  return (
    <Load res={res} what="the working">
      {(e) => <TextBody e={e} />}
    </Load>
  );
}

function TextBody({ e }: { e: Explanation }) {
  const reduce = useReducedMotion();
  if (!e.winner) return <p>{e.note}</p>;
  const w = e.winner;
  const max = Math.max(...w.terms.map((t) => Math.abs(t.contribution)), 1e-9);
  const rm3 = e.system === "bm25_rm3";
  return (
    <div className={s.working}>
      <p className={s.lead}>
        Its best passage scored <b className="num">{w.score.toFixed(3)}</b>. That score is a sum, one part per{" "}
        {rm3 ? "word of the expanded query" : "word of the query"}:
      </p>
      <ol className={s.terms}>
        {w.terms.map((t, i) => (
          <li key={t.term}>
            <code>{t.term}</code>
            <span className={s.termTrack}>
              <motion.i
                initial={reduce ? false : { width: 0 }}
                animate={{ width: `${(100 * Math.abs(t.contribution)) / max}%` }}
                transition={{ duration: 0.45, delay: reduce ? 0 : 0.06 * i, ease: [0.2, 0.8, 0.2, 1] }}
              />
            </span>
            <span className="num">{t.contribution.toFixed(3)}</span>
            <span className={s.termNote}>
              {rm3 ? `weight ${t.multiplier.toFixed(3)} × ` : t.multiplier > 1 ? `${t.multiplier} × ` : ""}BM25{" "}
              {t.bm25_weight.toFixed(3)}
            </span>
          </li>
        ))}
      </ol>
      <p className={s.check}>
        <Tick ok={w.check.matches} />
        {w.check.matches ? "Adds up: " : "Does not add up: "}the parts sum to{" "}
        <span className="num">{w.check.recomputed.toFixed(4)}</span>, the search engine returned{" "}
        <span className="num">{w.check.lucene.toFixed(4)}</span>.
      </p>
      <h3 className={s.drawerH}>Which passage counted</h3>
      <p className={s.muted}>
        <span className="num">{fmt(e.passages_retrieved.length)}</span> of the document&apos;s{" "}
        <span className="num">{fmt(e.passages_in_document ?? 0)}</span> passages were candidates; the best one sets its
        rank (<span className="num">#{e.rank}</span>).
      </p>
      <ol className={s.passageRail}>
        {e.passages_retrieved.slice(0, 12).map((p, i) => (
          <li key={p.passage} className={i === 0 ? s.best : undefined} title={`passage ${p.passage.split("#").pop()}`}>
            <i style={{ height: `${Math.max(8, (100 * p.score) / (e.passages_retrieved[0]?.score || 1))}%` }} />
          </li>
        ))}
      </ol>
      {w.text ? <Evidence words={w.text} lang={e.language} /> : null}
    </div>
  );
}

function GraphWorking({ r, settings }: { r: Reading; settings: { restart: number; hub: number; seeds: string[] } }) {
  const p = r.path?.paths[0];
  return (
    <div className={s.working}>
      <p className={s.lead}>
        A walk starting from the linked entities spent <b className="num">{(100 * r.score).toFixed(2)}%</b> of its time
        on this document. It restarts with probability <span className="num">{settings.restart}</span>; hubs are
        weighted by{" "}
        {settings.hub === 0 ? "nothing (no down-weighting)" : settings.hub === 1 ? "1 / degree" : `degree^-${settings.hub}`}.
      </p>
      {p ? (
        <>
          <h3 className={s.drawerH}>The shortest chain of facts from a starting point</h3>
          <ol className={s.pathRail}>
            {p.nodes.map((n, i) => (
              <li key={n.id}>
                {i && p.edges[i - 1] ? <span className={s.fact}>{stepLabel(p.edges[i - 1]!, p.nodes[i - 1]!.id)}</span> : null}
                <Link href={`/graph/?node=${encodeURIComponent(n.id)}`} className={s.node}>
                  {label(n.labels, n.id)}
                </Link>
              </li>
            ))}
          </ol>
          {r.path?.through_hubs ? <p className={s.muted}>This chain passes through a hub, so it says little on its own.</p> : null}
        </>
      ) : (
        <p className={s.muted}>No chain of four facts or fewer reaches it from a starting point.</p>
      )}
    </div>
  );
}

/** A check mark drawn as a stroke, or a cross for a failed check. */
function Tick({ ok }: { ok: boolean }) {
  const reduce = useReducedMotion();
  return (
    <svg className={ok ? s.tickOk : s.tickBad} viewBox="0 0 16 16" width="16" height="16" aria-hidden>
      <motion.path
        d={ok ? "M3 8.5 L6.5 12 L13 4" : "M4 4 L12 12 M12 4 L4 12"}
        fill="none"
        strokeWidth="2"
        strokeLinecap="round"
        initial={reduce ? false : { pathLength: 0 }}
        animate={{ pathLength: 1 }}
        transition={{ duration: 0.4, delay: reduce ? 0 : 0.3 }}
      />
    </svg>
  );
}
