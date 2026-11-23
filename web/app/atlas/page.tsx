"use client";

import Link from "next/link";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useMemo, useRef, useState } from "react";

import { HexRings } from "@/components/HexRings";
import { GROUP_NAMES, LiveGraph, groupOf, type Group, type LiveEdge, type LiveNode } from "@/components/LiveGraph";
import { Load, MarginNote, Names, fmt } from "@/components/ui";
import { NextSteps } from "@/components/Wayfinding";
import { api, label, type NearView, type Place } from "@/lib/api";
import { useTrailStep } from "@/lib/trail";
import { useResource } from "@/lib/useResource";

import { AtlasMap, type Hover, type MapHandle } from "./AtlasMap";
import s from "./atlas.module.css";

const GROUPS: ("built" | "people" | "culture" | "other")[] = ["built", "people", "culture", "other"];

function century(c: number): string {
  const n = Math.abs(c);
  const suffix = n % 100 >= 11 && n % 100 <= 13 ? "th" : (({ 1: "st", 2: "nd", 3: "rd" }) as Record<number, string>)[n % 10] ?? "th";
  return `${n}${suffix} c.${c < 0 ? " BCE" : ""}`;
}

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
  const point = useMemo(
    () => (lat && lon && Number.isFinite(+lat) && Number.isFinite(+lon) ? { lat: +lat, lon: +lon } : null),
    [lat, lon],
  );
  const places = useResource(api.places, "places");
  const goTo = useCallback(
    (p: { lat: number; lon: number } | null) =>
      router.push(p ? `/atlas/?lat=${p.lat.toFixed(5)}&lon=${p.lon.toFixed(5)}` : "/atlas/", { scroll: false }),
    [router],
  );
  return (
    <article className={s.full}>
      <h1 className="visually-hidden">Atlas</h1>
      <Load res={places} what="the places">
        {(ps) => <AtlasBody places={ps} point={point} goTo={goTo} />}
      </Load>
    </article>
  );
}

function AtlasBody({ places, point, goTo }: { places: Place[]; point: { lat: number; lon: number } | null; goTo: (p: { lat: number; lon: number } | null) => void }) {
  const reduce = useReducedMotion();
  const map = useRef<MapHandle>(null);
  const [groups, setGroups] = useState<Set<string>>(new Set(GROUPS));
  const span = useMemo(() => {
    const all = places.flatMap((p) => p.centuries);
    return [Math.min(...all), Math.max(...all)] as const;
  }, [places]);
  const [range, setRange] = useState<[number, number]>([span[0], span[1]]);
  const [undated, setUndated] = useState(true);
  const [hover, setHover] = useState<Hover | null>(null);
  const near = useResource(point ? () => api.near(point.lat, point.lon, 25) : null, point ? `near|${point.lat}|${point.lon}` : "none");
  const lit = useMemo(() => (near.state === "ready" ? near.data.places.map((p) => p.id) : []), [near]);

  const filtered = range[0] !== span[0] || range[1] !== span[1];
  const visible = useCallback(
    (p: Place): "on" | "faint" | "off" => {
      if (!groups.has(groupOf("entity", p.type))) return "off";
      if (!p.centuries.length) return undated ? (filtered ? "faint" : "on") : "off";
      return p.centuries.some((c) => c >= range[0] && c <= range[1]) ? "on" : "faint";
    },
    [groups, range, undated, filtered],
  );
  const dated = places.filter((p) => p.centuries.length).length;
  const inRange = places.filter((p) => p.centuries.length && visible(p) === "on").length;
  const toggle = (g: string) => {
    const next = new Set(groups);
    if (next.has(g)) next.delete(g);
    else next.add(g);
    if (next.size) setGroups(next);
  };

  return (
    <div className={s.stage}>
      <AtlasMap ref={map} places={places} visible={visible} lit={lit} point={point} onPick={goTo} onHover={setHover} />

      <div className={`${s.float} ${s.topLeft}`}>
        <PlaceFinder onPick={goTo} />
        <ul className={s.legend} aria-label="Kinds of place, click to show or hide">
          {GROUPS.map((g) => (
            <li key={g}>
              <button aria-pressed={groups.has(g)} onClick={() => toggle(g)}>
                <i className={s[`g_${g}`]} aria-hidden />
                {GROUP_NAMES[g]}
              </button>
            </li>
          ))}
        </ul>
        {/* Far out the map shows counts, not kinds; without this key the coloured chips above read as the hexagons' colours. */}
        <div className={s.densityKey}>
          <span>Far out, shade counts places per hexagon:</span>
          <span className={s.ramp} aria-hidden>
            fewer
            {[0.1, 0.33, 0.57, 0.8].map((a) => (
              <i key={a} style={{ opacity: a }} />
            ))}
            more
          </span>
          <span>Zoom in to see each place, coloured by kind.</span>
        </div>
      </div>

      <div className={`${s.float} ${s.bottomLeft}`}>
        <div className={s.period}>
          <span className={s.periodName}>Period</span>
          <span className={s.periodValue}>
            {century(range[0])} – {century(range[1])}
          </span>
          <div className={s.slider}>
            <input type="range" min={span[0]} max={span[1]} value={range[0]} aria-label="Earliest century" onChange={(e) => setRange([Math.min(+e.target.value, range[1]), range[1]])} />
            <input type="range" min={span[0]} max={span[1]} value={range[1]} aria-label="Latest century" onChange={(e) => setRange([range[0], Math.max(+e.target.value, range[0])])} />
          </div>
          <p className={s.periodNote}>
            <span className="num">{fmt(dated)}</span> of <span className="num">{fmt(places.length)}</span> places have a
            recorded century; <span className="num">{fmt(inRange)}</span> fall in this period.
          </p>
          <label className={s.check}>
            <input type="checkbox" checked={undated} onChange={(e) => setUndated(e.target.checked)} /> show places with no recorded century
            {filtered && undated ? " (faint)" : ""}
          </label>
        </div>
      </div>

      <div className={`${s.float} ${s.bottomRight} ${point ? s.shifted : ""}`} role="group" aria-label="Zoom">
        <button onClick={() => map.current?.zoomBy(1.8)} aria-label="Zoom in">
          +
        </button>
        <button onClick={() => map.current?.zoomBy(1 / 1.8)} aria-label="Zoom out">
          −
        </button>
        <button onClick={() => (map.current?.reset(), goTo(null))} aria-label="Show all of India">
          ⤢
        </button>
      </div>

      {hover ? (
        <div className={s.tip} style={{ transform: `translate(${hover.x + 14}px, ${hover.y + 14}px)` }} role="tooltip">
          <b>{label(hover.place.labels, hover.place.id)}</b>
          <span>
            {hover.place.type ?? "place"}
            {hover.place.centuries.length ? ` · ${century(hover.place.centuries[0]!)}${hover.place.centuries.length > 1 ? " …" : ""}` : ""}
            {` · ${fmt(hover.place.documents)} ${hover.place.documents === 1 ? "document" : "documents"}`}
          </span>
        </div>
      ) : null}

      <AnimatePresence>
        {point ? (
          <motion.aside
            key="drawer"
            className={s.drawer}
            initial={reduce ? false : { x: 40, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={reduce ? { opacity: 0 } : { x: 40, opacity: 0 }}
            transition={{ duration: 0.32, ease: [0.2, 0.8, 0.2, 1] }}
            aria-label="Places near the chosen point"
          >
            <button className={s.closeDrawer} onClick={() => goTo(null)} aria-label="Close">
              ×
            </button>
            <Load res={near} what="the places nearby">
              {(n) => <Nearby n={n} />}
            </Load>
          </motion.aside>
        ) : (
          <motion.p key="hint" className={s.hint} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            Click anywhere on the map, or find a place, to see what lies near it and what ties it together.
          </motion.p>
        )}
      </AnimatePresence>
    </div>
  );
}

function PlaceFinder({ onPick }: { onPick: (p: { lat: number; lon: number }) => void }) {
  const [q, setQ] = useState("");
  const res = useResource(q.trim().length >= 2 ? () => api.find(q.trim()) : null, `pf|${q.trim()}`);
  const placed = res.state === "ready" ? res.data.filter((n) => n.lat != null) : [];
  return (
    <div className={s.finder}>
      <label htmlFor="place" className="visually-hidden">
        Go to a place
      </label>
      <input id="place" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Go to a place: Belur, बेलूर, ಬೇಲೂರು" autoComplete="off" />
      {q.trim().length >= 2 && res.state === "ready" ? (
        <ul className={s.found}>
          {placed.length === 0 ? <li className={s.muted}>no place by that name on the map</li> : null}
          {placed.slice(0, 8).map((n) => (
            <li key={n.id}>
              <button onClick={() => (setQ(""), onPick({ lat: n.lat!, lon: n.lon! }))}>
                <i className={s[`g_${groupOf(n.kind, n.type)}`]} aria-hidden /> <Names labels={n.labels} fallback={n.id} />
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

/**
 * From the map to the place itself, for a reader planning a visit: OpenStreetMap (open data, no account) at the place
 * and a route to it. The coordinates are Wikidata's, as everywhere on the atlas.
 */
function GoThere({ name, lat, lon }: { name: string; lat: number; lon: number }) {
  const at = `${lat.toFixed(5)}/${lon.toFixed(5)}`;
  return (
    <p className={s.goThere}>
      Go to {name}:{" "}
      <a href={`https://www.openstreetmap.org/?mlat=${lat.toFixed(5)}&mlon=${lon.toFixed(5)}#map=16/${at}`} target="_blank" rel="noreferrer">
        on OpenStreetMap ↗
      </a>{" "}
      ·{" "}
      <a href={`https://www.openstreetmap.org/directions?route=%3B${lat.toFixed(5)}%2C${lon.toFixed(5)}`} target="_blank" rel="noreferrer">
        directions ↗
      </a>
    </p>
  );
}

function Nearby({ n }: { n: NearView }) {
  const here = n.places[0];
  useTrailStep(here ? { kind: "place", label: label(here.labels, here.id), href: `/atlas/?lat=${n.point.lat}&lon=${n.point.lon}` } : null);
  const far = n.places.length ? n.places[n.places.length - 1]!.distance_km : 0;
  const { nodes, edges } = useMemo(() => {
    const tied = new Set([...n.shared.flatMap((x) => x.members), ...n.links.flatMap((e) => [e.source, e.target])]);
    const nodes: LiveNode[] = n.places
      .filter((p) => tied.has(p.id))
      .map((p) => ({ id: p.id, label: label(p.labels, p.id), group: groupOf(p.kind, p.type) as Group, size: 5 + Math.min(5, Math.sqrt(p.documents)) }));
    n.shared.forEach((x) =>
      nodes.push({ id: x.node.id, label: label(x.node.labels, x.node.id), group: groupOf(x.node.kind, x.node.type), size: 6 + x.members.length, hub: true }),
    );
    const ids = new Set(nodes.map((x) => x.id));
    const edges: LiveEdge[] = [...n.links, ...n.shared_edges]
      .filter((e) => ids.has(e.source) && ids.has(e.target))
      .map((e) => ({ id: `${e.source < e.target ? e.source : e.target}|${e.source < e.target ? e.target : e.source}`, source: e.source, target: e.target, label: e.relation_label }));
    return { nodes, edges };
  }, [n]);

  return (
    <div className={s.nearby}>
      <p className={s.eyebrow}>near {here ? <Names labels={here.labels} fallback={here.id} /> : "this point"}</p>
      <h2 className={s.nearTitle}>
        <span className="num">{n.places.length}</span> places within <span className="num">{fmt(far, 1)}</span> km
      </h2>
      {here?.lat != null && here.lon != null ? <GoThere name={label(here.labels, here.id)} lat={here.lat} lon={here.lon} /> : null}

      {n.photos.length ? (
        <ul className={s.photos} aria-label="Objects linked to these places">
          {n.photos.map((d) => (
            <li key={d.id}>
              <Link href={`/document/?id=${encodeURIComponent(d.id)}`} title={label(d.labels, d.id)}>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={d.image!.thumb}
                  alt={label(d.labels, d.id)}
                  loading="lazy"
                  referrerPolicy="no-referrer"
                  onError={(e) => ((e.currentTarget.closest("li") as HTMLElement).style.display = "none")}
                />
              </Link>
            </li>
          ))}
        </ul>
      ) : (
        <p className={s.muted}>No museum object in the archive is linked to these places.</p>
      )}

      <h3 className={s.h3}>What ties them</h3>
      {nodes.length > 1 ? (
        <div className={s.mini}>
          <LiveGraph nodes={nodes} edges={edges} onSelect={() => {}} focusOnSelect={false} ariaLabel="How the nearby places are tied in the graph" />
        </div>
      ) : null}
      {n.shared.length === 0 && n.links.length === 0 ? <p className={s.muted}>The graph records no fact joining these places.</p> : null}
      <ul className={s.ties}>
        {n.shared.map((x) => (
          <li key={x.node.id}>
            <Link href={`/graph/?node=${encodeURIComponent(x.node.id)}`}>
              <Names labels={x.node.labels} fallback={x.node.id} />
            </Link>{" "}
            <span className={s.muted}>
              joins {x.members.length}
              {x.node.hub ? ", a hub" : ""}
            </span>
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
      <AtlasRings lat={n.point.lat} lon={n.point.lon} />
      <h3 className={s.h3}>The places</h3>
      <ol className={s.places}>
        {n.places.map((p) => (
          <li key={p.id}>
            <i className={s[`g_${groupOf(p.kind, p.type)}`]} aria-hidden />
            <Link href={`/graph/?node=${encodeURIComponent(p.id)}`}>
              <Names labels={p.labels} fallback={p.id} />
            </Link>
            <span className={`${s.km} num`}>{fmt(p.distance_km, 1)} km</span>
          </li>
        ))}
      </ol>
      {here ? (
        <NextSteps
          steps={[
            {
              label: `Documents about ${label(here.labels, here.id)}`,
              href: `/cases/?q=${encodeURIComponent(label(here.labels, here.id))}&seeds=${encodeURIComponent(here.id)}`,
              hint: "both lenses, starting here",
            },
            { label: "Open it in the graph", href: `/graph/?node=${encodeURIComponent(here.id)}`, hint: "its facts and neighbours" },
          ]}
        />
      ) : null}
      <MarginNote>
        <p>
          Nearness is distance on the globe from the chosen point: the 25 nearest places that are not hubs, however far
          that reaches. A fact ties two places when both link to the same entity; centuries are listed apart, since one
          century can join almost everything.
        </p>
        <p>
          No borders are drawn: India&apos;s boundaries must follow the Survey of India, whose boundary data needs a
          licence. The places themselves make the map.
        </p>
      </MarginNote>
    </div>
  );
}

/** The same neighbourhood counted in hexagons: the point's own cell, then each ring around it. */
function AtlasRings({ lat, lon }: { lat: number; lon: number }) {
  const r = useResource(() => api.rings(lat, lon, 2), `rings|${lat}|${lon}`);
  if (r.state !== "ready") return null;
  return (
    <HexRings
      title="Ring by ring"
      unit="places"
      bands={r.data.rings.map((b) => ({
        ring: b.ring,
        total: b.total,
        items: (b.places ?? []).slice(0, 6).map((p) => (
          <Link key={p.id} className={s.ringChip} href={`/graph/?node=${encodeURIComponent(p.id)}`}>
            {label(p.labels, p.id)}
          </Link>
        )),
      }))}
    />
  );
}
