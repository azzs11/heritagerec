"use client";

import { usePathname } from "next/navigation";
import { useEffect, useRef } from "react";

import { api } from "@/lib/api";

/**
 * The background: every placed entity as a faint point, India drawn by its own heritage, like a night sky.
 * Drawn once on a canvas and moved only by a slow CSS drift (cheap for the GPU); barely visible on paper, softly
 * luminous in the dark theme. Hidden where the Atlas and the Graph draw their own canvases, still under reduced
 * motion, and absent when the server cannot be reached (it is decoration, never information).
 */
export function SkyField() {
  const path = usePathname() ?? "/";
  const canvas = useRef<HTMLCanvasElement>(null);
  const hidden = path.startsWith("/atlas") || path.startsWith("/graph");

  useEffect(() => {
    if (hidden) return;
    let live = true;
    const draw = (points: { lat: number; lon: number }[]) => {
      const el = canvas.current;
      if (!el || !live) return;
      const w = window.innerWidth;
      const h = window.innerHeight;
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      // Drawn a little larger than the window so the drift never shows an edge.
      const W = w * 1.15;
      const H = h * 1.15;
      el.width = W * dpr;
      el.height = H * dpr;
      el.style.width = `${W}px`;
      el.style.height = `${H}px`;
      const ctx = el.getContext("2d");
      if (!ctx) return;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, W, H);
      const ink = getComputedStyle(document.documentElement).getPropertyValue("--ink").trim() || "#1b1a17";
      // A plain equirectangular frame around India, placed off-centre to the right like a figure in a margin.
      const lon0 = 66;
      const lon1 = 99;
      const lat0 = 5;
      const lat1 = 38;
      const size = Math.min(W * 0.62, H * 1.05);
      const ox = W - size * 1.02;
      const oy = (H - size) / 2 + H * 0.04;
      ctx.fillStyle = ink;
      for (const p of points) {
        if (p.lon < lon0 || p.lon > lon1 || p.lat < lat0 || p.lat > lat1) continue;
        const x = ox + ((p.lon - lon0) / (lon1 - lon0)) * size;
        const y = oy + ((lat1 - p.lat) / (lat1 - lat0)) * size;
        // A deterministic sprinkle of brighter points, from the coordinates, not chance.
        const bright = Math.abs(Math.sin(p.lat * 12.9898 + p.lon * 78.233)) > 0.93;
        ctx.globalAlpha = bright ? 0.9 : 0.45;
        ctx.beginPath();
        ctx.arc(x, y, bright ? 1.3 : 0.8, 0, Math.PI * 2);
        ctx.fill();
      }
    };
    let points: { lat: number; lon: number }[] = [];
    api.places().then(
      (ps) => {
        points = ps;
        draw(points);
      },
      () => {
        /* no server, no sky */
      },
    );
    const redraw = () => draw(points);
    window.addEventListener("resize", redraw);
    const mo = new MutationObserver(redraw);
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    media.addEventListener("change", redraw);
    return () => {
      live = false;
      window.removeEventListener("resize", redraw);
      mo.disconnect();
      media.removeEventListener("change", redraw);
    };
  }, [hidden]);

  if (hidden) return null;
  return (
    <div className="sky" aria-hidden>
      <div className="sky-glow" />
      <canvas ref={canvas} className="sky-field" />
    </div>
  );
}
