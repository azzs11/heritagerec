"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Load, fmt } from "@/components/ui";
import { api, get, label, type NodeCard } from "@/lib/api";
import { SOURCES } from "@/lib/names";
import { useStored } from "@/lib/stored";
import { useResource } from "@/lib/useResource";

import s from "./home.module.css";
import { Specimen } from "./Specimen";
import { ThreadFromTheGraph } from "./Thread";

const EXAMPLES = ["Hoysala temples Belur", "Mughal miniature painting", "मुगल किला आगरा", "ಹಂಪೆ ದೇವಾಲಯ"];
const PAGE = 24;

interface Item extends NodeCard {
  period?: [number | null, number | null];
  source?: string;
}

export default function Home() {
  const router = useRouter();
  const [q, setQ] = useState("");
  const stats = useResource(api.corpusStats, "stats");
  const health = useResource(api.health, "health");
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (q.trim()) router.push(`/cases/?q=${encodeURIComponent(q.trim())}`);
  };

  return (
    <div className="page">
      <FirstVisit />
      <section className={s.search}>
        <form onSubmit={submit} role="search" className={s.form}>
          <label htmlFor="home-q" className={s.prompt}>
            Search{" "}
            {stats.state === "ready" ? <span className="num">{fmt(Number(stats.data.snapshot.records))}</span> : null}{" "}
            documents on India&apos;s heritage, in English, हिन्दी or ಕನ್ನಡ
          </label>
          <div className={s.row}>
            <input id="home-q" value={q} onChange={(e) => setQ(e.target.value)} autoComplete="off" placeholder="Hoysala temples Belur" />
            <button type="submit">Search</button>
          </div>
        </form>
        <p className={s.examples}>
          {EXAMPLES.map((x) => (
            <Link key={x} href={`/cases/?q=${encodeURIComponent(x)}`}>
              {x}
            </Link>
          ))}
        </p>
      </section>

      <Specimen />

      <ThreadFromTheGraph />

      <Wall />

      <section className={s.study}>
        <div className="read">
          <h2 className={s.studyTitle}>What this is</h2>
          <p>
            A test of one question: does a knowledge graph find better documents than words alone? Every search here
            is answered twice, by a text lens that reads words and a graph lens that follows facts from Wikidata, and
            every step of both is shown.
          </p>
          <p>
            No verdict yet. The benchmark&apos;s questions and judgements are still being made, so the site measures
            nothing it cannot show. <Link href="/ledger/">The Ledger</Link> lists what exists, and{" "}
            <Link href="/lab/">the Lab</Link> where it already breaks.
          </p>
        </div>
        <dl className={s.facts}>
          <Load res={stats} what="the counts">
            {(m) => (
              <>
                <div title={`from ${m.source_file}`}>
                  <dt>documents</dt>
                  <dd className="num">{fmt(Number(m.snapshot.records))}</dd>
                </div>
                <div title={`from ${m.source_file}`}>
                  <dt>sources</dt>
                  <dd className="num">{Object.keys(m.by_source).length}</dd>
                </div>
                <div title={`from ${m.source_file}`}>
                  <dt>Hindi · Kannada</dt>
                  <dd className="num">
                    {fmt(m.by_language.hi ?? 0)} · {fmt(m.by_language.kn ?? 0)}
                  </dd>
                </div>
              </>
            )}
          </Load>
          {health.state === "ready" && health.data.graph.status === "ok" ? (
            <>
              <div title="from data/graph/core_v1 and data/explorer/v1">
                <dt>graph nodes · facts</dt>
                <dd className="num">
                  {fmt(Number(health.data.graph.nodes))} · {fmt(Number(health.data.graph.edges))}
                </dd>
              </div>
              <div title="from data/explorer/v1/nodes.jsonl.gz">
                <dt>places on the map</dt>
                <dd className="num">{fmt(Number(health.data.graph.placed))}</dd>
              </div>
            </>
          ) : null}
        </dl>
      </section>
    </div>
  );
}

function Wall() {
  const [pages, setPages] = useState(1);
  const first = useResource(() => get<{ total: number; items: Item[] }>("/api/collection", { offset: 0, limit: PAGE }), "wall0");
  const [more, setMore] = useState<Item[]>([]);
  const [busy, setBusy] = useState(false);
  const loadMore = async () => {
    setBusy(true);
    try {
      const r = await get<{ items: Item[] }>("/api/collection", { offset: pages * PAGE, limit: PAGE });
      setMore((m) => [...m, ...r.items]);
      setPages((p) => p + 1);
    } finally {
      setBusy(false);
    }
  };
  return (
    <section aria-label="Objects from the collection" className={s.wallSection}>
      <Load res={first} what="the collection">
        {(r) => (
          <>
            <p className={s.wallHead}>
              From the collection: <span className="num">{fmt(r.total)}</span> objects with open images, from The Met and
              the Cleveland Museum of Art
            </p>
            <ul className={s.wall}>
              {[...r.items, ...more].map((x) => (
                <Tile key={x.id} x={x} />
              ))}
            </ul>
            {pages * PAGE < r.total ? (
              <button className={s.more} onClick={loadMore} disabled={busy}>
                {busy ? "Loading…" : "More objects"}
              </button>
            ) : null}
          </>
        )}
      </Load>
    </section>
  );
}

function Tile({ x }: { x: Item }) {
  // A museum's server can refuse an image (the Met's bot protection sometimes does); such a tile is dropped
  // rather than shown broken.
  const [failed, setFailed] = useState(false);
  const im = x.image;
  if (!im || failed) return null;
  const [from, to] = x.period ?? [null, null];
  const when = from == null ? null : to != null && to !== from ? `${from}–${to}` : `${from}`;
  return (
    <li className={s.tile}>
      <Link href={`/document/?id=${encodeURIComponent(x.id)}`}>
        {/* Remote museum images in a static site: next/image's optimiser is not available here. */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={im.thumb}
          alt={label(x.labels, x.id)}
          loading="lazy"
          decoding="async"
          referrerPolicy="no-referrer"
          width={im.width ?? undefined}
          height={im.height ?? undefined}
          onError={() => setFailed(true)}
        />
        <span className={s.caption}>
          <span className={s.title}>{label(x.labels, x.id)}</span>
          <span className={s.meta}>
            {when ? <span className="num">{when}</span> : null}
            {when ? " · " : null}
            {SOURCES[x.source ?? ""] ?? x.source}
          </span>
        </span>
      </Link>
    </li>
  );
}

/** Offered once: a pointer to the five-step guide. */
function FirstVisit() {
  const [offered, setOffered] = useStored("guide-offered", "unknown");
  if (offered === "yes") return null;
  return (
    <aside className={s.firstVisit} aria-label="First visit">
      <span>
        First time here? <Link href="/guide/" onClick={() => setOffered("yes")}>Five steps</Link> show what each part
        does.
      </span>
      <button onClick={() => setOffered("yes")} aria-label="Dismiss">
        ×
      </button>
    </aside>
  );
}
