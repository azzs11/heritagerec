"use client";

import { forwardRef, useEffect, useImperativeHandle, useRef } from "react";

import { groupOf } from "@/components/LiveGraph";
import { label, type Place } from "@/lib/api";

import s from "./atlas.module.css";

// A box around India that frames the map; places outside it still exist and are listed when near.
export const FRAME = { lat: [6, 37.5] as const, lon: [68, 97.5] as const };
const DOTS_FROM = 2.2; // zoom at which density hexagons give way to dots
const DOTS_FULL = 3.6;

export interface MapHandle {
  zoomBy: (k: number) => void;
  reset: () => void;
}

export interface Hover {
  place: Place;
  x: number;
  y: number;
}

/**
 * The atlas canvas. Far out, places are counted into hexagons, so dense regions read as density rather than a
 * smear of dots; closer in, the hexagons melt into individual places coloured by type. A chosen point is flown to
 * and marked with a ping. Everything is drawn on one canvas; only the transform changes as the reader moves.
 */
export const AtlasMap = forwardRef<
  MapHandle,
  {
    places: Place[];
    visible: (p: Place) => "on" | "faint" | "off";
    lit: string[];
    point: { lat: number; lon: number } | null;
    onPick: (p: { lat: number; lon: number }) => void;
    onHover: (h: Hover | null) => void;
  }
>(function AtlasMap({ places, visible, lit, point, onPick, onHover }, ref) {
  const box = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const ping = useRef<HTMLDivElement>(null);
  const api = useRef<{ draw: () => void; zoomBy: (k: number) => void; reset: () => void; flyTo: (lat: number, lon: number) => void } | null>(null);
  const props = useRef({ visible, lit, point });

  useImperativeHandle(ref, () => ({ zoomBy: (k) => api.current?.zoomBy(k), reset: () => api.current?.reset() }), []);

  useEffect(() => {
    let cleanup = () => {};
    (async () => {
      const [{ geoConicEqualArea, geoGraticule10, geoPath }, { zoom, zoomIdentity }, { select }, { hexbin }] = await Promise.all([
        import("d3-geo"),
        import("d3-zoom"),
        import("d3-selection"),
        import("d3-hexbin"),
        import("d3-transition"),
      ]);
      const el = canvas.current;
      const holder = box.current;
      if (!el || !holder) return;
      const ctx = el.getContext("2d");
      if (!ctx) return;
      let t = zoomIdentity;
      let w = 0;
      let h = 0;
      const projection = geoConicEqualArea().parallels([12, 28]).rotate([-80, 0]);
      let xy: [number, number][] = [];
      const graticule = geoGraticule10();
      const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

      const size = () => {
        const dpr = Math.min(2, window.devicePixelRatio || 1);
        w = holder.clientWidth;
        h = holder.clientHeight;
        el.width = w * dpr;
        el.height = h * dpr;
        el.style.width = `${w}px`;
        el.style.height = `${h}px`;
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        projection.fitExtent(
          [
            [24, 24],
            [w - 24, h - 24],
          ],
          {
            type: "MultiPoint",
            coordinates: [
              [FRAME.lon[0], FRAME.lat[0]],
              [FRAME.lon[1], FRAME.lat[1]],
              [FRAME.lon[0], FRAME.lat[1]],
              [FRAME.lon[1], FRAME.lat[0]],
            ],
          },
        );
        xy = places.map((p) => projection([p.lon, p.lat]) ?? [-999, -999]);
      };

      const colours = () => {
        const css = getComputedStyle(document.documentElement);
        const v = (n: string) => css.getPropertyValue(n).trim();
        return {
          ink: v("--ink"),
          faint: v("--ink-faint"),
          rule: v("--rule"),
          lac: v("--lac"),
          paper: v("--paper"),
          built: v("--type-built"),
          people: v("--type-people"),
          culture: v("--type-culture"),
          other: v("--ink-soft"),
        };
      };

      const draw = () => {
        const c = colours();
        const { visible: vis, lit: litIds, point: pt } = props.current;
        const on = new Set(litIds);
        ctx.clearRect(0, 0, w, h);
        // graticule, in map space
        ctx.save();
        ctx.translate(t.x, t.y);
        ctx.scale(t.k, t.k);
        ctx.beginPath();
        geoPath(projection, ctx)(graticule);
        ctx.strokeStyle = c.rule;
        ctx.lineWidth = 0.7 / t.k;
        ctx.stroke();
        ctx.restore();

        const dotsMix = Math.max(0, Math.min(1, (t.k - DOTS_FROM) / (DOTS_FULL - DOTS_FROM)));
        // density hexagons, drawn in screen space from the visible places
        if (dotsMix < 1) {
          const pts: [number, number][] = [];
          places.forEach((p, i) => {
            if (vis(p) !== "on") return;
            pts.push([t.applyX(xy[i]![0]), t.applyY(xy[i]![1])]);
          });
          const bins = hexbin<[number, number]>().radius(11).extent([[-20, -20], [w + 20, h + 20]])(pts);
          const max = Math.max(1, ...bins.map((b) => b.length));
          const hexPath = new Path2D(hexbin().radius(10.2).hexagon());
          ctx.fillStyle = c.ink;
          for (const b of bins) {
            ctx.globalAlpha = (1 - dotsMix) * (0.12 + 0.68 * Math.sqrt(b.length / max));
            ctx.save();
            ctx.translate(b.x, b.y);
            ctx.fill(hexPath);
            ctx.restore();
          }
          ctx.globalAlpha = 1;
        }

        // individual places, coloured by type
        if (dotsMix > 0) {
          const grow = Math.min(2.4, Math.sqrt(t.k / 2));
          places.forEach((p, i) => {
            const v = vis(p);
            if (v === "off" || on.has(p.id)) return;
            const x = t.applyX(xy[i]![0]);
            const y = t.applyY(xy[i]![1]);
            if (x < -10 || y < -10 || x > w + 10 || y > h + 10) return;
            const g = groupOf("entity", p.type);
            ctx.globalAlpha = dotsMix * (v === "faint" ? 0.18 : on.size ? 0.4 : 0.85);
            ctx.fillStyle = c[g as "built" | "people" | "culture" | "other"] ?? c.other;
            ctx.beginPath();
            ctx.arc(x, y, (1.4 + Math.min(3.4, Math.sqrt(p.documents) * 0.6)) * grow, 0, Math.PI * 2);
            ctx.fill();
          });
          ctx.globalAlpha = 1;
        }

        // the chosen places, always drawn, with names when close enough to read
        const labelled: [number, number][] = [];
        ctx.font = '500 12px "Noto Sans", "Noto Sans Devanagari", "Noto Sans Kannada", sans-serif';
        litIds.forEach((id, rank) => {
          const i = places.findIndex((p) => p.id === id);
          if (i < 0) return;
          const x = t.applyX(xy[i]![0]);
          const y = t.applyY(xy[i]![1]);
          ctx.fillStyle = c.paper;
          ctx.beginPath();
          ctx.arc(x, y, 5.5, 0, Math.PI * 2);
          ctx.fill();
          ctx.fillStyle = c.lac;
          ctx.beginPath();
          ctx.arc(x, y, 3.8, 0, Math.PI * 2);
          ctx.fill();
          if (t.k >= 5 && rank < 10 && !labelled.some(([a, b]) => Math.abs(a - x) < 90 && Math.abs(b - y) < 16)) {
            labelled.push([x, y]);
            const name = label(places[i]!.labels, id);
            ctx.lineWidth = 3;
            ctx.strokeStyle = c.paper;
            ctx.strokeText(name, x + 8, y + 4);
            ctx.fillStyle = c.ink;
            ctx.fillText(name, x + 8, y + 4);
          }
        });

        // the ping sits on the chosen point
        if (pt && ping.current) {
          const pr = projection([pt.lon, pt.lat]);
          if (pr) ping.current.style.transform = `translate(${t.applyX(pr[0])}px, ${t.applyY(pr[1])}px)`;
        }
      };

      size();
      const z = zoom<HTMLCanvasElement, unknown>()
        .scaleExtent([1, 60])
        .on("zoom", (e) => {
          t = e.transform;
          draw();
        });
      const sel = select(el);
      sel.call(z).on("dblclick.zoom", null);
      const flyTo = (lat: number, lon: number) => {
        const c = projection([lon, lat]);
        if (!c) return;
        const k = Math.max(t.k, 7);
        const target = zoomIdentity.translate(w * 0.42, h / 2).scale(k).translate(-c[0], -c[1]);
        if (reduce) sel.call(z.transform, target);
        else sel.transition().duration(1000).call(z.transform, target);
      };
      api.current = {
        draw,
        flyTo,
        zoomBy: (k) => (reduce ? sel.call(z.scaleBy, k) : sel.transition().duration(300).call(z.scaleBy, k)),
        reset: () => (reduce ? sel.call(z.transform, zoomIdentity) : sel.transition().duration(700).call(z.transform, zoomIdentity)),
      };
      if (props.current.point) {
        const c = projection([props.current.point.lon, props.current.point.lat]);
        if (c) sel.call(z.transform, zoomIdentity.translate(w * 0.42, h / 2).scale(7).translate(-c[0], -c[1]));
      }

      const nearest = (mx: number, my: number, within: number) => {
        let best = -1;
        let bestD = within * within;
        const { visible: vis } = props.current;
        xy.forEach(([x0, y0], i) => {
          if (vis(places[i]!) === "off") return;
          const d = (t.applyX(x0) - mx) ** 2 + (t.applyY(y0) - my) ** 2;
          if (d < bestD) {
            bestD = d;
            best = i;
          }
        });
        return best;
      };
      el.addEventListener("click", (ev) => {
        const r = el.getBoundingClientRect();
        const mx = ev.clientX - r.left;
        const my = ev.clientY - r.top;
        const i = nearest(mx, my, 12);
        if (i >= 0) onPick({ lat: places[i]!.lat, lon: places[i]!.lon });
        else {
          const ll = projection.invert?.([t.invertX(mx), t.invertY(my)]);
          if (ll) onPick({ lat: Math.max(-90, Math.min(90, ll[1])), lon: ((ll[0] + 540) % 360) - 180 });
        }
      });
      el.addEventListener("mousemove", (ev) => {
        const r = el.getBoundingClientRect();
        const mx = ev.clientX - r.left;
        const my = ev.clientY - r.top;
        const i = t.k >= DOTS_FROM ? nearest(mx, my, 10) : -1;
        el.style.cursor = i >= 0 ? "pointer" : "crosshair";
        onHover(i >= 0 ? { place: places[i]!, x: mx, y: my } : null);
      });
      el.addEventListener("mouseleave", () => onHover(null));
      const ro = new ResizeObserver(() => {
        size();
        draw();
      });
      ro.observe(holder);
      const mo = new MutationObserver(draw);
      mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
      draw();
      cleanup = () => {
        ro.disconnect();
        mo.disconnect();
        sel.on(".zoom", null);
        api.current = null;
      };
    })();
    return () => cleanup();
    // Built once per set of places; filters, selection and the point only redraw (below).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [places]);

  useEffect(() => {
    const prev = props.current.point;
    props.current = { visible, lit, point };
    api.current?.draw();
    if (point && (!prev || prev.lat !== point.lat || prev.lon !== point.lon)) api.current?.flyTo(point.lat, point.lon);
  }, [visible, lit, point]);

  return (
    <div ref={box} className={s.map}>
      <canvas ref={canvas} role="img" aria-label={`Map of ${places.length} heritage places in and around India`} />
      {point ? <div ref={ping} key={`${point.lat},${point.lon}`} className={s.ping} aria-hidden /> : null}
    </div>
  );
});
