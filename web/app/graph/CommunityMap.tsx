"use client";

import { useEffect, useMemo, useState } from "react";

import type { Community, Overview } from "@/lib/api";

import s from "./CommunityMap.module.css";

/**
 * The graph's communities as rings of what they hold (decision 0035): each community a ring split by its share of
 * sites and places, people and polities, culture and style, other entities, and documents, named by its three most
 * connected members. Two arrangements of the same rings: "as a network" (the communities that share facts, laid out
 * by those links) and "on the map" (every community whose places cluster, at the median of its placed members; one
 * whose places spread across India is shown apart, never at a misleading middle point). Switching moves each ring
 * from one place to the other, so the reader sees where a part of the network lies.
 */
export type Arrangement = "network" | "map";

const W = 1000;
const H = 760;
const PAD = 56;
const ORDER = ["built", "people", "culture", "other", "documents"] as const;
export const COMPOSITION_NAMES: Record<(typeof ORDER)[number], string> = {
  built: "sites and places",
  people: "people and polities",
  culture: "culture and style",
  other: "other entities",
  documents: "documents",
};
const BOX = { west: 67, east: 98, south: 6.5, north: 36.5 };
const APART_X = W - 150; // the column for communities with no centre, in the map arrangement

function project(lat: number, lon: number): [number, number] {
  const usable = APART_X - 2 * PAD;
  const k = Math.min(usable / (BOX.east - BOX.west), (H - 2 * PAD) / (BOX.north - BOX.south));
  return [PAD + (lon - BOX.west) * k, PAD + (BOX.north - lat) * k];
}

/**
 * Rings at their true points overlap where regions are dense, and a covered ring cannot be chosen. Overlaps are
 * pushed apart, with a weak pull back to each true point; the true point is drawn too, with a hairline, whenever a
 * ring had to move further than its own radius. Deterministic: fixed order, fixed number of rounds.
 */
export function relax(items: { id: number; x: number; y: number; r: number }[], gap = 3, rounds = 120) {
  const pos = items.map((it) => ({ ...it, tx: it.x, ty: it.y }));
  for (let k = 0; k < rounds; k++) {
    for (let i = 0; i < pos.length; i++) {
      for (let j = i + 1; j < pos.length; j++) {
        const a = pos[i]!;
        const b = pos[j]!;
        let dx = b.x - a.x;
        let dy = b.y - a.y;
        let d = Math.hypot(dx, dy);
        const need = a.r + b.r + gap;
        if (d >= need) continue;
        if (d < 1e-6) {
          // Same point: split them along a fixed direction from their ids, never at random.
          dx = Math.cos(a.id + b.id);
          dy = Math.sin(a.id + b.id);
          d = 1;
        }
        const push = (need - d) / 2;
        a.x -= (dx / d) * push;
        a.y -= (dy / d) * push;
        b.x += (dx / d) * push;
        b.y += (dy / d) * push;
      }
    }
    for (const p of pos) {
      p.x += (p.tx - p.x) * 0.02;
      p.y += (p.ty - p.y) * 0.02;
    }
  }
  return pos;
}

export function describe(c: Community): string {
  const parts = ORDER.filter((g) => (c.composition?.[g] ?? 0) > 0).map((g) => `${c.composition![g]} ${COMPOSITION_NAMES[g]}`);
  const where = c.spread === "regional" ? "its places cluster in one region" : c.spread === "across India" ? "its places spread across India" : "too few of its members have coordinates";
  return `${(c.top_labels ?? [c.label]).filter(Boolean).join(", ")}: ${c.size} nodes; ${parts.join(", ")}; ${where}`;
}

/** Ring arcs as dash segments on one circle, in the fixed group order, so the same kind always sits in the same place. */
function arcs(c: Community) {
  const total = ORDER.reduce((n, g) => n + (c.composition?.[g] ?? 0), 0) || 1;
  let start = 0;
  return ORDER.map((g) => {
    const share = (100 * (c.composition?.[g] ?? 0)) / total;
    const arc = { g, share, start };
    start += share;
    return arc;
  }).filter((a) => a.share > 0);
}

export function CommunityMap({
  o,
  arrangement,
  picked,
  onPick,
}: {
  o: Overview;
  arrangement: Arrangement;
  picked: number | null;
  onPick: (id: number | null) => void;
}) {
  const linked = useMemo(() => new Set(o.links.flatMap((l) => [l.a, l.b])), [o]);
  const core = useMemo(() => o.communities.filter((c) => linked.has(c.id)), [o, linked]);
  const [network, setNetwork] = useState<Record<number, [number, number]>>({});
  const [hover, setHover] = useState<number | null>(null);

  // The network layout, computed once: ForceAtlas2 from a fixed circle, so it settles the same way every time.
  useEffect(() => {
    let live = true;
    (async () => {
      const [{ default: Graph }, { default: forceAtlas2 }] = await Promise.all([import("graphology"), import("graphology-layout-forceatlas2")]);
      const g = new Graph({ type: "undirected" });
      core.forEach((c, i) => {
        const a = (2 * Math.PI * i) / Math.max(1, core.length);
        g.addNode(String(c.id), { x: Math.cos(a) * 10, y: Math.sin(a) * 10, size: Math.sqrt(c.size) });
      });
      o.links.forEach((l) => {
        if (g.hasNode(String(l.a)) && g.hasNode(String(l.b)) && !g.hasEdge(String(l.a), String(l.b))) g.addEdge(String(l.a), String(l.b), { weight: l.edges });
      });
      if (core.length > 2) forceAtlas2.assign(g, { iterations: 400, settings: { ...forceAtlas2.inferSettings(g), adjustSizes: true } });
      const xs = g.mapNodes((_, a) => a.x as number);
      const ys = g.mapNodes((_, a) => a.y as number);
      const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
      const k = Math.min((W - 2 * PAD) / (x1 - x0 || 1), (H - 2 * PAD) / (y1 - y0 || 1));
      const out: Record<number, [number, number]> = {};
      g.forEachNode((id, a) => {
        out[Number(id)] = [PAD + ((a.x as number) - x0) * k + (W - 2 * PAD - (x1 - x0) * k) / 2, PAD + ((a.y as number) - y0) * k];
      });
      if (live) setNetwork(out);
    })();
    return () => {
      live = false;
    };
  }, [core, o.links]);

  const max = Math.max(...o.communities.map((c) => c.size), 1);
  const full = (c: Community) => 7 + 26 * Math.sqrt(c.size / max);
  // In the map's side column, rings are capped in size so the column holds them without overlap.
  const radius = (c: Community) => (arrangement === "map" && !c.centre ? Math.min(full(c), 15) : full(c));

  // Where each ring stands in the current arrangement; a ring with no place there is hidden, not moved.
  const apart = o.communities.filter((c) => !c.centre).sort((a, b) => b.size - a.size);
  // The side column, stacked by each ring's own size; the ones that do not fit are listed in the text table.
  const column = new Map<number, [number, number]>();
  {
    let y = PAD + 48;
    for (const c of apart) {
      const r = Math.min(full(c), 15);
      if (y + r > H - 12) break;
      column.set(c.id, [APART_X + 110, y + r]);
      y += 2 * r + 10;
    }
  }
  const place = (c: Community): [number, number] | null => {
    if (arrangement === "network") return network[c.id] ?? null;
    if (c.centre) return project(c.centre[0], c.centre[1]);
    return column.get(c.id) ?? null;
  };
  const raw = o.communities.map((c) => ({ c, at: place(c) }));
  const settled =
    arrangement === "map"
      ? new Map(
          relax(raw.filter((x) => x.at && x.c.centre).map((x) => ({ id: x.c.id, x: x.at![0], y: x.at![1], r: radius(x.c) }))).map((p) => [p.id, p]),
        )
      : new Map<number, { x: number; y: number; tx: number; ty: number; r: number }>();
  const shown = raw.map(({ c, at }) => {
    const p = settled.get(c.id);
    return { c, at: p ? ([p.x, p.y] as [number, number]) : at, truth: p && Math.hypot(p.x - p.tx, p.y - p.ty) > p.r ? ([p.tx, p.ty] as [number, number]) : null };
  });
  // The picked ring is drawn last, so nothing covers it. Not the hovered one: moving an element in the DOM between
  // mouse-down and mouse-up loses the click (found in testing: the first click on a ring did nothing).
  const order = [...shown].sort((a, b) => Number(a.c.id === picked) - Number(b.c.id === picked));
  const visible = new Set(shown.filter((x) => x.at).map((x) => x.c.id));
  // Labels for the largest rings, the picked one and the one under the pointer; the rest name themselves on focus.
  const labelled = new Set([
    ...shown
      .filter((x) => x.at && (arrangement === "network" || x.c.centre))
      .sort((a, b) => b.c.size - a.c.size)
      .slice(0, arrangement === "network" ? 14 : 7)
      .map((x) => x.c.id),
    ...(arrangement === "map" ? [...column.keys()] : []), // each row of the side column has room for its name
    picked,
    hover,
  ]);

  return (
    <svg className={s.map} viewBox={`0 0 ${W} ${H}`} role="group" aria-label={arrangement === "network" ? "Communities, laid out by the facts they share" : "Communities, placed where their places cluster"}>
      {arrangement === "map" ? (
        <g className={s.graticule} aria-hidden>
          {[70, 75, 80, 85, 90, 95].map((lon) => {
            const [x] = project(BOX.south, lon);
            return <line key={lon} x1={x} y1={project(BOX.north, lon)[1]} x2={x} y2={project(BOX.south, lon)[1]} />;
          })}
          {[10, 15, 20, 25, 30, 35].map((lat) => {
            const [, y] = project(lat, BOX.west);
            return <line key={lat} x1={project(lat, BOX.west)[0]} y1={y} x2={project(lat, BOX.east)[0]} y2={y} />;
          })}
          <text className={s.apartTitle} x={APART_X + 130} y={PAD + 2} textAnchor="end">
            <tspan x={APART_X + 130}>across India,</tspan>
            <tspan x={APART_X + 130} dy="16">or too few placed</tspan>
          </text>
        </g>
      ) : null}
      <g className={s.links} aria-hidden>
        {o.links.map((l) => {
          const a = o.communities.find((c) => c.id === l.a);
          const b = o.communities.find((c) => c.id === l.b);
          const pa = a && shown.find((x) => x.c.id === a.id)?.at;
          const pb = b && shown.find((x) => x.c.id === b.id)?.at;
          if (!pa || !pb) return null;
          const lit = picked === l.a || picked === l.b || hover === l.a || hover === l.b;
          // On the map, every link at once is a web of long lines; only the chosen community's links are drawn.
          if (arrangement === "map" && !lit) return null;
          return <line key={`${l.a}-${l.b}`} className={lit ? s.linkLit : undefined} x1={pa[0]} y1={pa[1]} x2={pb[0]} y2={pb[1]} />;
        })}
      </g>
      <g className={s.truths} aria-hidden>
        {shown.map(({ c, at, truth }) =>
          truth && at ? (
            <g key={c.id}>
              <line x1={truth[0]} y1={truth[1]} x2={at[0]} y2={at[1]} />
              <circle cx={truth[0]} cy={truth[1]} r={2} />
            </g>
          ) : null,
        )}
      </g>
      {order.map(({ c, at }) => {
        const r = radius(c);
        const on = visible.has(c.id);
        return (
          <g
            key={c.id}
            className={`${s.ring} ${on ? "" : s.gone} ${picked === c.id ? s.picked : ""}`}
            style={{ transform: `translate(${(at ?? [W / 2, H / 2])[0]}px, ${(at ?? [W / 2, H / 2])[1]}px)` }}
            role="button"
            tabIndex={on ? 0 : -1}
            aria-hidden={!on}
            aria-pressed={picked === c.id}
            aria-label={describe(c)}
            onClick={() => onPick(picked === c.id ? null : c.id)}
            onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), onPick(picked === c.id ? null : c.id))}
            onPointerEnter={() => setHover(c.id)}
            onPointerLeave={() => setHover(null)}
            onFocus={() => setHover(c.id)}
            onBlur={() => setHover(null)}
          >
            <title>{describe(c)}</title>
            <circle className={s.hit} r={r + 6} />
            <circle className={s.track} r={r} pathLength={100} />
            {arcs(c).map((a) => (
              <circle
                key={a.g}
                className={s[`arc_${a.g}`]}
                r={r}
                pathLength={100}
                strokeDasharray={`${Math.max(0, a.share - 0.8)} ${100 - Math.max(0, a.share - 0.8)}`}
                strokeDashoffset={-a.start}
                transform="rotate(-90)"
              />
            ))}
          </g>
        );
      })}
      {/* Names above every ring, so no ring covers another's name. */}
      <g className={s.names} aria-hidden>
        {shown.map(({ c, at }) => {
          if (!at || !labelled.has(c.id) || !visible.has(c.id)) return null;
          const r = radius(c);
          return arrangement === "map" && !c.centre ? (
            <text key={c.id} className={s.name} x={at[0] - r - 6} y={at[1] + 4} textAnchor="end">
              {c.label}
            </text>
          ) : (
            <text key={c.id} className={s.name} x={at[0]} y={at[1] + r + 14} textAnchor="middle">
              {c.label}
            </text>
          );
        })}
      </g>
    </svg>
  );
}

export function CompositionLegend() {
  return (
    <ul className={s.legend} aria-label="What the ring's colours mean">
      {ORDER.map((g) => (
        <li key={g}>
          <i className={s[`key_${g}`]} aria-hidden /> {COMPOSITION_NAMES[g]}
        </li>
      ))}
    </ul>
  );
}
