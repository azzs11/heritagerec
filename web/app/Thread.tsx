"use client";

import Link from "next/link";
import { motion, useReducedMotion } from "motion/react";
import { useState } from "react";

import { groupOf } from "@/components/LiveGraph";
import { api, get, label, stepLabel, type GraphEdge, type NodeCard } from "@/lib/api";
import { useResource } from "@/lib/useResource";

import s from "./home.module.css";

interface Thread {
  object: NodeCard;
  entity: NodeCard;
  place: NodeCard | null;
  fact: GraphEdge | null;
}

/** Follows the graph from a random museum object to what it is about, and on to a place joined to that by a fact. */
async function pull(): Promise<Thread | null> {
  for (let attempt = 0; attempt < 5; attempt++) {
    const at = Math.floor(Math.random() * 6000);
    const page = await get<{ items: NodeCard[] }>("/api/collection", { offset: at, limit: 1 });
    const object = page.items[0];
    if (!object) continue;
    const about = await api.ego(object.id, 12, "about");
    const entity = about.nodes.find((n) => n.kind !== "document");
    if (!entity) continue;
    const around = await api.ego(entity.id, 60);
    const step = around.edges
      .map((e) => ({ e, other: around.nodes.find((n) => n.id === (e.source === entity.id ? e.target : e.source)) }))
      .filter((x) => x.other && x.other.kind !== "document" && x.other.kind !== "period" && !x.other.hub && x.other.id !== entity.id)
      .sort((a, b) => Number(b.other!.lat != null) - Number(a.other!.lat != null) || b.other!.documents - a.other!.documents)[0];
    return { object, entity, place: step?.other ?? null, fact: step?.e ?? null };
  }
  return null;
}

export function ThreadFromTheGraph() {
  const reduce = useReducedMotion();
  const [round, setRound] = useState(0);
  const res = useResource(() => pull(), `thread|${round}`);
  const card = (i: number) => ({
    initial: reduce ? false : { opacity: 0, y: 10 },
    animate: { opacity: 1, y: 0 },
    transition: { duration: 0.42, delay: reduce ? 0 : 0.35 * i, ease: [0.2, 0.8, 0.2, 1] as const },
  });
  return (
    <section className={s.thread} aria-label="A thread from the graph">
      <div className={s.threadHead}>
        <h2 className={s.threadTitle}>A thread from the graph</h2>
        <button className={s.another} onClick={() => setRound((r) => r + 1)}>
          Pull another ↻
        </button>
      </div>
      {res.state !== "ready" || !res.data ? (
        <div className={s.threadSkeleton} aria-busy="true" />
      ) : (
        <ol className={s.threadRow} key={round}>
          <motion.li {...card(0)} className={s.tCard}>
            <Link href={`/document/?id=${encodeURIComponent(res.data.object.id)}`}>
              {res.data.object.image ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={res.data.object.image.thumb} alt="" referrerPolicy="no-referrer" onError={(e) => (e.currentTarget.style.visibility = "hidden")} />
              ) : null}
              <span className={s.tKind}>museum object</span>
              <span className={s.tName}>{label(res.data.object.labels, res.data.object.id)}</span>
            </Link>
          </motion.li>
          <motion.li {...card(1)} className={s.tLink} aria-hidden>
            <span>is about</span>
          </motion.li>
          <motion.li {...card(2)} className={s.tCard}>
            <Link href={`/graph/?node=${encodeURIComponent(res.data.entity.id)}`}>
              <i className={s[`dot_${groupOf(res.data.entity.kind, res.data.entity.type)}`]} aria-hidden />
              <span className={s.tKind}>{res.data.entity.type ?? "entity"}</span>
              <span className={s.tName}>{label(res.data.entity.labels, res.data.entity.id)}</span>
              <span className={s.tMeta}>{res.data.entity.documents} documents about it</span>
            </Link>
          </motion.li>
          {res.data.place && res.data.fact ? (
            <>
              <motion.li {...card(3)} className={s.tLink} aria-hidden>
                <span>{stepLabel(res.data.fact, res.data.entity.id)}</span>
              </motion.li>
              <motion.li {...card(4)} className={s.tCard}>
                <Link
                  href={
                    res.data.place.lat != null
                      ? `/atlas/?lat=${res.data.place.lat}&lon=${res.data.place.lon}`
                      : `/graph/?node=${encodeURIComponent(res.data.place.id)}`
                  }
                >
                  <i className={s[`dot_${groupOf(res.data.place.kind, res.data.place.type)}`]} aria-hidden />
                  <span className={s.tKind}>{res.data.place.type ?? "entity"}</span>
                  <span className={s.tName}>{label(res.data.place.labels, res.data.place.id)}</span>
                  <span className={s.tMeta}>{res.data.place.lat != null ? "on the atlas →" : "in the graph →"}</span>
                </Link>
              </motion.li>
            </>
          ) : null}
        </ol>
      )}
      <p className={s.threadNote}>Chosen at random on every visit, from the real graph: each link is a recorded fact.</p>
    </section>
  );
}
