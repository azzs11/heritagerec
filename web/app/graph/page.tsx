"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState } from "react";

import { GraphCanvas, type CanvasEdge, type CanvasNode } from "@/components/GraphCanvas";
import { Load, MarginNote, Names, Seal, fmt } from "@/components/ui";
import { api, label, stepLabel, type Bundle, type EgoView, type GraphEdge, type NodeCard, type Overview, type PathView } from "@/lib/api";
import { KINDS, KINDS_PLURAL } from "@/lib/names";
import { NextSteps } from "@/components/Wayfinding";
import { useTrailStep } from "@/lib/trail";
import { useResource } from "@/lib/useResource";

import s from "./graph.module.css";

const GLOBAL_BUDGET = 400; // the most marks on screen after merging neighbourhoods

export default function GraphPage() {
  return (
    <Suspense fallback={<p className="page">Opening the graph…</p>}>
      <Explorer />
    </Suspense>
  );
}

function Explorer() {
  const params = useSearchParams();
  const router = useRouter();
  const centre = params.get("node");
  const go = (id: string | null) => router.push(id ? `/graph/?node=${encodeURIComponent(id)}` : "/graph/");

  return (
    <article className={s.full}>
      <header className={s.head}>
        <div>
          <h1 className={s.title}>{centre ? "Graph · neighbourhood" : "Graph · communities"}</h1>
        </div>
        <Finder onPick={(id) => go(id)} />
      </header>
      {centre ? <Neighbourhood key={centre} centre={centre} go={go} /> : <Communities go={go} />}
    </article>
  );
}

function Finder({ onPick }: { onPick: (id: string) => void }) {
  const [q, setQ] = useState("");
  const res = useResource(q.trim().length >= 2 ? () => api.find(q.trim()) : null, `find|${q.trim()}`);
  return (
    <div className={s.finder}>
      <label htmlFor="find" className="label">
        find a place, person, dynasty or document
      </label>
      <input id="find" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Hampi, हम्पी, ಹಂಪೆ…" autoComplete="off" />
      {q.trim().length >= 2 && res.state === "ready" ? (
        <ul className={s.found} role="listbox" aria-label="Matches">
          {res.data.length === 0 ? <li className={s.muted}>nothing by that name</li> : null}
          {res.data.slice(0, 10).map((n) => (
            <li key={n.id}>
              <button onClick={() => (setQ(""), onPick(n.id))}>
                <Names labels={n.labels} fallback={n.id} /> <span className={s.muted}>{KINDS[n.kind]}</span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

// ---------- overview: communities ----------

function Communities({ go }: { go: (id: string) => void }) {
  const res = useResource(() => api.overview(10), "overview");
  return (
    <Load res={res} what="the communities">
      {(o) => <CommunityView o={o} go={go} />}
    </Load>
  );
}

function CommunityView({ o, go }: { o: Overview; go: (id: string) => void }) {
  const [picked, setPicked] = useState<number | null>(null);
  const { nodes, edges } = useMemo(() => {
    const max = Math.max(...o.communities.map((c) => c.size));
    // Communities arrive largest first; only the largest are always labelled, the rest on hover or choice.
    const nodes: CanvasNode[] = o.communities.map((c, i) => ({
      id: `c${c.id}`,
      label: c.label ?? `community ${c.id}`,
      size: 3 + 14 * Math.sqrt(c.size / max),
      tone: "community",
      important: i < 15,
    }));
    const edges: CanvasEdge[] = o.links.map((l) => ({ id: `l${l.a}-${l.b}`, source: `c${l.a}`, target: `c${l.b}`, label: `${l.edges} edges` }));
    return { nodes, edges };
  }, [o]);
  const c = picked != null ? o.communities.find((x) => x.id === picked) : null;

  return (
    <div className={s.stage}>
      <div className={s.canvas}>
        <GraphCanvas
          nodes={nodes}
          edges={edges}
          selected={picked != null ? `c${picked}` : null}
          onSelect={(id) => setPicked(Number(id.slice(1)))}
          ariaLabel={`${o.communities.length} communities of the graph, joined where they share edges`}
        />
      </div>
      <aside className={s.panel}>
        <p>
          <span className="num">{fmt(o.communities.length)}</span> communities with {o.min_size} or more nodes are
          drawn; <span className="num">{fmt(o.others.communities)}</span> smaller ones (
          <span className="num">{fmt(o.others.nodes)}</span> nodes) are left out of this picture, and the hubs are set
          aside. Lines join communities that share at least one edge.
        </p>
        {c ? (
          <div className={s.card}>
            <h2 className={s.cardTitle}>{c.label}</h2>
            <p className={s.muted}>
              <span className="num">{fmt(c.size)}</span> nodes: <span className="num">{fmt(c.documents)}</span>{" "}
              documents, <span className="num">{fmt(c.entities)}</span> entities (
              <span className="num">{fmt(c.placed)}</span> on the map)
            </p>
            <p className="label">its most connected members</p>
            <TopMembers ids={c.top} go={go} />
          </div>
        ) : (
          <p className={s.muted}>Choose a community to see what it is made of.</p>
        )}
        <MarginNote>
          <p>
            Communities are found by the Louvain method with a fixed seed, on the graph without its hubs. They are a way
            to look at the graph, not a finding about heritage.
          </p>
        </MarginNote>
        <TextList title="Communities in this picture" items={o.communities.map((x) => `${x.label ?? x.id}: ${x.size} nodes`)} />
      </aside>
    </div>
  );
}

function TopMembers({ ids, go }: { ids: string[]; go: (id: string) => void }) {
  const res = useResource(() => Promise.all(ids.map((id) => api.node(id))), `top|${ids.join(",")}`);
  return (
    <Load res={res} what="its members">
      {(nodes) => (
        <ul className={s.members}>
          {nodes.map((n) => (
            <li key={n.id}>
              <button onClick={() => go(n.id)}>
                <Names labels={n.labels} fallback={n.id} />
              </button>
              <span className="num">{fmt(n.degree)}</span>
            </li>
          ))}
        </ul>
      )}
    </Load>
  );
}

// ---------- a neighbourhood that grows on demand ----------

interface Merged {
  nodes: Map<string, NodeCard>;
  edges: Map<string, GraphEdge>;
  bundles: Map<string, Bundle & { owner: string }>;
}

const edgeKey = (e: GraphEdge) => `${e.source}|${e.relation}|${e.target}`;

function merge(into: Merged, v: EgoView): Merged {
  const out: Merged = { nodes: new Map(into.nodes), edges: new Map(into.edges), bundles: new Map(into.bundles) };
  v.nodes.forEach((n) => out.nodes.set(n.id, n));
  v.edges.forEach((e) => out.edges.set(edgeKey(e), e));
  v.bundles.forEach((b) => out.bundles.set(`${v.center}|${b.relation}|${b.direction}|${b.kind}`, { ...b, owner: v.center }));
  return out;
}

function Neighbourhood({ centre, go }: { centre: string; go: (id: string | null) => void }) {
  const first = useResource(() => api.ego(centre, 150), `ego|${centre}`);
  return (
    <Load res={first} what="the neighbourhood">
      {(v) => <Growing centre={centre} first={v} go={go} />}
    </Load>
  );
}

function Growing({ centre, first, go }: { centre: string; first: EgoView; go: (id: string | null) => void }) {
  const centreCard = first.nodes[0];
  useTrailStep(
    centreCard
      ? {
          kind: centreCard.kind === "document" ? "document" : "entity",
          label: label(centreCard.labels, centreCard.id),
          href: `/graph/?node=${encodeURIComponent(centreCard.id)}`,
        }
      : null,
  );
  const [view, setView] = useState<Merged>(() => merge({ nodes: new Map(), edges: new Map(), bundles: new Map() }, first));
  const [selected, setSelected] = useState<string>(centre);
  const [path, setPath] = useState<PathView | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const marks = view.nodes.size + view.bundles.size;
  const highlight = useMemo(() => {
    const h = new Set<string>();
    path?.paths.forEach((p) => {
      p.nodes.forEach((n) => h.add(n.id));
      p.edges.forEach((e) => h.add(edgeKey(e)));
    });
    return h;
  }, [path]);

  const { nodes, edges } = useMemo(() => {
    const maxDeg = Math.max(...[...view.nodes.values()].map((n) => n.degree), 1);
    const nodes: CanvasNode[] = [...view.nodes.values()].map((n) => ({
      id: n.id,
      label: label(n.labels, n.id),
      size: n.id === centre ? 14 : n.kind === "document" ? 3 : 4 + 8 * Math.sqrt(n.degree / maxDeg),
      tone: n.id === centre ? "focus" : n.hub ? "hub" : n.kind === "document" ? "document" : n.kind === "period" ? "period" : "entity",
    }));
    const edges: CanvasEdge[] = [...view.edges.values()].map((e) => ({ id: edgeKey(e), source: e.source, target: e.target, label: e.relation_label }));
    for (const [k, b] of view.bundles) {
      nodes.push({ id: `bundle:${k}`, label: `+${fmt(b.count)} ${KINDS_PLURAL[b.kind]} · ${b.relation_label}`, size: 5, tone: "bundle" });
      edges.push({ id: `bundle-edge:${k}`, source: b.owner, target: `bundle:${k}`, label: b.relation_label });
    }
    return { nodes, edges };
  }, [view, centre]);

  const expand = async (id: string) => {
    setBusy(true);
    setMessage(null);
    try {
      const room = Math.max(2, Math.min(150, GLOBAL_BUDGET - marks + 1));
      if (room <= 2) {
        setMessage(`The picture holds ${GLOBAL_BUDGET} marks at most. Centre on this node instead to see its neighbourhood.`);
        return;
      }
      const v = await api.ego(id, room);
      setView((cur) => merge(cur, v));
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const findPath = async (id: string) => {
    setBusy(true);
    try {
      const p = await api.path(centre, id);
      setPath(p);
      setView((cur) => {
        let out = cur;
        for (const pp of p.paths) out = merge(out, { center: centre, budget: 0, nodes: pp.nodes, edges: pp.edges, bundles: [], neighbours: 0, shown: 0, center_is_hub: false });
        return out;
      });
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const sel = selected.startsWith("bundle:") ? null : view.nodes.get(selected);
  const bundle = selected.startsWith("bundle:") ? view.bundles.get(selected.slice(7)) : null;

  return (
    <div className={s.stage}>
      <div className={s.canvas} aria-busy={busy}>
        <GraphCanvas nodes={nodes} edges={edges} highlight={highlight} selected={selected} onSelect={setSelected} ariaLabel={`Neighbourhood of ${label(view.nodes.get(centre)?.labels ?? {}, centre)}: ${view.nodes.size} nodes`} />
      </div>
      <aside className={s.panel}>
        <p className={s.budget}>
          <span className="num">{fmt(view.nodes.size)}</span> nodes and <span className="num">{fmt(view.bundles.size)}</span>{" "}
          bundles on screen, of at most <span className="num">{GLOBAL_BUDGET}</span>.{" "}
          <button className={s.linkish} onClick={() => go(null)}>
            back to communities
          </button>
        </p>
        {first.center_is_hub ? (
          <p className={s.hubNote}>
            <Seal kind="pending">hub</Seal> This node joins <span className="num">{fmt(first.neighbours)}</span> others.
            Only its <span className="num">{fmt(first.shown)}</span> most connected are drawn; the rest are folded into
            bundles.
          </p>
        ) : null}
        {message ? <p className={s.message}>{message}</p> : null}

        {sel ? (
          <div className={s.card}>
            <p className={s.kind}>
              {KINDS[sel.kind]}
              {sel.type ? ` · ${sel.type}` : ""}
              {sel.hub ? " · hub" : ""}
            </p>
            <h2 className={s.cardTitle}>
              <Names labels={sel.labels} fallback={sel.id} size="title" />
            </h2>
            <p className={s.muted}>
              <code>{sel.id}</code> · <span className="num">{fmt(sel.degree)}</span> connections
              {sel.documents ? (
                <>
                  {" "}
                  · <span className="num">{fmt(sel.documents)}</span> documents about it
                </>
              ) : null}
              {sel.lat != null ? (
                <>
                  {" "}
                  ·{" "}
                  <Link href={`/atlas/?lat=${sel.lat}&lon=${sel.lon}`}>
                    on the atlas
                  </Link>
                </>
              ) : null}
            </p>
            <div className={s.actions}>
              {sel.id !== centre ? <button onClick={() => go(sel.id)}>Centre here</button> : null}
              <button onClick={() => expand(sel.id)} disabled={busy}>
                Expand here
              </button>
              {sel.id !== centre ? (
                <button onClick={() => findPath(sel.id)} disabled={busy}>
                  Path from the centre
                </button>
              ) : null}
              {sel.kind === "document" ? <Link href={`/document/?id=${encodeURIComponent(sel.id)}`}>Read the document</Link> : null}
            </div>
            <EdgesOf id={sel.id} view={view} onPick={setSelected} />
            <NextSteps
              title="From this node"
              steps={[
                sel.kind === "document"
                  ? { label: "Read the document", href: `/document/?id=${encodeURIComponent(sel.id)}` }
                  : {
                      label: "Documents about it",
                      href: `/cases/?q=${encodeURIComponent(label(sel.labels, sel.id))}&seeds=${encodeURIComponent(sel.id)}`,
                      hint: "both lenses, starting here",
                    },
                ...(sel.lat != null ? [{ label: "On the atlas", href: `/atlas/?lat=${sel.lat}&lon=${sel.lon}`, hint: "what lies near it" }] : []),
              ]}
            />
          </div>
        ) : null}

        {bundle ? (
          <div className={s.card}>
            <p className={s.kind}>bundle</p>
            <h2 className={s.cardTitle}>
              {fmt(bundle.count)} {KINDS_PLURAL[bundle.kind]}, folded
            </h2>
            <p className={s.muted}>
              All linked to <Names labels={view.nodes.get(bundle.owner)?.labels ?? {}} fallback={bundle.owner} /> by “
              {bundle.relation_label}”. They are folded so the picture stays readable. A few of them:
            </p>
            <ul className={s.members}>
              {bundle.sample.map((n) => (
                <li key={n.id}>
                  <button onClick={() => go(n.id)}>
                    <Names labels={n.labels} fallback={n.id} />
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {path ? <PathCard path={path} onClear={() => setPath(null)} /> : null}

        <MarginNote>
          <p>
            Every line is a fact from Wikidata (with the revision it was read at) or a link from a document to what it is
            about. Nothing here is drawn because two texts look alike.
          </p>
          <p>
            Expanding adds a node&apos;s neighbours to the picture; when a node has more neighbours than fit, the least
            connected are folded into a bundle. Hubs such as centuries and India are never drawn with all their lines.
          </p>
        </MarginNote>
        <TextList
          title="Everything on screen, as text"
          items={[...view.edges.values()].map(
            (e) => `${label(view.nodes.get(e.source)?.labels ?? {}, e.source)} — ${e.relation_label} — ${label(view.nodes.get(e.target)?.labels ?? {}, e.target)}`,
          )}
        />
      </aside>
    </div>
  );
}

function EdgesOf({ id, view, onPick }: { id: string; view: Merged; onPick: (id: string) => void }) {
  const rows = [...view.edges.values()].filter((e) => e.source === id || e.target === id);
  if (!rows.length) return null;
  return (
    <ul className={s.edges}>
      {rows.slice(0, 40).map((e) => {
        const other = e.source === id ? e.target : e.source;
        const n = view.nodes.get(other);
        return (
          <li key={edgeKey(e)}>
            <span className={s.rel}>
              {e.source === id ? "" : "← "}
              {e.relation_label}
              {e.source === id ? " →" : ""}
            </span>
            <button onClick={() => onPick(other)}>{n ? label(n.labels, other) : other}</button>
            <span className={s.rev} title="Wikidata revision the fact was read at">
              {e.layer} · r{e.revision}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

function PathCard({ path, onClear }: { path: PathView; onClear: () => void }) {
  return (
    <div className={`${s.card} ${s.pathCard}`}>
      <p className={s.kind}>
        path{" "}
        {path.through_hubs ? (
          <Seal kind="pending">only through a hub</Seal>
        ) : path.through_hubs === false ? (
          <Seal kind="graph">avoids hubs</Seal>
        ) : null}
      </p>
      {path.paths.length === 0 ? (
        <p>No path of four steps or fewer joins them.</p>
      ) : (
        path.paths.map((p, i) => (
          <ol key={i} className={s.ribbon}>
            {p.nodes.map((n, j) => (
              <li key={n.id}>
                <span>{label(n.labels, n.id)}</span>
                {p.edges[j] ? <em>{stepLabel(p.edges[j]!, n.id)}</em> : null}
              </li>
            ))}
          </ol>
        ))
      )}
      <button className={s.linkish} onClick={onClear}>
        clear the path
      </button>
    </div>
  );
}

function TextList({ title, items }: { title: string; items: string[] }) {
  return (
    <details className={s.textList}>
      <summary>
        {title} ({fmt(items.length)})
      </summary>
      <ul>
        {items.map((x, i) => (
          <li key={i}>{x}</li>
        ))}
      </ul>
    </details>
  );
}
