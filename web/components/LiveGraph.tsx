"use client";

import { useEffect, useRef, useState } from "react";

import type { ImageRef } from "@/lib/api";

import s from "./LiveGraph.module.css";

export type Group = "built" | "people" | "culture" | "other" | "time" | "document" | "bundle";

export interface LiveNode {
  id: string;
  label: string;
  group: Group;
  size: number;
  hub?: boolean;
  image?: ImageRef;
  near?: string; // a node already on screen this one grows out of
}

export interface LiveEdge {
  id: string;
  source: string;
  target: string;
  label: string;
}

/** The entity types fold into three colour groups (validated for colour-blind readers); the type is always given in words too. */
export function groupOf(kind: string, type: string | null): Group {
  if (kind === "document") return "document";
  if (kind === "period") return "time";
  if (type === "site" || type === "place") return "built";
  if (type === "person" || type === "polity") return "people";
  if (type === "culture" || type === "style") return "culture";
  return "other";
}

export const GROUP_NAMES: Record<Exclude<Group, "bundle">, string> = {
  built: "sites and places",
  people: "people and polities",
  culture: "culture and style",
  other: "other entities",
  time: "centuries",
  document: "documents",
};

function hash(id: string): number {
  let h = 2166136261;
  for (let i = 0; i < id.length; i++) h = Math.imul(h ^ id.charCodeAt(i), 16777619);
  return (h >>> 0) / 4294967295;
}

function rgb(c: string): [number, number, number] {
  const m = c.match(/^#([0-9a-f]{6})$/i);
  if (m) {
    const n = parseInt(m[1]!, 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }
  const parts = c.match(/[\d.]+/g)?.map(Number) ?? [0, 0, 0];
  return [parts[0] ?? 0, parts[1] ?? 0, parts[2] ?? 0];
}

/** `t` of the way from colour `a` to colour `b`, as an opaque hex. */
function mix(a: string, b: string, t: number): string {
  const x = rgb(a);
  const y = rgb(b);
  return `#${x.map((c, i) => Math.round(c + (y[i]! - c) * t).toString(16).padStart(2, "0")).join("")}`;
}

function palette() {
  const css = getComputedStyle(document.documentElement);
  const v = (n: string) => css.getPropertyValue(n).trim();
  const paper = v("--paper");
  const ink = v("--ink");
  return {
    built: v("--type-built"),
    people: v("--type-people"),
    culture: v("--type-culture"),
    other: v("--ink-soft"),
    time: v("--ink-faint"),
    document: v("--ink-faint"),
    bundle: v("--ink-faint"),
    ink,
    faint: mix(paper, ink, 0.12),
    strong: mix(paper, ink, 0.32),
    lac: v("--lac"),
    paper,
    card: v("--card"),
  };
}

type Sigma = import("sigma").default;
type GraphT = import("graphology").default;
type FA2 = import("graphology-layout-forceatlas2/worker").default;

/**
 * A graph that stays alive between changes: the layout runs in a worker and the reader watches it settle; new
 * nodes are placed beside the node they grew from and everything already placed stays where it is; hovering lights
 * a node's neighbours and the facts between them; selecting flies the camera to the node; a path pulses along its
 * facts. Museum objects with an open image ride on their node as a small round photograph (drawn as HTML, since the
 * museums' image servers do not allow their pictures inside WebGL).
 */
export function LiveGraph({
  nodes,
  edges,
  selected,
  path,
  onSelect,
  ariaLabel,
  focusOnSelect = true,
}: {
  nodes: LiveNode[];
  edges: LiveEdge[];
  selected?: string | null;
  path?: { nodes: string[]; edges: string[] } | null;
  onSelect: (id: string | null) => void;
  ariaLabel: string;
  focusOnSelect?: boolean;
}) {
  const box = useRef<HTMLDivElement>(null);
  const overlay = useRef<HTMLDivElement>(null);
  const live = useRef<{ sigma: Sigma; graph: GraphT; fa2: FA2 | null; stop: number } | null>(null);
  const state = useRef({ hover: null as string | null, selected: selected ?? null, pathEdges: new Set<string>(), pathNodes: new Set<string>(), lit: 0 });
  const pick = useRef(onSelect);
  const [ready, setReady] = useState(false);
  // The first selection is the page opening on its centre: show the whole picture, fly only on later choices.
  const firstSelection = useRef(true);
  const imageNodes = nodes.filter((n) => n.image);

  useEffect(() => {
    pick.current = onSelect;
  });

  // Build the renderer once.
  useEffect(() => {
    let killed = false;
    (async () => {
      const [{ default: Graph }, { default: Sigma }] = await Promise.all([import("graphology"), import("sigma")]);
      if (killed || !box.current) return;
      const graph = new Graph({ type: "undirected", multi: false });
      let colours = palette();
      const sigma = new Sigma(graph, box.current, {
        renderEdgeLabels: true,
        enableEdgeEvents: false,
        labelFont: '"Noto Sans", "Noto Sans Devanagari", "Noto Sans Kannada", sans-serif',
        labelSize: 12,
        labelWeight: "500",
        edgeLabelFont: '"Noto Sans", sans-serif',
        edgeLabelSize: 11,
        labelDensity: 0.9,
        labelGridCellSize: 90,
        labelRenderedSizeThreshold: 6,
        zIndex: true,
        defaultEdgeType: "line",
        nodeReducer: (key, attr) => {
          const st = state.current;
          const g = attr.group as Group;
          const hover = st.hover;
          const neighbour = hover != null && (key === hover || graph.areNeighbors(hover, key));
          const onPath = st.pathNodes.has(key);
          const dim = (hover != null && !neighbour) || (st.pathNodes.size > 0 && !onPath && hover == null);
          return {
            ...attr,
            color: onPath ? colours.lac : dim ? colours.faint : colours[g] || colours.other,
            size: key === st.selected ? attr.size * 1.45 : attr.size,
            label: dim ? "" : attr.label,
            forceLabel: key === st.selected || key === hover || onPath || attr.important,
            highlighted: key === st.selected,
            zIndex: key === st.selected || onPath ? 3 : neighbour ? 2 : dim ? 0 : 1,
          };
        },
        edgeReducer: (key, attr) => {
          const st = state.current;
          const [a, b] = graph.extremities(key);
          const touching = st.hover != null && (a === st.hover || b === st.hover);
          const lit = st.pathEdges.has(key) && [...st.pathEdges].indexOf(key) < st.lit;
          return {
            ...attr,
            color: lit ? colours.lac : touching ? colours.ink : st.hover != null || st.pathEdges.size ? colours.faint : colours.strong,
            size: lit ? 3 : touching ? 1.6 : 0.8,
            label: touching || lit ? attr.label : "",
            forceLabel: touching || lit,
            zIndex: lit ? 2 : touching ? 1 : 0,
          };
        },
        labelColor: { color: colours.ink },
        edgeLabelColor: { color: colours.lac },
        defaultDrawNodeHover: (ctx, data, settings) => {
          const size = settings.labelSize;
          ctx.font = `${settings.labelWeight} ${size}px ${settings.labelFont}`;
          const label = typeof data.label === "string" ? data.label : "";
          const w = ctx.measureText(label).width;
          const pad = 4;
          ctx.beginPath();
          ctx.fillStyle = colours.card;
          ctx.strokeStyle = colours.strong;
          ctx.lineWidth = 1;
          if (label) {
            const x = data.x + data.size + 2;
            const y = data.y - size / 2 - pad;
            ctx.roundRect(x, y, w + 2 * pad + 2, size + 2 * pad, 3);
            ctx.fill();
            ctx.stroke();
            ctx.fillStyle = colours.ink;
            ctx.fillText(label, x + pad + 1, data.y + size / 3);
          }
          ctx.beginPath();
          ctx.arc(data.x, data.y, data.size + 3, 0, Math.PI * 2);
          ctx.strokeStyle = colours.ink;
          ctx.lineWidth = 1.5;
          ctx.stroke();
        },
      });
      sigma.on("enterNode", ({ node }) => {
        state.current.hover = node;
        if (box.current) box.current.style.cursor = "pointer";
        sigma.refresh({ skipIndexation: true });
      });
      sigma.on("leaveNode", () => {
        state.current.hover = null;
        if (box.current) box.current.style.cursor = "grab";
        sigma.refresh({ skipIndexation: true });
      });
      sigma.on("clickNode", ({ node }) => pick.current(node));
      sigma.on("clickStage", () => pick.current(null));
      // Keep the photographs on their nodes as the camera and the layout move.
      sigma.on("afterRender", () => {
        const layer = overlay.current;
        if (!layer) return;
        for (const el of Array.from(layer.children) as HTMLElement[]) {
          const id = el.dataset.node!;
          if (!graph.hasNode(id)) continue;
          const d = sigma.getNodeDisplayData(id);
          if (!d) continue;
          const p = sigma.graphToViewport({ x: graph.getNodeAttribute(id, "x"), y: graph.getNodeAttribute(id, "y") });
          const r = Math.max(9, sigma.scaleSize(d.size) * 1.9);
          const st = state.current;
          const dim = st.hover != null && st.hover !== id && !graph.areNeighbors(st.hover, id);
          el.style.transform = `translate(${p.x - r}px, ${p.y - r}px)`;
          el.style.width = el.style.height = `${2 * r}px`;
          el.style.opacity = dim ? "0.15" : "1";
        }
      });
      const recolour = () => {
        colours = palette();
        sigma.setSetting("labelColor", { color: colours.ink });
        sigma.setSetting("edgeLabelColor", { color: colours.lac });
        sigma.refresh();
      };
      const mo = new MutationObserver(recolour);
      mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
      const media = window.matchMedia("(prefers-color-scheme: dark)");
      media.addEventListener("change", recolour);
      live.current = { sigma, graph, fa2: null, stop: 0 };
      (live.current as unknown as { cleanup: () => void }).cleanup = () => {
        mo.disconnect();
        media.removeEventListener("change", recolour);
      };
      setReady(true);
    })();
    return () => {
      killed = true;
      const l = live.current as (typeof live.current & { cleanup?: () => void }) | null;
      l?.cleanup?.();
      l?.fa2?.kill();
      window.clearTimeout(l?.stop ?? 0);
      l?.sigma.kill();
      live.current = null;
    };
  }, []);

  // Grow or shrink the graph to match the data, then let the layout settle where the reader can see it.
  useEffect(() => {
    const l = live.current;
    if (!ready || !l) return;
    const { graph, sigma } = l;
    const want = new Set(nodes.map((n) => n.id));
    graph.forEachNode((n) => {
      if (!want.has(n)) graph.dropNode(n);
    });
    const fresh = graph.order === 0;
    nodes.forEach((n, i) => {
      if (graph.hasNode(n.id)) {
        graph.mergeNodeAttributes(n.id, { label: n.label, group: n.group, size: n.size, important: n.hub });
        return;
      }
      let x: number;
      let y: number;
      const parent = n.near && graph.hasNode(n.near) ? graph.getNodeAttributes(n.near) : null;
      const angle = 2 * Math.PI * hash(n.id);
      if (parent) {
        x = parent.x + Math.cos(angle) * 3;
        y = parent.y + Math.sin(angle) * 3;
      } else {
        const r = fresh ? 4 + 18 * hash(`${n.id}r`) : 24;
        x = i === 0 && fresh ? 0 : Math.cos(angle) * r;
        y = i === 0 && fresh ? 0 : Math.sin(angle) * r;
      }
      graph.addNode(n.id, { x, y, label: n.label, group: n.group, size: n.size, important: n.hub });
    });
    for (const e of edges) {
      if (graph.hasNode(e.source) && graph.hasNode(e.target) && e.source !== e.target && !graph.hasEdge(e.source, e.target)) {
        graph.addEdgeWithKey(e.id, e.source, e.target, { label: e.label });
      }
    }
    graph.forEachEdge((key) => {
      if (!edges.some((e) => e.id === key)) graph.dropEdge(key);
    });

    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    (async () => {
      const [{ default: FA2Layout }, { default: forceAtlas2 }] = await Promise.all([
        import("graphology-layout-forceatlas2/worker"),
        import("graphology-layout-forceatlas2"),
      ]);
      if (!live.current) return;
      const settings = { ...forceAtlas2.inferSettings(graph), slowDown: 6, gravity: 1.2, barnesHutOptimize: graph.order > 300 };
      if (reduce || graph.order < 3) {
        if (graph.order >= 3) forceAtlas2.assign(graph, { iterations: 200, settings });
        sigma.refresh();
        return;
      }
      l.fa2?.kill();
      window.clearTimeout(l.stop);
      const fa2 = new FA2Layout(graph, { settings });
      l.fa2 = fa2;
      fa2.start();
      l.stop = window.setTimeout(() => fa2.stop(), fresh ? 2600 : 1600);
    })();
  }, [nodes, edges, ready]);

  // Fly to the selected node.
  useEffect(() => {
    state.current.selected = selected ?? null;
    const l = live.current;
    if (!ready || !l) return;
    l.sigma.refresh({ skipIndexation: true });
    if (firstSelection.current) {
      firstSelection.current = false;
      return;
    }
    if (!selected || !focusOnSelect || !l.graph.hasNode(selected)) return;
    const t = window.setTimeout(() => {
      const d = l.sigma.getNodeDisplayData(selected);
      if (!d) return;
      const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      l.sigma.getCamera().animate({ x: d.x, y: d.y, ratio: Math.min(l.sigma.getCamera().ratio, 0.8) }, { duration: reduce ? 0 : 600 });
    }, 250);
    return () => window.clearTimeout(t);
  }, [selected, ready, focusOnSelect]);

  // A path lights up one fact at a time, like a walk travelling along it.
  useEffect(() => {
    const st = state.current;
    st.pathEdges = new Set(path?.edges ?? []);
    st.pathNodes = new Set(path?.nodes ?? []);
    st.lit = 0;
    const l = live.current;
    if (!ready || !l) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!path || reduce) {
      st.lit = st.pathEdges.size;
      l.sigma.refresh({ skipIndexation: true });
      return;
    }
    const timer = window.setInterval(() => {
      st.lit += 1;
      l.sigma.refresh({ skipIndexation: true });
      if (st.lit >= st.pathEdges.size) window.clearInterval(timer);
    }, 320);
    return () => window.clearInterval(timer);
  }, [path, ready]);

  return (
    <div className={s.wrap}>
      <div ref={box} className={s.canvas} role="img" aria-label={ariaLabel} />
      <div ref={overlay} className={s.photos} aria-hidden>
        {imageNodes.map((n) => (
          <div key={n.id} data-node={n.id} className={s.photo}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={n.image!.thumb} alt="" loading="lazy" referrerPolicy="no-referrer" onError={(e) => ((e.currentTarget.parentElement as HTMLElement).style.display = "none")} />
          </div>
        ))}
      </div>
    </div>
  );
}

/** What the colours mean, with the type in words. */
export function Legend({ groups }: { groups: Exclude<Group, "bundle">[] }) {
  return (
    <ul className={s.legend} aria-label="Legend">
      {groups.map((g) => (
        <li key={g}>
          <i className={s[`dot_${g}`]} aria-hidden />
          {GROUP_NAMES[g]}
        </li>
      ))}
    </ul>
  );
}
