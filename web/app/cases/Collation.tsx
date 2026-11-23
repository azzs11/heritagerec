"use client";

import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

import type { Lens, Reading } from "./model";
import { ResultCard } from "./ResultCard";
import s from "./search.module.css";

interface Line {
  id: string;
  d: string;
}

/**
 * The two readings side by side, as a scholar collates two witnesses of a text: a line joins every document
 * both lenses found, and a document only one lens found stands alone. Ranks slide when either reading changes.
 */
export function Collation({
  text,
  graph,
  textHead,
  graphHead,
  onWorking,
  query,
}: {
  query?: string;
  text: Reading[];
  graph: Reading[];
  textHead: React.ReactNode;
  graphHead: React.ReactNode;
  onWorking: (lens: Lens, r: Reading) => void;
}) {
  const reduce = useReducedMotion();
  const [hover, setHover] = useState<string | null>(null);
  const [lines, setLines] = useState<Line[]>([]);
  const box = useRef<HTMLDivElement>(null);
  const spine = useRef<SVGSVGElement>(null);
  const cards = useRef(new Map<string, HTMLElement>());
  const textRank = new Map(text.map((r) => [r.id, r.rank]));
  const graphRank = new Map(graph.map((r) => [r.id, r.rank]));
  const shared = text.filter((r) => graphRank.has(r.id)).map((r) => r.id);
  const sharedKey = shared.join(",");

  const measure = useCallback(() => {
    const svg = spine.current;
    if (!svg) return;
    const sb = svg.getBoundingClientRect();
    const next: Line[] = [];
    for (const id of shared) {
      const a = cards.current.get(`text|${id}`)?.getBoundingClientRect();
      const b = cards.current.get(`graph|${id}`)?.getBoundingClientRect();
      if (!a || !b) continue;
      const y1 = a.top + Math.min(a.height / 2, 28) - sb.top;
      const y2 = b.top + Math.min(b.height / 2, 28) - sb.top;
      const w = sb.width;
      next.push({ id, d: `M 0 ${y1} C ${w * 0.5} ${y1}, ${w * 0.5} ${y2}, ${w} ${y2}` });
    }
    setLines(next);
    // `shared` is rebuilt on every render from the props; `sharedKey` says when it really changed.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sharedKey]);

  // Redraw while cards slide to their new places, then whenever the layout changes size.
  useLayoutEffect(() => {
    let frame = 0;
    const until = performance.now() + (reduce ? 0 : 520);
    const tick = () => {
      measure();
      if (performance.now() < until) frame = requestAnimationFrame(tick);
    };
    tick();
    return () => cancelAnimationFrame(frame);
  }, [measure, text, graph, reduce]);

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const ro = new ResizeObserver(() => measure());
    ro.observe(el);
    return () => ro.disconnect();
  }, [measure]);

  const column = (lens: Lens, items: Reading[], other: Map<string, number>) => {
    const top = Math.max(...items.map((r) => r.score), 0);
    return (
      <ol
        className={`${s.column} ${lens === "text" ? s.columnText : s.columnGraph}`}
        aria-label={lens === "text" ? "Text lens results" : "Graph lens results"}
      >
        {items.length === 0 ? (
          <li className={s.emptyLane}>{lens === "text" ? "No passage matched the question's words." : "The walk reached no document."}</li>
        ) : null}
        <AnimatePresence initial={false}>
          {items.map((r) => (
            <motion.li
              key={r.id}
              layout={!reduce}
              initial={reduce ? false : { opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={reduce ? { opacity: 0 } : { opacity: 0, x: lens === "text" ? -12 : 12 }}
              transition={{ duration: 0.32, ease: [0.2, 0.8, 0.2, 1] }}
            >
              <ResultCard
                ref={(el) => {
                  if (el) cards.current.set(`${lens}|${r.id}`, el);
                  else cards.current.delete(`${lens}|${r.id}`);
                }}
                r={r}
                lens={lens}
                top={top}
                counterpart={other.get(r.id) ?? null}
                dimmed={hover != null && hover !== r.id}
                lit={hover === r.id}
                onHover={setHover}
                onWorking={() => onWorking(lens, r)}
                query={query}
              />
            </motion.li>
          ))}
        </AnimatePresence>
      </ol>
    );
  };

  return (
    <div className={s.collation} ref={box}>
      <div className={`${s.colHead} ${s.colHeadText}`}>{textHead}</div>
      <div className={s.spineHead} aria-hidden />
      <div className={`${s.colHead} ${s.colHeadGraph}`}>{graphHead}</div>
      {column("text", text, graphRank)}
      <svg className={s.spine} ref={spine} aria-hidden>
        <defs>
          <linearGradient id="collate" gradientUnits="userSpaceOnUse" x1="0%" x2="100%" y1="0" y2="0">
            <stop offset="0" stopColor="var(--indigo)" />
            <stop offset="1" stopColor="var(--lac)" />
          </linearGradient>
        </defs>
        {lines.map((l) => (
          <path
            key={l.id}
            d={l.d}
            className={`${s.line} ${hover == null ? "" : hover === l.id ? s.lineLit : s.lineDim}`}
            stroke="url(#collate)"
          />
        ))}
      </svg>
      {column("graph", graph, textRank)}
    </div>
  );
}
