"use client";

import Link from "next/link";
import { useState } from "react";

import { Load, MarginNote, Names, Seal } from "@/components/ui";
import { api, label, stepLabel, type GraphRank, type NodeCard } from "@/lib/api";
import { useResource } from "@/lib/useResource";

import s from "./cases.module.css";

const HUB = [
  [1, "inverse frequency"],
  [0.5, "half"],
  [0, "none"],
] as const;
const RESTART = [0.1, 0.15, 0.3] as const;

/** Personalised PageRank from entities the reader picks, until the query linker exists (decisions 0026, 0027). */
export function GraphLens({
  seeds,
  setSeeds,
  suggestions,
}: {
  seeds: string[];
  setSeeds: (s: string[]) => void;
  suggestions: NodeCard[];
}) {
  const [hub, setHub] = useState<number>(1);
  const [restart, setRestart] = useState<number>(0.15);
  const key = `${seeds.join(";")}|${hub}|${restart}`;
  const res = useResource(seeds.length ? () => api.rank(seeds, hub, restart, 10) : null, seeds.length ? key : "none");
  const add = (id: string) => !seeds.includes(id) && setSeeds([...seeds, id].slice(0, 10));
  const offered = suggestions.filter((n) => !seeds.includes(n.id)).slice(0, 8);

  return (
    <div>
      <p className={s.muted}>
        <Seal kind="pending">linker not built</Seal> The query linker (decision 0026) is not built, so you choose where
        the walk starts. The ranking below is the real system on the real graph; only its starting points come from
        you.
      </p>
      <SeedPicker seeds={seeds} setSeeds={setSeeds} onAdd={add} />
      {offered.length ? (
        <p className={s.suggest}>
          <span className={s.muted}>start from what the text lens&apos;s answers are about:</span>
          {offered.map((n) => (
            <button key={n.id} onClick={() => add(n.id)} className={s.chipAdd}>
              + <Names labels={n.labels} fallback={n.id} />
            </button>
          ))}
        </p>
      ) : null}
      {seeds.length ? (
        <>
          <div className={s.settings}>
            <div role="group" aria-label="Hub down-weighting" className={s.switchSmall}>
              <span className={s.muted}>hubs:</span>
              {HUB.map(([v, name]) => (
                <button key={v} aria-pressed={hub === v} onClick={() => setHub(v)}>
                  {name}
                </button>
              ))}
            </div>
            <div role="group" aria-label="Restart probability" className={s.switchSmall}>
              <span className={s.muted}>restart:</span>
              {RESTART.map((v) => (
                <button key={v} aria-pressed={restart === v} onClick={() => setRestart(v)}>
                  {v}
                </button>
              ))}
            </div>
          </div>
          <Load res={res} what="the walk">
            {(r) => <Ranked r={r} />}
          </Load>
        </>
      ) : null}
    </div>
  );
}

function SeedPicker({ seeds, setSeeds, onAdd }: { seeds: string[]; setSeeds: (s: string[]) => void; onAdd: (id: string) => void }) {
  const [q, setQ] = useState("");
  const found = useResource(q.trim().length >= 2 ? () => api.find(q.trim()) : null, `seedfind|${q.trim()}`);
  const cards = useResource(seeds.length ? () => Promise.all(seeds.map((id) => api.node(id))) : null, `seedcards|${seeds.join(";")}`);
  return (
    <div className={s.picker}>
      {seeds.length && cards.state === "ready" ? (
        <ul className={s.chips} aria-label="Where the walk starts">
          {cards.data.map((n) => (
            <li key={n.id}>
              <Names labels={n.labels} fallback={n.id} />
              <button aria-label={`Remove ${label(n.labels, n.id)}`} onClick={() => setSeeds(seeds.filter((x) => x !== n.id))}>
                ×
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      <label className="visually-hidden" htmlFor="seed">
        Add an entity to start from
      </label>
      <input id="seed" className={s.seedInput} value={q} onChange={(e) => setQ(e.target.value)} placeholder="add a place, dynasty, style…" autoComplete="off" />
      {q.trim().length >= 2 && found.state === "ready" ? (
        <ul className={s.seedFound}>
          {found.data
            .filter((n) => n.kind !== "document")
            .slice(0, 8)
            .map((n) => (
              <li key={n.id}>
                <button onClick={() => (onAdd(n.id), setQ(""))}>
                  <Names labels={n.labels} fallback={n.id} /> <span className={s.muted}>{n.type ?? n.kind}</span>
                </button>
              </li>
            ))}
        </ul>
      ) : null}
    </div>
  );
}

function Ranked({ r }: { r: GraphRank }) {
  if (!r.results.length) return <p>The walk reached no document from these entities.</p>;
  return (
    <>
      <ol className={s.results}>
        {r.results.map((x) => {
          const p = x.path?.paths[0];
          return (
            <li key={x.document.id} className={s.result}>
              <div className={s.resultHead}>
                <span className={`${s.rank} num`}>{x.rank}</span>
                <div className={s.resultTitle}>
                  <Link href={`/document/?id=${encodeURIComponent(x.document.id)}`}>{label(x.document.labels, x.document.id)}</Link>
                </div>
                <span className={`${s.scoreGraph} num`} title="share of the walk spent on this document">
                  {x.score.toFixed(4)}
                </span>
              </div>
              {p ? (
                <p className={s.pathLine}>
                  {p.nodes.map((n, i) => (
                    <span key={n.id}>
                      {i && p.edges[i - 1] ? <em> {stepLabel(p.edges[i - 1]!, p.nodes[i - 1]!.id)} </em> : null}
                      {label(n.labels, n.id)}
                    </span>
                  ))}
                  {x.path?.through_hubs ? <Seal kind="pending">through a hub</Seal> : null}
                </p>
              ) : (
                <p className={s.muted}>no path of four steps or fewer from a seed</p>
              )}
            </li>
          );
        })}
      </ol>
      {r.walk_spends_time_at.length ? (
        <p className={s.suggest}>
          <span className={s.muted}>the walk spends most time at:</span>
          {r.walk_spends_time_at.map((w) => (
            <Link key={w.node.id} href={`/graph/?node=${encodeURIComponent(w.node.id)}`} className={s.timeAt}>
              {label(w.node.labels, w.node.id)} <span className="num">{(100 * w.share).toFixed(1)}%</span>
            </Link>
          ))}
        </p>
      ) : null}
      <MarginNote>
        <p>
          A walker starts at your entities and moves along the graph&apos;s facts, jumping back to a start with the
          restart probability at every step. A document&apos;s score is the share of time the walk spends on it. With
          hubs down-weighted, a step into a very common node (a century, a state, India) is made less likely, so the
          walk is not carried everywhere by them.
        </p>
        <p>The path under each result is the shortest chain of facts from one of your entities to it.</p>
      </MarginNote>
    </>
  );
}
