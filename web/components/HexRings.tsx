"use client";

import { motion } from "motion/react";
import type { ReactNode } from "react";

import s from "./HexRings.module.css";

// Axial coordinates of the hexagons within two rings of the centre: 1 + 6 + 12.
function ringCells(r: number): [number, number][] {
  if (r === 0) return [[0, 0]];
  const dirs: [number, number][] = [
    [1, 0],
    [1, -1],
    [0, -1],
    [-1, 0],
    [-1, 1],
    [0, 1],
  ];
  const out: [number, number][] = [];
  let q = -r;
  let rr = r;
  for (const [dq, dr] of dirs) {
    for (let i = 0; i < r; i++) {
      out.push([q, rr]);
      q += dq;
      rr += dr;
    }
  }
  return out;
}

function hexPath(cx: number, cy: number, size: number) {
  const pts = Array.from({ length: 6 }, (_, i) => {
    const a = (Math.PI / 3) * i + Math.PI / 6;
    return `${(cx + size * Math.cos(a)).toFixed(1)},${(cy + size * Math.sin(a)).toFixed(1)}`;
  });
  return `M${pts.join("L")}Z`;
}

/**
 * Nearness as concentric rings of hexagons (Uber's H3, decision 0030): the centre cell, the six around it, the twelve
 * beyond. Each ring is shaded by how much it holds, and its contents are listed beside it.
 */
export function HexRings({
  bands,
  unit,
  title,
}: {
  bands: { ring: number; total: number; items: ReactNode[] }[];
  unit: string;
  title: ReactNode;
}) {
  const max = Math.max(1, ...bands.map((b) => b.total));
  const size = 13;
  return (
    <section className={s.wrap}>
      <h3 className={s.title}>{title}</h3>
      <div className={s.body}>
        <svg viewBox="-80 -72 160 144" className={s.diagram} aria-hidden>
          {bands.map((b) =>
            ringCells(b.ring).map(([q, r], i) => {
              const x = size * Math.sqrt(3) * (q + r / 2);
              const y = size * 1.5 * r;
              return (
                <motion.path
                  key={`${b.ring}-${i}`}
                  d={hexPath(x, y, size - 1)}
                  className={b.ring === 0 ? s.centre : s.cell}
                  initial={{ opacity: 0, scale: 0.6 }}
                  animate={{ opacity: b.ring === 0 ? 1 : 0.25 + 0.75 * Math.sqrt(b.total / max), scale: 1 }}
                  transition={{ duration: 0.4, delay: 0.12 * b.ring + 0.015 * i, ease: [0.2, 0.8, 0.2, 1] }}
                  style={{ transformOrigin: `${x}px ${y}px` }}
                />
              );
            }),
          )}
        </svg>
        <ol className={s.bands}>
          {bands.map((b) => (
            <li key={b.ring}>
              <p className={s.bandHead}>
                <span className={s.bandName}>{b.ring === 0 ? "same hexagon" : `${b.ring} ${b.ring === 1 ? "ring" : "rings"} out`}</span>
                <span className="num">
                  {b.total} {unit}
                </span>
              </p>
              {b.items.length ? <div className={s.items}>{b.items}</div> : <p className={s.none}>none</p>}
            </li>
          ))}
        </ol>
      </div>
      <p className={s.note}>Hexagons about 10 km across, on Uber&apos;s H3 grid; every neighbour is the same distance away.</p>
    </section>
  );
}
