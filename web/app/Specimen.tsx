"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { seedString } from "@/app/cases/model";
import { groupOf } from "@/components/LiveGraph";
import { api, label, type EgoView, type GraphRank, type Place, type SearchView } from "@/lib/api";
import { useResource, type Resource } from "@/lib/useResource";

import s from "./home.module.css";

/**
 * The home page's doors, as one question seen four ways (decision 0028: each door shows a small live picture of
 * what lies behind it). A reader learns what the site is by watching the same question go through the text lens,
 * the graph lens, the map and the analyser, and each door opens on exactly what it shows.
 */
const QUESTIONS = ["Hoysala temples Belur", "Mughal miniature painting", "मुगल किला आगरा", "ಹಂಪೆ ದೇವಾಲಯ", "Chola bronze Nataraja"];
const TOP = 3;

export function Specimen() {
  // Always opens on the first question, so the static page and the browser agree; "Another question" cycles.
  const [i, setI] = useState(0);
  const q = QUESTIONS[i % QUESTIONS.length] ?? "Hoysala temples Belur";

  const text = useResource(() => api.search(q, "bm25", undefined, TOP), `sp-text|${q}`);
  const linked = text.state === "ready" ? text.data.linked : null;
  const seedKey = linked && Object.keys(linked.seeds).length ? seedString(linked.seeds) : "";
  const graph = useResource(seedKey ? () => api.rank(seedKey, 1, 0.15, TOP) : null, `sp-graph|${seedKey}`);
  const first = linked?.mentions[0]?.candidates[0]?.id ?? null;
  const ego = useResource(first ? () => api.ego(first, 10) : null, `sp-ego|${first}`);
  const read = useResource(() => api.analyse(q), `sp-read|${q}`);
  const places = useResource(api.places, "places");

  const enc = encodeURIComponent(q);
  return (
    <section className={s.specimen} aria-labelledby="specimen-title">
      <header className={s.specimenHead}>
        <h2 id="specimen-title" className={s.specimenTitle}>
          One question, four ways of looking at it
        </h2>
        <p className={s.specimenQ}>
          <span className={s.specimenQText} lang={/[ऀ-ॿ]/.test(q) ? "hi" : /[ಀ-೿]/.test(q) ? "kn" : "en"}>
            “{q}”
          </span>
          <button type="button" className={s.another} onClick={() => setI((i + 1) % QUESTIONS.length)}>
            Another question
          </button>
        </p>
      </header>
      <div className={s.specimenDoors}>
        <Door href={`/cases/?q=${enc}`} name="Search" open="Open the case">
          <SearchPicture text={text} graph={seedKey ? graph : null} />
        </Door>
        <Door href={atlasHref(places, linked?.seeds)} name="Atlas" open="Open the map here">
          <AtlasPicture places={places} lit={linked ? Object.keys(linked.seeds) : null} />
        </Door>
        <Door href={first ? `/graph/?node=${encodeURIComponent(first)}` : "/graph/"} name="Graph" open="Walk from here">
          <GraphPicture ego={first ? ego : null} />
        </Door>
        <Door href="/lab/" name="Lab" open="Where reading goes wrong">
          <ReadPicture q={q} read={read} />
        </Door>
      </div>
    </section>
  );
}

function Door({ href, name, open, children }: { href: string; name: string; open: string; children: React.ReactNode }) {
  return (
    <Link href={href} className={s.sDoor}>
      <span className={s.sDoorName}>{name}</span>
      {children}
      <span className={s.sDoorOpen}>{open} →</span>
    </Link>
  );
}

function Wait({ res, lines = 3 }: { res: Resource<unknown> | null; lines?: number }) {
  if (res && (res.state === "unavailable" || res.state === "refused" || res.state === "failed")) {
    return <span className={s.sNote}>Not available: {res.state === "unavailable" ? res.error.reason : "the server did not answer"}</span>;
  }
  return (
    <span className={s.sSkeleton} aria-hidden>
      {Array.from({ length: lines }, (_, k) => (
        <i key={k} />
      ))}
    </span>
  );
}

/** The two lenses' top three, with a thread between any document both found. */
function SearchPicture({ text, graph }: { text: Resource<SearchView>; graph: Resource<GraphRank> | null }) {
  if (text.state !== "ready") return <Wait res={text} />;
  const left = text.data.results.slice(0, TOP).map((r) => ({ id: r.doc_id, title: r.title ?? r.doc_id }));
  const right =
    graph && graph.state === "ready" ? graph.data.results.slice(0, TOP).map((r) => ({ id: r.document.id, title: label(r.document.labels, r.document.id) })) : [];
  const shared = left.filter((l) => right.some((r) => r.id === l.id)).length;
  const row = 22;
  return (
    <>
      <span className={s.lenses} aria-hidden>
        <span className={s.lensName}>text</span>
        <span />
        <span className={`${s.lensName} ${s.lensNameGraph}`}>graph</span>
        <ol className={s.lens}>
          {left.map((r) => (
            <li key={r.id} className={right.some((x) => x.id === r.id) ? s.inBoth : undefined}>
              {r.title}
            </li>
          ))}
        </ol>
        <svg className={s.spine} viewBox={`0 0 24 ${row * TOP}`} preserveAspectRatio="none">
          {left.map((l, a) => {
            const b = right.findIndex((r) => r.id === l.id);
            return b < 0 ? null : <path key={l.id} d={`M0 ${row * a + row / 2} C12 ${row * a + row / 2}, 12 ${row * b + row / 2}, 24 ${row * b + row / 2}`} />;
          })}
        </svg>
        <ol className={`${s.lens} ${s.lensGraph}`}>
          {right.length ? right.map((r) => <li key={r.id}>{r.title}</li>) : <li className={s.sMuted}>{graph ? "…" : "no name to start from"}</li>}
        </ol>
      </span>
      <span className={s.sCaption}>
        Text lens and graph lens, top {TOP} each{right.length ? `: ${shared} found by both.` : "."}
      </span>
    </>
  );
}

const BOX = { west: 68, east: 98, south: 6, north: 37 };
const W = 120;
const H = 124;
const px = (lon: number) => ((lon - BOX.west) / (BOX.east - BOX.west)) * W;
const py = (lat: number) => H - ((lat - BOX.south) / (BOX.north - BOX.south)) * H;

/** Every placed entity as a speck; the places this question names, lit. */
function AtlasPicture({ places, lit }: { places: Resource<Place[]>; lit: string[] | null }) {
  const specks = useMemo(
    () =>
      places.state === "ready"
        ? places.data.filter((p) => p.lon >= BOX.west && p.lon <= BOX.east && p.lat >= BOX.south && p.lat <= BOX.north)
        : [],
    [places],
  );
  if (places.state !== "ready") return <Wait res={places} />;
  const on = specks.filter((p) => lit?.includes(p.id));
  return (
    <>
      <svg className={s.miniMap} viewBox={`0 0 ${W} ${H}`} aria-hidden>
        {specks.map((p) => (
          <circle key={p.id} cx={px(p.lon)} cy={py(p.lat)} r={0.55} />
        ))}
        {on.map((p) => (
          <g key={p.id} className={s.miniLit}>
            <circle cx={px(p.lon)} cy={py(p.lat)} r={5} />
            <circle cx={px(p.lon)} cy={py(p.lat)} r={1.8} />
          </g>
        ))}
      </svg>
      <span className={s.sCaption}>
        {lit == null
          ? "Finding the places it names…"
          : on.length
            ? `${on.map((p) => label(p.labels, p.id)).join(", ")}, among ${specks.length.toLocaleString("en-IN")} places.`
            : `It names no place with coordinates; ${specks.length.toLocaleString("en-IN")} places on the map.`}
      </span>
    </>
  );
}

function atlasHref(places: Resource<Place[]>, seeds: Record<string, number> | undefined): string {
  if (places.state !== "ready" || !seeds) return "/atlas/";
  const p = places.data.find((x) => x.id in seeds);
  return p ? `/atlas/?lat=${p.lat.toFixed(4)}&lon=${p.lon.toFixed(4)}` : "/atlas/";
}

/**
 * The first named entity and its neighbours on a circle: a fixed drawing, no layout to wait for. A hub's neighbours
 * come back from the server bundled by relation (decision 0025); a bundle is drawn hollow, sized by how many it holds.
 */
function GraphPicture({ ego }: { ego: Resource<EgoView> | null }) {
  if (!ego) return <span className={s.sNote}>The question names nothing the graph knows, so the graph lens has no place to start.</span>;
  if (ego.state !== "ready") return <Wait res={ego} />;
  const centre = ego.data.nodes.find((n) => n.id === ego.data.center);
  const around = ego.data.nodes.filter((n) => n.id !== ego.data.center).slice(0, 10);
  const bundles = ego.data.bundles.slice(0, Math.max(0, 12 - around.length));
  const total = around.length + bundles.length;
  const r = 34;
  const at = (k: number) => {
    const a = (2 * Math.PI * k) / Math.max(total, 1) - Math.PI / 2;
    return { x: 60 + r * Math.cos(a), y: 44 + r * Math.sin(a) };
  };
  const spots = around.map((n, k) => ({ n, ...at(k) }));
  const groups = bundles.map((b, k) => ({ b, ...at(around.length + k), size: 2.5 + Math.min(5, Math.log10(b.count + 1) * 2.2) }));
  const inBundles = bundles.reduce((sum, b) => sum + b.count, 0);
  return (
    <>
      <svg className={s.miniGraph} viewBox="0 0 120 88" aria-hidden>
        {[...spots, ...groups].map(({ x, y }, k) => (
          <line key={k} x1={60} y1={44} x2={x} y2={y} />
        ))}
        {spots.map(({ n, x, y }) => (
          <circle key={n.id} cx={x} cy={y} r={3.6} className={s[`n_${groupOf(n.kind, n.type)}`]} />
        ))}
        {groups.map(({ b, x, y, size }) => (
          <circle key={`${b.relation}-${b.direction}-${b.kind}`} cx={x} cy={y} r={size} className={s.nBundle} />
        ))}
        <circle cx={60} cy={44} r={6} className={s.nCentre} />
      </svg>
      <span className={s.sCaption}>
        {centre ? label(centre.labels, centre.id) : ego.data.center}: {ego.data.neighbours.toLocaleString("en-IN")} neighbours
        {inBundles ? `, ${inBundles.toLocaleString("en-IN")} of them in ${bundles.length} ${bundles.length === 1 ? "group" : "groups"} (hollow)` : ""}.
      </span>
    </>
  );
}

/** What the text lens actually searches for: the question after analysis, words it changed marked. */
function ReadPicture({ q, read }: { q: string; read: Resource<{ tokens: string[]; language: string }> }) {
  if (read.state !== "ready") return <Wait res={read} lines={2} />;
  const words = q.toLowerCase().split(/\s+/);
  const changed = read.data.tokens.filter((t) => !words.includes(t)).length;
  return (
    <>
      <span className={s.tokens} aria-hidden>
        {read.data.tokens.map((t, k) => (
          <code key={k} className={words.includes(t) ? undefined : s.tokenChanged}>
            {t}
          </code>
        ))}
      </span>
      <span className={s.sCaption}>
        What the text lens searches for{changed ? `: ${changed} ${changed === 1 ? "word" : "words"} cut to a stem` : ", word for word"}.
      </span>
    </>
  );
}
