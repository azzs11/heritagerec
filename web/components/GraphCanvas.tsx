"use client";

import { useEffect, useRef } from "react";

export interface CanvasNode {
  id: string;
  label: string;
  size: number;
  tone: "focus" | "entity" | "document" | "period" | "bundle" | "hub" | "community";
  important?: boolean; // always labelled
}

export interface CanvasEdge {
  id: string;
  source: string;
  target: string;
  label: string;
}

export interface CanvasProps {
  nodes: CanvasNode[];
  edges: CanvasEdge[];
  highlight?: Set<string>; // nodes and edges on a path, drawn in the graph lens colour
  selected?: string | null;
  onSelect: (id: string) => void;
  ariaLabel: string;
}

function tokens() {
  const css = getComputedStyle(document.documentElement);
  const v = (name: string) => css.getPropertyValue(name).trim();
  return {
    ink: v("--ink"),
    soft: v("--ink-soft"),
    faint: v("--ink-faint"),
    rule: v("--rule-strong"),
    lac: v("--lac"),
    paper: v("--paper"),
    indigo: v("--indigo"),
  };
}

/** WebGL drawing of a small graph (sigma.js + graphology); laid out by ForceAtlas2 from a seeded circle. */
export function GraphCanvas({ nodes, edges, highlight, selected, onSelect, ariaLabel }: CanvasProps) {
  const box = useRef<HTMLDivElement>(null);
  const pick = useRef(onSelect);
  useEffect(() => {
    pick.current = onSelect;
  });

  useEffect(() => {
    let killed = false;
    let renderer: { kill: () => void; refresh: () => void } | null = null;
    const observer = new MutationObserver(() => renderer?.refresh());
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const onScheme = () => renderer?.refresh();

    (async () => {
      const [{ default: Graph }, { default: Sigma }, { default: forceAtlas2 }] = await Promise.all([
        import("graphology"),
        import("sigma"),
        import("graphology-layout-forceatlas2"),
      ]);
      if (killed || !box.current) return;
      const g = new Graph({ multi: true, type: "undirected" });
      const n = nodes.length;
      nodes.forEach((node, i) => {
        // A fixed starting circle (no randomness), so the same view always settles the same way.
        const a = (2 * Math.PI * i) / Math.max(1, n);
        g.addNode(node.id, { x: Math.cos(a) * 10, y: Math.sin(a) * 10, size: node.size, label: node.label, tone: node.tone, important: !!node.important });
      });
      for (const e of edges) if (g.hasNode(e.source) && g.hasNode(e.target)) g.addEdgeWithKey(e.id, e.source, e.target, { label: e.label, size: 1 });
      if (n > 2) forceAtlas2.assign(g, { iterations: 220, settings: { ...forceAtlas2.inferSettings(g), barnesHutOptimize: n > 400 } });

      const s = new Sigma(g, box.current, {
        renderEdgeLabels: false,
        labelFont: '"Source Serif 4", "Noto Serif Devanagari", "Noto Serif Kannada", serif',
        labelSize: 13,
        labelWeight: "500",
        labelDensity: n > 150 ? 0.5 : 1,
        labelRenderedSizeThreshold: n > 150 ? 6 : 3,
        zIndex: true,
        nodeReducer: (key, attr) => {
          const t = tokens();
          const tone = attr.tone as CanvasNode["tone"];
          const lit = highlight?.has(key) || key === selected;
          const color =
            lit || tone === "focus"
              ? t.lac
              : tone === "document"
                ? t.faint
                : tone === "period" || tone === "bundle"
                  ? t.soft
                  : t.ink;
          return { ...attr, color, labelColor: t.ink, zIndex: lit ? 2 : tone === "document" ? 0 : 1, forceLabel: lit || tone === "focus" || !!attr.important };
        },
        edgeReducer: (key, attr) => {
          const t = tokens();
          const lit = highlight?.has(key);
          return { ...attr, color: lit ? t.lac : t.rule, size: lit ? 2.5 : 1, zIndex: lit ? 1 : 0 };
        },
        labelColor: { attribute: "labelColor" },
      });
      s.on("clickNode", ({ node }) => pick.current(node));
      s.on("enterNode", () => box.current && (box.current.style.cursor = "pointer"));
      s.on("leaveNode", () => box.current && (box.current.style.cursor = "default"));
      renderer = s;
      observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
      media.addEventListener("change", onScheme);
    })();

    return () => {
      killed = true;
      observer.disconnect();
      media.removeEventListener("change", onScheme);
      renderer?.kill();
    };
  }, [nodes, edges, highlight, selected]);

  return <div ref={box} role="img" aria-label={ariaLabel} style={{ width: "100%", height: "100%" }} />;
}
