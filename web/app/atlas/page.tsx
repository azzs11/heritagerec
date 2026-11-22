"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";

import { GraphCanvas, type CanvasEdge, type CanvasNode } from "@/components/GraphCanvas";
import { Load, MarginNote, Names, Seal, fmt } from "@/components/ui";
import { api, label, type NearView, type Place } from "@/lib/api";
import { useResource } from "@/lib/useResource";

import s from "./atlas.module.css";

// A rough box around India, used only to frame the map; places outside it still exist and are listed when near.
const FRAME = { lat: [6, 37.5] as const, lon: [68, 97.5] as const };

export default function AtlasPage() {
  return (
    <Suspense fallback={<p className="page">Unrolling the atlas…</p>}>
      <Atlas />
    </Suspense>
  );
}

function Atlas() {
  const params = useSearchParams();
  const router = useRouter();
  const lat = params.get("lat");
  const lon = params.get("lon");
  const point = lat && lon && Number.isFinite(+lat) && Number.isFinite(+lon) ? { lat: +lat, lon: +lon } : null;
  const places = useResource(api.places, "places");
  const goTo = (p: { lat: number; lon: number }) => router.push(`/atlas/?lat=${p.lat.toFixed(5)}&lon=${p.lon.toFixed(5)}`, { scroll: false });

  return (
    <article className={s.full}>
      <header className={s.head}>
        <div>
          <h1 className={s.title}>Atlas</h1>
        </div>
        <PlaceFinder onPick={goTo} />
      </header>
      <Load res={places} what="the places">
        {(ps) => <AtlasBody places={ps} point={point} onPick={goTo} />}
      </Load>
    </article>
  );
}

function PlaceFinder({ onPick }: { onPick: (p: { lat: number; lon: number }) => void }) {
  const [q, setQ] = useState("");
  const res = useResource(q.trim().length >= 2 ? () => api.find(q.trim()) : null, `pf|${q.trim()}`);
  const placed = res.state === "ready" ? res.data.filter((n) => n.lat != null) : [];
  return (
    <div className={s.finder}>
      <label htmlFor="place" className="label">
        go to a place
      </label>
      <input id="place" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Belur, बेलूर, ಬೇಲೂರು…" autoComplete="off" />
      {q.trim().length >= 2 && res.state === "ready" ? (
        <ul className={s.found}>
          {placed.length === 0 ? <li className={s.muted}>no placed match</li> : null}
          {placed.slice(0, 8).map((n) => (
            <li key={n.id}>
              <button onClick={() => (setQ(""), onPick({ lat: n.lat!, lon: n.lon! }))}>
                <Names labels={n.labels} fallback={n.id} />
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function AtlasBody({ places, point, onPick }: { places: Place[]; point: { lat: number; lon: number } | null; onPick: (p: { lat: number; lon: number }) => void }) {
  const near = useResource(point ? () => api.near(point.lat, point.lon, 25) : null, point ? `near|${point.lat}|${point.lon}` : "none");
  // Nearest first; the map labels only the closest few so the names do not collide.
  const nearIds = useMemo(() => (near.state === "ready" ? near.data.places.map((p) => p.id) : []), [near]);
  const outside = places.filter((p) => p.lat < FRAME.lat[0] || p.lat > FRAME.lat[1] || p.lon < FRAME.lon[0] || p.lon > FRAME.lon[1]).length;

  return (
    <div className={s.stage}>
      <div>
        <InkMap places={places} point={point} lit={nearIds} onPick={onPick} />
        <p className={s.caption}>
          <span className="num">{fmt(places.length)}</span> places with coordinates, each a dot sized by the documents
          about it; <span className="num">{fmt(outside)}</span> lie outside this frame. Scroll or pinch to zoom; click
          anywhere to ask what is near.
        </p>
      </div>
      <aside className={s.panel}>
        {!point ? (
          <>
            <p>
              Click the map, or go to a place by name. The atlas finds the 25 nearest places that are not hubs, however
              far that reaches, so a quiet region still answers, and shows what the graph says ties them.
            </p>
            <MarginNote title="Why are there no borders?">
              <p>
                India&apos;s boundaries must follow the Survey of India&apos;s depiction, and its boundary data needs a
                licence. Until that is settled, nothing political is drawn: the dots themselves make the map.
              </p>
            </MarginNote>
          </>
        ) : (
          <Load res={near} what="the places nearby">
            {(n) => <Nearby n={n} />}
          </Load>
        )}
      </aside>
    </div>
  );
}

function InkMap({ places, point, lit, onPick }: { places: Place[]; point: { lat: number; lon: number } | null; lit: string[]; onPick: (p: { lat: number; lon: number }) => void }) {
  const box = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const redraw = useRef<() => void>(() => {});
  const state = useRef({ lit, point });

  useEffect(() => {
    let cleanup = () => {};
    (async () => {
      const [{ geoConicEqualArea, geoGraticule10, geoPath }, { zoom, zoomIdentity }, { select }] = await Promise.all([
        import("d3-geo"),
        import("d3-zoom"),
        import("d3-selection"),
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

      const size = () => {
        const dpr = window.devicePixelRatio || 1;
        w = holder.clientWidth;
        h = holder.clientHeight;
        el.width = w * dpr;
        el.height = h * dpr;
        el.style.width = `${w}px`;
        el.style.height = `${h}px`;
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        projection.fitExtent(
          [
            [16, 16],
            [w - 16, h - 16],
          ],
          { type: "MultiPoint", coordinates: [[FRAME.lon[0], FRAME.lat[0]], [FRAME.lon[1], FRAME.lat[1]], [FRAME.lon[0], FRAME.lat[1]], [FRAME.lon[1], FRAME.lat[0]]] },
        );
        xy = places.map((p) => projection([p.lon, p.lat]) ?? [-99, -99]);
      };

      const draw = () => {
        const css = getComputedStyle(document.documentElement);
        const ink = css.getPropertyValue("--ink").trim();
        const rule = css.getPropertyValue("--rule").trim();
        const lac = css.getPropertyValue("--lac").trim();
        ctx.clearRect(0, 0, w, h);
        ctx.save();
        ctx.translate(t.x, t.y);
        ctx.scale(t.k, t.k);
        ctx.beginPath();
        geoPath(projection, ctx)(graticule);
        ctx.strokeStyle = rule;
        ctx.lineWidth = 0.6 / t.k;
        ctx.stroke();
        ctx.restore();
        const grow = Math.min(2.2, Math.sqrt(t.k));
        const { lit: order, point: pt } = state.current;
        const on = new Set(order);
        const labelled = new Set(order.slice(0, 8));
        ctx.globalAlpha = on.size ? 0.35 : 0.72;
        ctx.fillStyle = ink;
        places.forEach((p, i) => {
          const [x0, y0] = xy[i]!;
          const x = t.applyX(x0);
          const y = t.applyY(y0);
          if (x < -10 || y < -10 || x > w + 10 || y > h + 10 || on.has(p.id)) return;
          const r = (0.9 + Math.min(4, Math.sqrt(p.documents) * 0.55)) * grow;
          ctx.beginPath();
          ctx.arc(x, y, r, 0, 2 * Math.PI);
          ctx.fill();
        });
        ctx.globalAlpha = 1;
        ctx.fillStyle = lac;
        ctx.font = '500 12px "Noto Sans", "Noto Sans Devanagari", "Noto Sans Kannada", sans-serif';
        places.forEach((p, i) => {
          if (!on.has(p.id)) return;
          const [x0, y0] = xy[i]!;
          const x = t.applyX(x0);
          const y = t.applyY(y0);
          ctx.beginPath();
          ctx.arc(x, y, 3.2 * grow, 0, 2 * Math.PI);
          ctx.fill();
          if (t.k >= 6 && labelled.has(p.id)) ctx.fillText(label(p.labels, p.id), x + 6, y - 5);
        });
        if (pt) {
          const c = projection([pt.lon, pt.lat]);
          if (c) {
            const x = t.applyX(c[0]);
            const y = t.applyY(c[1]);
            ctx.strokeStyle = lac;
            ctx.lineWidth = 1.5;
            ctx.beginPath();
            ctx.moveTo(x - 9, y);
            ctx.lineTo(x + 9, y);
            ctx.moveTo(x, y - 9);
            ctx.lineTo(x, y + 9);
            ctx.stroke();
          }
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
      sel.call(z);
      if (state.current.point) {
        const c = projection([state.current.point.lon, state.current.point.lat]);
        if (c) sel.call(z.transform, zoomIdentity.translate(w / 2, h / 2).scale(8).translate(-c[0], -c[1]));
      }
      el.addEventListener("click", (ev) => {
        const rect = el.getBoundingClientRect();
        const mx = ev.clientX - rect.left;
        const my = ev.clientY - rect.top;
        // Snap to a dot under the pointer; otherwise ask about the spot itself.
        let best = -1;
        let bestD = 12 * 12;
        xy.forEach(([x0, y0], i) => {
          const d = (t.applyX(x0) - mx) ** 2 + (t.applyY(y0) - my) ** 2;
          if (d < bestD) {
            bestD = d;
            best = i;
          }
        });
        if (best >= 0) onPick({ lat: places[best]!.lat, lon: places[best]!.lon });
        else {
          const ll = projection.invert?.([t.invertX(mx), t.invertY(my)]);
          if (ll) onPick({ lat: Math.max(-90, Math.min(90, ll[1])), lon: ((ll[0] + 540) % 360) - 180 });
        }
      });
      const ro = new ResizeObserver(() => {
        size();
        draw();
      });
      ro.observe(holder);
      const mo = new MutationObserver(draw);
      mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
      redraw.current = draw;
      draw();
      cleanup = () => {
        ro.disconnect();
        mo.disconnect();
        sel.on(".zoom", null);
      };
    })();
    return () => cleanup();
    // The map is built once per set of places; selection changes only redraw it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [places]);

  useEffect(() => {
    state.current = { lit, point };
    redraw.current();
  }, [lit, point]);

  return (
    <div ref={box} className={s.map}>
      <canvas ref={canvas} role="img" aria-label={`Map of ${places.length} heritage places in and around India, drawn as dots`} />
    </div>
  );
}

function Nearby({ n }: { n: NearView }) {
  const far = n.places.length ? n.places[n.places.length - 1]!.distance_km : 0;
  const { nodes, edges } = useMemo(() => {
    const tied = new Set([...n.shared.flatMap((x) => x.members), ...n.links.flatMap((e) => [e.source, e.target])]);
    const nodes: CanvasNode[] = n.places.map((p) => ({ id: p.id, label: label(p.labels, p.id), size: 5 + Math.min(6, Math.sqrt(p.documents)), tone: "entity", important: tied.has(p.id) }));
    n.shared.forEach((x) => nodes.push({ id: x.node.id, label: label(x.node.labels, x.node.id), size: 4 + x.members.length, tone: "focus", important: true }));
    const seen = new Set(nodes.map((x) => x.id));
    const edges: CanvasEdge[] = [...n.links, ...n.shared_edges]
      .filter((e) => seen.has(e.source) && seen.has(e.target))
      .map((e) => ({ id: `${e.source}|${e.relation}|${e.target}`, source: e.source, target: e.target, label: e.relation_label }));
    return { nodes, edges };
  }, [n]);

  return (
    <div>
      <h2 className={s.nearTitle}>
        The <span className="num">{n.places.length}</span> nearest places, within <span className="num">{fmt(far, 1)}</span> km
      </h2>
      <div className={s.mini}>
        <GraphCanvas nodes={nodes} edges={edges} onSelect={() => {}} ariaLabel="How the nearby places are tied in the graph" labelOnlyImportant />
      </div>
      <p className={s.legend}>
        <Seal kind="graph">ties</Seal> places and what joins two or more of them; direct links between places are drawn too.
      </p>

      <h3 className={s.h3}>What ties them</h3>
      {n.shared.length === 0 && n.links.length === 0 ? <p className={s.muted}>The graph has no link among these places.</p> : null}
      <ul className={s.ties}>
        {n.shared.map((x) => (
          <li key={x.node.id}>
            <Link href={`/graph/?node=${encodeURIComponent(x.node.id)}`}>
              <Names labels={x.node.labels} fallback={x.node.id} />
            </Link>{" "}
            joins <span className="num">{x.members.length}</span>
            {x.node.hub ? <span className={s.muted}> (a hub)</span> : null}
          </li>
        ))}
      </ul>
      {n.periods.length ? (
        <>
          <h3 className={s.h3}>Centuries they share</h3>
          <p className={s.rail}>
            {n.periods.map((x) => (
              <span key={x.node.id}>
                {label(x.node.labels, x.node.id)} <span className="num">×{x.members.length}</span>
              </span>
            ))}
          </p>
        </>
      ) : null}
      <h3 className={s.h3}>The places</h3>
      <ol className={s.places}>
        {n.places.map((p) => (
          <li key={p.id}>
            <Link href={`/graph/?node=${encodeURIComponent(p.id)}`}>
              <Names labels={p.labels} fallback={p.id} />
            </Link>
            <span className={s.muted}>
              {" "}
              <span className="num">{fmt(p.distance_km, 1)}</span> km · <span className="num">{fmt(n.documents_per_place[p.id] ?? 0)}</span>{" "}
              {(n.documents_per_place[p.id] ?? 0) === 1 ? "document" : "documents"}
            </span>
          </li>
        ))}
      </ol>
      {n.documents_about_several.length ? (
        <>
          <h3 className={s.h3}>Documents about several of them</h3>
          <ul className={s.ties}>
            {n.documents_about_several.slice(0, 8).map((x) => (
              <li key={x.node.id}>
                <Link href={`/document/?id=${encodeURIComponent(x.node.id)}`}>{label(x.node.labels, x.node.id)}</Link>{" "}
                <span className={s.muted}>about {x.members.length}</span>
              </li>
            ))}
          </ul>
        </>
      ) : null}
      <MarginNote>
        <p>
          Nearness is distance on the globe from where you clicked. Ties come from the graph: a node counts as a tie when
          two or more of these places link to it. Centuries are listed apart, because one century can join almost
          everything nearby.
        </p>
      </MarginNote>
    </div>
  );
}
