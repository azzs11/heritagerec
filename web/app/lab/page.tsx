"use client";

import Link from "next/link";

import { Load, MarginNote, Seal } from "@/components/ui";
import { api, label } from "@/lib/api";
import { useResource } from "@/lib/useResource";

import s from "../pages.module.css";

const PLANNED = [
  ["Known-item check", "each sampled document searched by its own title; success at rank 1 and reciprocal rank, with ranx"],
  ["Typos", "seeded letter swaps, drops and doublings"],
  ["Romanised Hindi and Kannada", "the same question typed in Latin letters"],
  ["Script swaps", "entity names moved into another script from the gazetteer"],
  ["Diacritics stripped", "Mysūru typed as Mysuru, Kāśī as Kasi"],
  ["One word, empty, very long", "the edges of what a query can be"],
  ["Hub-heavy questions", "questions that name only India, a state or a century"],
  ["Failure gallery", "the worst cases of each run, each opening its case page"],
  ["Engineering breaks", "fuzzing every route (already in the server's tests), missing parts, latency at the median and 95th percentile"],
];

export default function Lab() {
  return (
    <article className="page">
      <header className={s.head}>
        <p className={s.kicker}>Lab</p>
        <h1 className={s.title}>Where the system tries to break itself</h1>
        <p className={s.lede}>
          A system that is only shown working is not tested. The Lab runs the same searches with their input bent out of
          shape and records where each lens fails. The measured runs come next; below are the first breaks found while
          building it, run live against the system each time this page opens.
        </p>
      </header>
      <section className="folio">
        <div>
          <h2 className={s.h2}>Found so far, run live</h2>
          <StemCollision />
          <AddedWords />
          <HubPath />
          <h2 className={s.h2}>The measured runs</h2>
          <table className={s.table}>
            <tbody>
              {PLANNED.map(([name, what]) => (
                <tr key={name}>
                  <td>
                    <Seal kind="pending">not built yet</Seal>
                  </td>
                  <td>
                    <strong>{name}</strong> <span className={s.small}>{what}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className={s.small}>
            Perturbations run on dev queries only; the test queries stay sealed until the analysis plan is committed.
          </p>
        </div>
        <aside>
          <MarginNote>
            <p>
              Each observation here asks the running system the same question every time and shows its answer. If the
              system changes, the observation changes with it.
            </p>
          </MarginNote>
        </aside>
      </section>
    </article>
  );
}

function StemCollision() {
  const res = useResource(
    () => Promise.all([api.analyse("आगरा", "hi"), api.analyse("अगर", "hi")]),
    "stem",
  );
  return (
    <section className={s.case}>
      <p className="label">stemming · Hindi</p>
      <h3>Does Agra become “if”?</h3>
      <Load res={res} what="the Hindi analyser">
        {([agra, agar]) => {
          const same = agra.tokens.join() === agar.tokens.join();
          return (
            <>
              <p className={s.evidence}>
                आगरा (Agra) →
                <span className={s.tokens}>
                  {agra.tokens.map((t) => (
                    <code key={t}>{t}</code>
                  ))}
                </span>
                अगर (“if”) →
                <span className={s.tokens}>
                  {agar.tokens.map((t) => (
                    <code key={t}>{t}</code>
                  ))}
                </span>
                {same ? <Seal kind="pending">same stem</Seal> : <Seal kind="measured">kept apart</Seal>}
              </p>
              <p>
                {same
                  ? "Lucene's Hindi stemmer reduces the city and the everyday word for “if” to one form, so a Hindi question about Agra also matches every passage that says “if”."
                  : "The analyser keeps the city and the word apart."}{" "}
                <Link href="/cases/?q=%E0%A4%86%E0%A4%97%E0%A4%B0%E0%A4%BE%20%E0%A4%95%E0%A4%BE%20%E0%A4%95%E0%A4%BF%E0%A4%B2%E0%A4%BE">
                  Open the case
                </Link>
              </p>
            </>
          );
        }}
      </Load>
    </section>
  );
}

function AddedWords() {
  const q = "Hoysala temples Belur";
  const res = useResource(async () => {
    const r = await api.search(q, "bm25_rm3", "en", 1);
    const top = r.results[0];
    if (!top) return null;
    const [e, a] = await Promise.all([api.explain(q, top.doc_id, "bm25_rm3", "en"), api.analyse(q, "en")]);
    return { e, original: new Set(a.tokens) };
  }, "rm3");
  return (
    <section className={s.case}>
      <p className="label">query expansion · RM3</p>
      <h3>What words does RM3 add?</h3>
      <Load res={res} what="the expansion">
        {(d) =>
          d ? (
            <>
              <p className={s.evidence}>
                “{q}” →
                <span className={s.tokens}>
                  {d.e.terms
                    .filter((t) => !d.original.has(t.term))
                    .map((t) => (
                      <code key={t.term} title={`weight ${t.multiplier.toFixed(3)}`}>
                        {t.term}
                      </code>
                    ))}
                </span>
              </p>
              <p>
                RM3 reads the passages that rank first and adds the words they share. The added words come from how those
                passages are written as much as from what they are about; a reader can judge which belong to the
                question. <Link href={`/cases/?q=${encodeURIComponent(q)}&system=bm25_rm3`}>Open the case</Link>
              </p>
            </>
          ) : (
            <p>Nothing was retrieved.</p>
          )
        }
      </Load>
    </section>
  );
}

function HubPath() {
  const res = useResource(() => api.path("Q466581", "Q33296"), "hubpath");
  return (
    <section className={s.case}>
      <p className="label">graph · hubs</p>
      <h3>How are the Hoysala and Mughal empires joined?</h3>
      <Load res={res} what="the path">
        {(p) => (
          <>
            <p className={s.evidence}>
              {p.through_hubs ? <Seal kind="pending">only through a hub</Seal> : p.through_hubs === false ? <Seal kind="measured">without hubs</Seal> : <Seal kind="pending">not joined</Seal>}
              {p.paths[0]
                ? p.paths[0].nodes.map((n, i) => (
                    <span key={n.id}>
                      {i ? "→ " : ""}
                      {label(n.labels, n.id)}
                    </span>
                  ))
                : null}
            </p>
            <p>
              {p.through_hubs
                ? "Within four steps, every route between these two empires passes through a hub, such as a century, shown in the path above. A graph method can follow such a route, but it says little more than that both share something very common."
                : "The two empires are joined without passing through a hub."}{" "}
              <Link href="/graph/?node=Q466581">Open the neighbourhood</Link>
            </p>
          </>
        )}
      </Load>
    </section>
  );
}
