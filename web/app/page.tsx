"use client";

import Link from "next/link";

import { BarList } from "@/components/BarList";
import { Load, MarginNote, Names, Seal, fmt } from "@/components/ui";
import { api, label } from "@/lib/api";
import { DOC_TYPES, LANGUAGES, SOURCES, rowsOf } from "@/lib/names";
import { useStored } from "@/lib/stored";
import { useResource } from "@/lib/useResource";

import s from "./story.module.css";

export default function Story() {
  const stats = useResource(api.corpusStats, "stats");
  const health = useResource(api.health, "health");
  const overview = useResource(() => api.overview(10), "overview");
  const hampi = useResource(() => api.find("Hampi"), "hampi");

  return (
    <article className="page">
      <FirstVisit />
      <section className={s.opening}>
        <p className={s.kicker}>A study of one question</p>
        <h1 className={s.headline}>
          Does the <em>shape</em> of knowledge find what <em>words</em> miss?
        </h1>
        <p className={s.lede}>
          Indian heritage is written about in many languages and kept in many places: an article in Kannada, a
          gazetteer printed in 1908, a painting in Cleveland, a temple&apos;s entry on Wikidata. A search engine that
          reads only words treats them as strangers. A knowledge graph knows that they share a dynasty, a style, a
          century, a river. This site tests, in the open, whether that knowledge finds better documents than the words
          alone, and shows every step it takes to answer.
        </p>
        <Load res={hampi} what="a name in three scripts">
          {(nodes) => {
            const n = nodes.find((x) => x.kind === "entity" && x.labels.hi && x.labels.kn) ?? nodes[0];
            return n ? (
              <p className={s.triad}>
                <span className="label">one place, three scripts</span>
                <Names labels={n.labels} fallback={n.id} size="title" />
                <Link href={`/graph/?node=${encodeURIComponent(n.id)}`} className={s.small}>
                  see it in the graph →
                </Link>
              </p>
            ) : null;
          }}
        </Load>
      </section>

      <section className={`folio ${s.chapter}`}>
        <div>
          <p className={s.chapterNo}>I</p>
          <h2>The documents</h2>
          <Load res={stats} what="the corpus manifest">
            {(m) => (
              <>
                <p>
                  The corpus holds <strong className="num">{fmt(Number(m.snapshot.records))}</strong> documents about the
                  Republic of India&apos;s heritage, gathered from{" "}
                  <span className="num">{Object.keys(m.by_source).length}</span> open sources. Every one keeps its source, its
                  licence and a checksum of the response it came from; {fmt(m.duplicates_merged)} copies that arrived
                  twice were merged.
                </p>
                <BarList title="Documents by source" rows={rowsOf(m.by_source, SOURCES)} source={m.source_file} />
                <div className={s.pair}>
                  <BarList title="By language" rows={rowsOf(m.by_language, LANGUAGES)} source={m.source_file} />
                  <BarList title="By kind of document" rows={rowsOf(m.by_doc_type, DOC_TYPES)} source={m.source_file} />
                </div>
              </>
            )}
          </Load>
        </div>
        <aside>
          <MarginNote>
            <p>
              These counts are read from the snapshot&apos;s manifest, written by the script that built the corpus. The
              snapshot itself is a single compressed file with a fixed checksum, so anyone can confirm they have the
              same documents.
            </p>
          </MarginNote>
        </aside>
      </section>

      <section className={`folio ${s.chapter}`}>
        <div>
          <p className={s.chapterNo}>II</p>
          <h2>The graph, and what holds it together</h2>
          <Load res={health} what="the graph">
            {(h) =>
              h.graph.status === "ok" ? (
                <p>
                  From Wikidata&apos;s statements about these places, people, dynasties and styles, the graph has{" "}
                  <strong className="num">{fmt(Number(h.graph.nodes))}</strong> nodes and{" "}
                  <strong className="num">{fmt(Number(h.graph.edges))}</strong> edges;{" "}
                  <span className="num">{fmt(Number(h.graph.placed))}</span> of its places carry coordinates and appear
                  on the atlas. It holds facts only: who built what, what lies within what, which century. No edge was
                  drawn because two texts look alike.
                </p>
              ) : null
            }
          </Load>
          <Load res={overview} what="the communities">
            {(o) => (
              <>
                <p>
                  Set aside its most connected nodes, the <em>hubs</em>, and group what is left into communities:
                  there are <span className="num">{fmt(o.communities.length + o.others.communities)}</span>, and only{" "}
                  <span className="num">{fmt(o.communities.length)}</span> have ten or more members. Between those
                  larger communities, only <span className="num">{fmt(o.links.length)}</span> pairs share an edge at
                  all. Most of what joins one part of the graph to another is a century, a state or an empire. Whether
                  a graph like this can still help a search is the heart of the question.
                </p>
                <HubStrip ids={o.hubs.slice(0, 12)} />
              </>
            )}
          </Load>
        </div>
        <aside>
          <MarginNote>
            <p>
              A hub here is every century node and every entity above the 99th percentile of connections. The hubs
              are kept in the graph; the explorer only folds them so they do not swallow the picture.
            </p>
          </MarginNote>
        </aside>
      </section>

      <section className={`folio ${s.chapter}`}>
        <div>
          <p className={s.chapterNo}>III</p>
          <h2>Two lenses, one case</h2>
          <p>
            Each search is heard as a case. The <Seal kind="text">text lens</Seal> reads words: BM25 counts them, RM3
            adds words from the best first answers. The <Seal kind="graph">graph lens</Seal> walks from the entities a
            query names to the documents about their neighbours. Both are shown side by side, with every step that
            made each ranking, and a check that the explanation adds up to the score.
          </p>
          <p className={s.doors}>
            <Link href="/cases/?q=Hoysala%20temples%20Belur" className={s.door}>
              Open a case <span>Hoysala temples at Belur</span>
            </Link>
            <Link href="/atlas/" className={s.door}>
              Walk the atlas <span>click a place, see what ties it to its neighbours</span>
            </Link>
            <Link href="/graph/" className={s.door}>
              Enter the graph <span>communities, neighbourhoods and paths</span>
            </Link>
          </p>
        </div>
      </section>

      <section className={`folio ${s.chapter}`}>
        <div>
          <p className={s.chapterNo}>IV</p>
          <h2>What is not measured yet</h2>
          <p>
            The verdict needs judged queries, and some systems are still being built. Until they exist, the site says
            so rather than guessing.
          </p>
          <Load res={health} what="the status of each system">
            {(h) => (
              <ul className={s.status}>
                {(["corpus", "graph", "keyword"] as const).map((k) => (
                  <li key={k}>
                    <Seal kind={h[k].status === "ok" ? "measured" : "missing"}>{h[k].status === "ok" ? "running" : "missing"}</Seal>
                    <span>{k === "keyword" ? "keyword search (BM25, RM3)" : k}</span>
                  </li>
                ))}
                {Object.entries(h.planned).map(([k, v]) => (
                  <li key={k}>
                    <Seal kind="pending">not built yet</Seal>
                    <span>
                      {k.replace(/_/g, " ")} <span className={s.see}>{v.see}</span>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Load>
        </div>
      </section>
    </article>
  );
}

/** Offered once: a pointer to the five-step guide, dismissed for good when closed. */
function FirstVisit() {
  const [offered, setOffered] = useStored("guide-offered", "unknown");
  if (offered === "yes") return null;
  const close = () => setOffered("yes");
  return (
    <aside className={s.firstVisit} aria-label="First visit">
      <span>
        New here? <Link href="/guide/" onClick={close}>A first case in five steps</Link> shows what every panel means.
      </span>
      <button onClick={close} aria-label="Dismiss the guide offer">
        ×
      </button>
    </aside>
  );
}

function HubStrip({ ids }: { ids: string[] }) {
  const cards = useResource(() => Promise.all(ids.map((id) => api.node(id))), `hubs:${ids.join(",")}`);
  return (
    <Load res={cards} what="the hubs">
      {(nodes) => (
        <ol className={s.hubs}>
          {nodes.map((n) => (
            <li key={n.id}>
              <Link href={`/graph/?node=${encodeURIComponent(n.id)}`}>{label(n.labels, n.id)}</Link>
              <span className="num">{fmt(n.degree)}</span>
            </li>
          ))}
        </ol>
      )}
    </Load>
  );
}
