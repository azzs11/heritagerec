"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState, type FormEvent } from "react";

import { Evidence, Load, MarginNote, MissingSlip, Seal, fmt } from "@/components/ui";
import { api, type Explanation, type NodeCard, type SearchResult } from "@/lib/api";
import { DOC_TYPES, SOURCES } from "@/lib/names";
import { useResource } from "@/lib/useResource";

import s from "./cases.module.css";
import { GraphLens } from "./GraphLens";

const SYSTEMS = { bm25: "BM25", bm25_rm3: "BM25 + RM3" } as const;
type System = keyof typeof SYSTEMS;
const EXAMPLES = ["Hoysala temples Belur", "Mughal miniature painting", "मुगल किला आगरा", "ಹಂಪೆ ದೇವಾಲಯ"];

export default function CasesPage() {
  return (
    <Suspense fallback={<p className="page">Opening the case…</p>}>
      <Cases />
    </Suspense>
  );
}

function Cases() {
  const params = useSearchParams();
  const router = useRouter();
  const q = params.get("q") ?? "";
  const system = (params.get("system") as System) in SYSTEMS ? (params.get("system") as System) : "bm25";
  const lang = params.get("lang") ?? "";
  const [draft, setDraft] = useState(q);

  const seeds = (params.get("seeds") ?? "").split(";").filter(Boolean);
  const go = (next: { q?: string; system?: string; lang?: string; seeds?: string }) => {
    const p = new URLSearchParams({ q, system, lang, seeds: seeds.join(";"), ...next });
    for (const [k, v] of [...p.entries()]) if (!v) p.delete(k);
    router.push(`/cases/?${p.toString()}`);
  };
  const submit = (e: FormEvent) => {
    e.preventDefault();
    go({ q: draft.trim(), seeds: "" });
  };

  return (
    <article className="page">
      <header className={s.head}>
        <p className={s.kicker}>Cases</p>
        <h1 className={s.title}>Put a question to both lenses</h1>
        <form className={s.form} onSubmit={submit} role="search">
          <label htmlFor="q" className="visually-hidden">
            Query
          </label>
          <input
            id="q"
            className={s.input}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="A question in English, हिन्दी or ಕನ್ನಡ"
            maxLength={500}
            autoComplete="off"
          />
          <label className={s.select}>
            <span className="label">read as</span>
            <select value={lang} onChange={(e) => go({ lang: e.target.value })}>
              <option value="">script decides</option>
              <option value="en">English</option>
              <option value="hi">Hindi</option>
              <option value="kn">Kannada</option>
            </select>
          </label>
          <button className={s.submit} type="submit">
            Open the case
          </button>
        </form>
        {!q ? (
          <p className={s.examples}>
            <span className="label">or try</span>
            {EXAMPLES.map((x) => (
              <button key={x} onClick={() => (setDraft(x), go({ q: x }))} className={s.example}>
                {x}
              </button>
            ))}
          </p>
        ) : null}
      </header>
      {q ? (
        <Case
          q={q}
          system={system}
          lang={lang || undefined}
          onSystem={(x) => go({ system: x })}
          seeds={seeds}
          onSeeds={(x) => go({ seeds: x.join(";") })}
        />
      ) : null}
    </article>
  );
}

function Case({
  q,
  system,
  lang,
  onSystem,
  seeds,
  onSeeds,
}: {
  q: string;
  system: System;
  lang?: string;
  onSystem: (s: System) => void;
  seeds: string[];
  onSeeds: (s: string[]) => void;
}) {
  const res = useResource(() => api.search(q, system, lang, 10), `${q}|${system}|${lang}`);
  const [open, setOpen] = useState<string | null>(null);

  return (
    <section aria-label={`Case: ${q}`}>
      <div className={s.caseLine}>
        <span className={s.caseNo}>case</span>
        <q className={s.caseQuery}>{q}</q>
      </div>

      <Load res={res} what="the text lens">
        {(r) => (
          <>
            <ol className={s.stages}>
              <li>
                <span className={s.stageNo}>1</span>
                <div>
                  <h2 className={s.stageTitle}>Reading the question</h2>
                  <p>
                    Read as <strong>{{ en: "English", hi: "Hindi", kn: "Kannada" }[r.language] ?? r.language}</strong>
                    {lang ? " (chosen by you)" : " (from its script)"}, then reduced to the forms the index stores:
                  </p>
                  <div className={s.tokens}>
                    <Tokens q={q} lang={r.language} />
                  </div>
                  <MissingSlip
                    title="not built yet"
                    part="query linker"
                    reason="The entities this question names are not linked yet, so the graph lens has no place to start from."
                    fix="decision 0025; the linker and its evaluation come in phase 1, week 7"
                  />
                </div>
              </li>
              <li>
                <span className={s.stageNo}>2</span>
                <div>
                  <h2 className={s.stageTitle}>Finding candidates</h2>
                  <p>
                    {SYSTEMS[r.system]} scored every passage of the {r.language} index;{" "}
                    <span className="num">{fmt(r.passages_retrieved)}</span> passages were kept (the depth is{" "}
                    <span className="num">{fmt(r.passage_depth)}</span>), and each document took the score of its best
                    passage.
                  </p>
                  <div className={s.switch} role="group" aria-label="Text lens system">
                    {(Object.keys(SYSTEMS) as System[]).map((x) => (
                      <button key={x} aria-pressed={x === system} onClick={() => onSystem(x)}>
                        {SYSTEMS[x]}
                      </button>
                    ))}
                  </div>
                </div>
              </li>
            </ol>

            <div className={s.lenses}>
              <section className={s.lens} aria-label="Text lens">
                <h2 className={s.lensTitle}>
                  <Seal kind="text">text lens</Seal> {SYSTEMS[r.system]}
                </h2>
                {r.results.length === 0 ? <p>No document matched any word of the question.</p> : null}
                <ol className={s.results}>
                  {r.results.map((x) => (
                    <Result
                      key={x.doc_id}
                      x={x}
                      open={open === x.doc_id}
                      onOpen={() => setOpen(open === x.doc_id ? null : x.doc_id)}
                      q={q}
                      system={r.system}
                      lang={r.language}
                    />
                  ))}
                </ol>
              </section>
              <section className={s.lens} aria-label="Graph lens">
                <h2 className={s.lensTitle}>
                  <Seal kind="graph">graph lens</Seal> personalised PageRank
                </h2>
                <GraphLensWithSuggestions docIds={r.results.slice(0, 5).map((x) => x.doc_id)} seeds={seeds} setSeeds={onSeeds} />
              </section>
            </div>

            <ol className={s.stages} start={3}>
              <li>
                <span className={s.stageNo}>3</span>
                <div>
                  <h2 className={s.stageTitle}>Fusing and re-ranking</h2>
                  <MissingSlip
                    title="not built yet"
                    part="fusion, reranker, lambdamart"
                    reason="Reciprocal rank fusion, the bge-reranker and LambdaMART will each appear here with their own share of the final order."
                    fix="decision 0008"
                  />
                </div>
              </li>
              <li>
                <span className={s.stageNo}>4</span>
                <div>
                  <h2 className={s.stageTitle}>Verdict</h2>
                  <p>
                    <Seal kind="pending">not measured yet</Seal> A verdict needs relevance judgements for this kind of
                    question. Until the benchmark is judged, neither lens is declared better here.
                  </p>
                </div>
              </li>
            </ol>
          </>
        )}
      </Load>
    </section>
  );
}

function Tokens({ q, lang }: { q: string; lang: string }) {
  const res = useResource(() => api.analyse(q, lang).then((a) => a.tokens), `tok|${q}|${lang}`);
  return (
    <Load res={res} what="the analysed words">
      {(tokens) => (
        <>
          {tokens.map((t, i) => (
            <code key={i} className={s.token}>
              {t}
            </code>
          ))}
        </>
      )}
    </Load>
  );
}

function Result({
  x,
  open,
  onOpen,
  q,
  system,
  lang,
}: {
  x: SearchResult;
  open: boolean;
  onOpen: () => void;
  q: string;
  system: string;
  lang: string;
}) {
  return (
    <li className={s.result}>
      <div className={s.resultHead}>
        <span className={`${s.rank} num`}>{x.rank}</span>
        <div className={s.resultTitle}>
          <Link href={`/document/?id=${encodeURIComponent(x.doc_id)}`} lang={x.language}>
            {x.title ?? x.doc_id}
          </Link>
          <span className={s.meta}>
            {SOURCES[x.source ?? ""] ?? x.source} · {DOC_TYPES[x.doc_type ?? ""] ?? x.doc_type}
          </span>
        </div>
        <span className={`${s.score} num`} title="the score of its best passage">
          {x.score.toFixed(3)}
        </span>
      </div>
      {x.snippet ? <Evidence words={x.snippet} lang={x.language} /> : null}
      <button className={s.why} aria-expanded={open} onClick={onOpen}>
        {open ? "close the working" : "why here? show the working"}
      </button>
      {open ? <Working q={q} doc={x.doc_id} system={system} lang={lang} /> : null}
    </li>
  );
}

function Working({ q, doc, system, lang }: { q: string; doc: string; system: string; lang: string }) {
  const res = useResource(() => api.explain(q, doc, system, lang), `ex|${q}|${doc}|${system}|${lang}`);
  return (
    <div className={s.working}>
      <Load res={res} what="the working">
        {(e) => <WorkingBody e={e} />}
      </Load>
    </div>
  );
}

function WorkingBody({ e }: { e: Explanation }) {
  if (!e.winner) return <p>{e.note}</p>;
  const w = e.winner;
  const max = Math.max(...w.terms.map((t) => Math.abs(t.contribution)), 1e-9);
  const rm3 = e.system === "bm25_rm3";
  return (
    <>
      <h4 className={s.workTitle}>The best passage scored {w.score.toFixed(3)}, made of:</h4>
      <table className={s.terms}>
        <thead>
          <tr>
            <th scope="col">term</th>
            <th scope="col">{rm3 ? "expansion weight" : "times in query"}</th>
            <th scope="col">BM25 weight here</th>
            <th scope="col">adds</th>
            <th scope="col">
              <span className="visually-hidden">share</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {w.terms.map((t) => (
            <tr key={t.term} className={t.contribution === 0 ? s.zero : undefined}>
              <td>
                <code>{t.term}</code>
              </td>
              <td className="num">{rm3 ? t.multiplier.toFixed(3) : t.multiplier}</td>
              <td className="num">{t.bm25_weight.toFixed(3)}</td>
              <td className="num">{t.contribution.toFixed(3)}</td>
              <td className={s.termBar}>
                <span style={{ width: `${(100 * Math.abs(t.contribution)) / max}%` }} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className={s.check}>
        {w.check.matches ? <Seal kind="measured">adds up</Seal> : <Seal kind="pending">does not add up</Seal>} the terms
        sum to <span className="num">{w.check.recomputed.toFixed(4)}</span>; Lucene returned{" "}
        <span className="num">{w.check.lucene.toFixed(4)}</span>.
      </p>
      <p className={s.muted}>
        Passage <code>{w.passage}</code> of <span className="num">{fmt(e.passages_in_document ?? 0)}</span> in the
        document; <span className="num">{fmt(e.passages_retrieved.length)}</span> of them were among the candidates. The
        document ranks <span className="num">{e.rank}</span> because this is its best.
      </p>
      {e.passages_retrieved.length > 1 ? (
        <ol className={s.passages}>
          {e.passages_retrieved.slice(0, 8).map((p, i) => (
            <li key={p.passage} className={i === 0 ? s.winner : undefined}>
              <code>#{p.passage.split("#").pop()}</code> <span className="num">{p.score.toFixed(3)}</span>
              {i === 0 ? <span className={s.muted}> best, counts</span> : null}
            </li>
          ))}
        </ol>
      ) : null}
      {w.text ? <Evidence words={w.text} lang={e.language} /> : null}
      <MarginNote>
        <p>
          BM25 gives each query term a weight for this passage: higher when the term is rare in the collection and
          frequent in the passage, lower when the passage is long. The passage&apos;s score is the sum. RM3 first reads
          the best passages, adds the words they share, and weighs every word, original or added; each row then adds
          its weight times its BM25 weight.
        </p>
        <p>The check recomputes the sum from these rows and compares it with the score the search engine returned.</p>
      </MarginNote>
    </>
  );
}

/** The graph lens, offered the entities that the text lens's top answers are about as starting points. */
function GraphLensWithSuggestions({ docIds, seeds, setSeeds }: { docIds: string[]; seeds: string[]; setSeeds: (s: string[]) => void }) {
  const about = useResource(
    () => Promise.all(docIds.map((d) => api.ego(d, 12, "about").catch(() => null))),
    `about|${docIds.join(",")}`,
  );
  const suggestions: NodeCard[] = [];
  if (about.state === "ready") {
    const seen = new Set<string>();
    for (const v of about.data) {
      for (const n of v?.nodes.slice(1) ?? []) {
        if (seen.has(n.id) || n.kind === "document") continue;
        seen.add(n.id);
        suggestions.push(n);
      }
    }
  }
  return <GraphLens seeds={seeds} setSeeds={setSeeds} suggestions={suggestions} />;
}
