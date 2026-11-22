"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useRef, useState, type FormEvent } from "react";

import { Load, Names, fmt } from "@/components/ui";
import { api, label, type Linked, type NodeCard } from "@/lib/api";
import { DOC_TYPES, LANGUAGES } from "@/lib/names";
import { useResource } from "@/lib/useResource";

import { Collation } from "./Collation";
import { fromGraph, fromText, parseSeeds, seedString, type Lens, type Reading } from "./model";
import { Pipeline, type Step } from "./Pipeline";
import s from "./search.module.css";
import { WorkingDrawer } from "./WorkingDrawer";

const SYSTEMS = { bm25: "BM25", bm25_rm3: "BM25 + RM3" } as const;
type System = keyof typeof SYSTEMS;
const EXAMPLES = ["Hoysala temples Belur", "Mughal miniature painting", "मुगल किला आगरा", "ಹಂಪೆ ದೇವಾಲಯ", "jama masjid delhi"];
const DEPTH = 20; // fetched per lens, so filters still leave ten to compare
const SHOWN = 10;

export default function SearchPage() {
  return (
    <Suspense fallback={<div className="page">Opening search…</div>}>
      <Search />
    </Suspense>
  );
}

function Search() {
  const params = useSearchParams();
  const router = useRouter();
  const q = params.get("q") ?? "";
  const system = ((params.get("system") as System) in SYSTEMS ? params.get("system") : "bm25") as System;
  const lang = params.get("lang") ?? "";
  const explicitSeeds = params.get("seeds");
  const hub = Number(params.get("hub") ?? 1);
  const restart = Number(params.get("restart") ?? 0.15);
  const [draft, setDraft] = useState(q);
  const input = useRef<HTMLInputElement>(null);

  const go = (next: Record<string, string | null>) => {
    const p = new URLSearchParams(params.toString());
    for (const [k, v] of Object.entries(next)) {
      if (v == null || v === "") p.delete(k);
      else p.set(k, v);
    }
    router.push(`/cases/?${p.toString()}`, { scroll: false });
  };

  // "/" returns to the query from anywhere on the page.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const typing = e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement;
      if (e.key === "/" && !typing) {
        e.preventDefault();
        input.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (draft.trim()) go({ q: draft.trim(), seeds: null });
  };

  return (
    <div className={s.page}>
      <form className={s.queryBar} onSubmit={submit} role="search">
        <label htmlFor="q" className="visually-hidden">
          Question
        </label>
        <input
          id="q"
          ref={input}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Ask in English, हिन्दी or ಕನ್ನಡ"
          maxLength={500}
          autoComplete="off"
          autoFocus={!q}
        />
        <select aria-label="Read the question as" value={lang} onChange={(e) => go({ lang: e.target.value || null })}>
          <option value="">script decides</option>
          <option value="en">English</option>
          <option value="hi">Hindi</option>
          <option value="kn">Kannada</option>
        </select>
        <button type="submit">Search</button>
      </form>
      {q ? (
        <Case
          q={q}
          system={system}
          lang={lang || undefined}
          explicitSeeds={explicitSeeds}
          hub={hub}
          restart={restart}
          go={go}
        />
      ) : (
        <Empty onPick={(x) => (setDraft(x), go({ q: x, seeds: null }))} />
      )}
    </div>
  );
}

function Case({
  q,
  system,
  lang,
  explicitSeeds,
  hub,
  restart,
  go,
}: {
  q: string;
  system: System;
  lang?: string;
  explicitSeeds: string | null;
  hub: number;
  restart: number;
  go: (next: Record<string, string | null>) => void;
}) {
  const text = useResource(() => api.search(q, system, lang, DEPTH), `t|${q}|${system}|${lang}`);
  const linked: Linked | null = text.state === "ready" ? text.data.linked : null;
  const seeds = explicitSeeds != null ? parseSeeds(explicitSeeds) : (linked?.seeds ?? null);
  const seedKey = seeds ? seedString(seeds) : "";
  const graph = useResource(
    seeds && seedKey ? () => api.rank(seedKey, hub, restart, DEPTH) : null,
    seeds ? `g|${seedKey}|${hub}|${restart}` : "none",
  );
  const [filters, setFilters] = useState<{ language: Set<string>; kind: Set<string> }>({ language: new Set(), kind: new Set() });
  const [working, setWorking] = useState<{ lens: Lens; r: Reading } | null>(null);

  const textAll = useMemo(() => (text.state === "ready" ? fromText(text.data) : []), [text]);
  const graphAll = useMemo(() => (graph.state === "ready" ? fromGraph(graph.data) : []), [graph]);
  const keep = (r: Reading) =>
    (!filters.language.size || filters.language.has(r.language)) && (!filters.kind.size || filters.kind.has(r.kind ?? ""));
  const textShown = textAll.filter(keep).slice(0, SHOWN);
  const graphShown = graphAll.filter(keep).slice(0, SHOWN);
  const shared = textShown.filter((r) => graphShown.some((g) => g.id === r.id)).length;

  if (text.state !== "ready") {
    return text.state === "loading" ? <Skeleton /> : <Load res={text} what="the text lens">{() => null}</Load>;
  }
  const t = text.data;
  const seedCards: NodeCard[] =
    graph.state === "ready" ? graph.data.seeds : (linked?.mentions.flatMap((m) => m.candidates) ?? []);
  const steps: Step[] = [
    {
      key: "read",
      name: "Read",
      value: `${{ en: "English", hi: "Hindi", kn: "Kannada" }[t.language] ?? t.language}${lang ? "" : " (script)"}`,
      state: "done",
      detail: <ReadDetail q={q} lang={t.language} />,
    },
    {
      key: "link",
      name: "Linked",
      value: linked && linked.mentions.length ? `${linked.mentions.length} ${linked.mentions.length === 1 ? "name" : "names"}` : "none found",
      state: linked && linked.mentions.length ? "done" : "pending",
      detail: <LinkDetail linked={linked} />,
    },
    {
      key: "text",
      name: "Text lens",
      value: `${SYSTEMS[system]} · ${fmt(t.passages_retrieved)} passages`,
      state: "done",
      detail: (
        <p>
          {SYSTEMS[system]} scored every passage of the {t.language} index and kept the best{" "}
          <span className="num">{fmt(t.passage_depth)}</span>; a document scores as its best passage. Anserini&apos;s
          defaults, untuned (decision 0023).
        </p>
      ),
    },
    {
      key: "graph",
      name: "Graph lens",
      value: seeds && Object.keys(seeds).length ? `PageRank · restart ${restart}` : "no starting point",
      state: seeds && Object.keys(seeds).length ? "done" : "pending",
      detail: <GraphSettings hub={hub} restart={restart} go={go} />,
    },
    { key: "fusion", name: "Fusion", value: "not built", state: "missing", detail: <p>Reciprocal rank fusion, the reranker and LambdaMART come next (decision 0008).</p> },
    {
      key: "verdict",
      name: "Verdict",
      value: "not measured",
      state: "missing",
      detail: <p>Which lens is better needs the benchmark&apos;s judged questions; until then nothing is declared here.</p>,
    },
  ];

  return (
    <>
      <Pipeline steps={steps} />
      <Facets all={[...textAll.slice(0, DEPTH), ...graphAll.slice(0, DEPTH)]} filters={filters} setFilters={setFilters} />
      <p className={s.agreement} aria-live="polite">
        <span className={`${s.agreeNum} num`}>{shared}</span>
        <span>
          of the top {Math.max(textShown.length, graphShown.length)} found by both lenses
          {graph.state !== "ready" ? " (graph lens still reading)" : ""}
        </span>
      </p>
      <Collation
        text={textShown}
        graph={graphShown}
        textHead={
          <div className={s.lensHead}>
            <span className={s.tagText}>text lens</span>
            <div className={s.segmented} role="group" aria-label="Text lens system">
              {(Object.keys(SYSTEMS) as System[]).map((x) => (
                <button key={x} aria-pressed={x === system} onClick={() => go({ system: x === "bm25" ? null : x })}>
                  {SYSTEMS[x]}
                </button>
              ))}
            </div>
          </div>
        }
        graphHead={
          <div className={s.lensHead}>
            <span className={s.tagGraph}>graph lens</span>
            <SeedChips
              cards={seedCards}
              linkedSeeds={linked?.seeds ?? {}}
              seeds={seeds ?? {}}
              overridden={explicitSeeds != null}
              set={(next) => go({ seeds: seedString(next) })}
              reset={() => go({ seeds: null })}
            />
          </div>
        }
        onWorking={(lens, r) => setWorking({ lens, r })}
      />
      {graph.state === "ready" && graphShown.length === 0 ? (
        <p className={s.muted}>The walk from these starting points reached no document.</p>
      ) : null}
      {!seeds || !Object.keys(seeds).length ? (
        <p className={s.muted}>
          No name in the question matched an entity of the graph, so the graph lens has nowhere to start. Add a starting
          point above.
        </p>
      ) : null}
      <WorkingDrawer
        open={working != null}
        onClose={() => setWorking(null)}
        lens={working?.lens ?? "text"}
        r={working?.r ?? null}
        q={q}
        system={system}
        lang={lang}
        settings={{ restart, hub, seeds: Object.keys(seeds ?? {}) }}
      />
    </>
  );
}

function ReadDetail({ q, lang }: { q: string; lang: string }) {
  const res = useResource(() => api.analyse(q, lang), `a|${q}|${lang}`);
  return (
    <Load res={res} what="the analysed words">
      {(a) => (
        <p className={s.tokens}>
          The index keeps words in a reduced form; the question becomes:{" "}
          {a.tokens.map((t, i) => (
            <code key={i}>{t}</code>
          ))}
        </p>
      )}
    </Load>
  );
}

function LinkDetail({ linked }: { linked: Linked | null }) {
  if (!linked || !linked.mentions.length) return <p>No name in the question matched an entity of the graph.</p>;
  return (
    <ul className={s.mentions}>
      {linked.mentions.map((m) => (
        <li key={m.text}>
          <q>{m.text}</q> <span className={s.method}>{m.method === "fuzzy" ? `close spelling, ${m.score}` : m.method}</span> →{" "}
          {m.candidates.map((c, i) => (
            <span key={c.id}>
              {i ? ", " : ""}
              <Link href={`/graph/?node=${encodeURIComponent(c.id)}`}>
                <Names labels={c.labels} fallback={c.id} />
              </Link>
            </span>
          ))}
          {m.candidates.length > 1 ? <span className={s.method}> · weight split {m.candidates.length} ways</span> : null}
        </li>
      ))}
    </ul>
  );
}

function GraphSettings({ hub, restart, go }: { hub: number; restart: number; go: (n: Record<string, string | null>) => void }) {
  return (
    <div className={s.settings}>
      <div role="group" aria-label="Hub down-weighting" className={s.segmented}>
        <span className={s.setName}>hubs</span>
        {[
          [1, "1 / degree"],
          [0.5, "1 / √degree"],
          [0, "no weighting"],
        ].map(([v, name]) => (
          <button key={v} aria-pressed={hub === v} onClick={() => go({ hub: v === 1 ? null : String(v) })}>
            {name}
          </button>
        ))}
      </div>
      <div role="group" aria-label="Restart probability" className={s.segmented}>
        <span className={s.setName}>restart</span>
        {[0.1, 0.15, 0.3].map((v) => (
          <button key={v} aria-pressed={restart === v} onClick={() => go({ restart: v === 0.15 ? null : String(v) })}>
            {v}
          </button>
        ))}
      </div>
      <p className={s.muted}>Defaults from decision 0027; they are tuned on the dev questions only.</p>
    </div>
  );
}

function SeedChips({
  cards,
  seeds,
  overridden,
  set,
  reset,
}: {
  cards: NodeCard[];
  linkedSeeds: Record<string, number>;
  seeds: Record<string, number>;
  overridden: boolean;
  set: (next: Record<string, number>) => void;
  reset: () => void;
}) {
  const [adding, setAdding] = useState("");
  const found = useResource(adding.trim().length >= 2 ? () => api.find(adding.trim()) : null, `sf|${adding.trim()}`);
  const byId = new Map(cards.map((c) => [c.id, c]));
  return (
    <div className={s.seeds}>
      <span className={s.setName}>starts from</span>
      {Object.keys(seeds).map((id) => (
        <span key={id} className={s.chip}>
          {byId.get(id) ? label(byId.get(id)!.labels, id) : id}
          <button
            aria-label={`Remove ${byId.get(id) ? label(byId.get(id)!.labels, id) : id}`}
            onClick={() => {
              const next = { ...seeds };
              delete next[id];
              set(next);
            }}
          >
            ×
          </button>
        </span>
      ))}
      <span className={s.addWrap}>
        <input aria-label="Add a starting point" placeholder="+ add" value={adding} onChange={(e) => setAdding(e.target.value)} />
        {adding.trim().length >= 2 && found.state === "ready" ? (
          <ul className={s.addList}>
            {found.data
              .filter((n) => n.kind !== "document")
              .slice(0, 7)
              .map((n) => (
                <li key={n.id}>
                  <button onClick={() => (set({ ...seeds, [n.id]: 1 }), setAdding(""))}>
                    <Names labels={n.labels} fallback={n.id} />
                  </button>
                </li>
              ))}
          </ul>
        ) : null}
      </span>
      {overridden ? (
        <button className={s.reset} onClick={reset}>
          use the linked names
        </button>
      ) : null}
    </div>
  );
}

function Facets({
  all,
  filters,
  setFilters,
}: {
  all: Reading[];
  filters: { language: Set<string>; kind: Set<string> };
  setFilters: (f: { language: Set<string>; kind: Set<string> }) => void;
}) {
  const count = (key: "language" | "kind") => {
    const seen = new Map<string, Set<string>>();
    for (const r of all) {
      const v = (key === "language" ? r.language : r.kind) ?? "";
      if (!seen.has(v)) seen.set(v, new Set());
      seen.get(v)!.add(r.id);
    }
    return [...seen.entries()].map(([v, ids]) => [v, ids.size] as const).sort((a, b) => b[1] - a[1]);
  };
  const toggle = (key: "language" | "kind", v: string) => {
    const next = new Set(filters[key]);
    if (next.has(v)) next.delete(v);
    else next.add(v);
    setFilters({ ...filters, [key]: next });
  };
  const row = (key: "language" | "kind", names: Record<string, string>) => (
    <div className={s.facetRow} role="group" aria-label={key === "language" ? "Language" : "Kind of document"}>
      {count(key).map(([v, n]) => (
        <button key={v} aria-pressed={filters[key].has(v)} onClick={() => toggle(key, v)}>
          {names[v] ?? (v || "other")} <span className="num">{n}</span>
        </button>
      ))}
    </div>
  );
  return (
    <div className={s.facets}>
      {row("language", LANGUAGES)}
      {row("kind", DOC_TYPES)}
    </div>
  );
}

function Skeleton() {
  return (
    <div className={s.skeleton} aria-busy="true" aria-label="Reading the question">
      <div className={s.skelStrip} />
      <div className={s.skelCols}>
        {[0, 1].map((c) => (
          <div key={c}>
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className={s.skelCard} />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

function Empty({ onPick }: { onPick: (q: string) => void }) {
  return (
    <section className={s.empty}>
      <div className={s.emptyText}>
        <h1 className={s.emptyTitle}>Two readings of every question</h1>
        <p>
          The text lens reads the words. The graph lens finds the places, dynasties and styles the question names and
          walks the facts that join them. Their answers are set side by side, as scholars collate two copies of a
          manuscript: a line joins every document both found.
        </p>
        <p className={s.examples}>
          {EXAMPLES.map((x) => (
            <button key={x} onClick={() => onPick(x)}>
              {x}
            </button>
          ))}
        </p>
      </div>
      <svg className={s.emptyArt} viewBox="0 0 240 180" aria-hidden>
        {[0, 1, 2, 3, 4].map((i) => (
          <rect key={`l${i}`} x="8" y={14 + i * 32} width="74" height="20" rx="2" className={s.artCard} />
        ))}
        {[0, 1, 2, 3, 4].map((i) => (
          <rect key={`r${i}`} x="158" y={14 + i * 32} width="74" height="20" rx="2" className={s.artCard} />
        ))}
        {(
          [
            [0, 1],
            [1, 0],
            [3, 2],
          ] as const
        ).map(([a, b]) => (
          <path key={`${a}${b}`} d={`M 82 ${24 + a * 32} C 120 ${24 + a * 32}, 120 ${24 + b * 32}, 158 ${24 + b * 32}`} className={s.artLine} />
        ))}
      </svg>
    </section>
  );
}
