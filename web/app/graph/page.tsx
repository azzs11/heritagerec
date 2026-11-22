"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState } from "react";

import { LiveGraph, Legend, groupOf, type Group, type LiveEdge, type LiveNode } from "@/components/LiveGraph";
import { Load, MarginNote, Names, Seal, fmt } from "@/components/ui";
import { NextSteps } from "@/components/Wayfinding";
import { api, label, stepLabel, type Bundle, type EgoView, type GraphEdge, type NodeCard, type Overview, type PathView } from "@/lib/api";
import { KINDS, KINDS_PLURAL } from "@/lib/names";
import { useTrailStep } from "@/lib/trail";
import { useResource } from "@/lib/useResource";

import s from "./graph.module.css";

const GLOBAL_BUDGET = 400; // the most marks on screen after growing neighbourhoods

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
        <h1 className={s.title}>{centre ? "Graph · neighbourhood" : "Graph · communities"}</h1>
        {centre ? <Legend groups={["built", "people", "culture", "other", "time", "document"]} /> : null}
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
      <label htmlFor="find" className="visually-hidden">
        Find a place, person, dynasty or document
      </label>
      <input id="find" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Find: Hampi, हम्पी, ಹಂಪೆ…" autoComplete="off" />
      {q.trim().length >= 2 && res.state === "ready" ? (
        <ul className={s.found} role="listbox" aria-label="Matches">
          {res.data.length === 0 ? <li className={s.muted}>nothing by that name</li> : null}
          {res.data.slice(0, 10).map((n) => (
            <li key={n.id}>
              <button onClick={() => (setQ(""), onPick(n.id))}>
                <i className={s[`g_${groupOf(n.kind, n.type)}`]} aria-hidden /> <Names labels={n.labels} fallback={n.id} />{" "}
                <span className={s.muted}>{n.type ?? KINDS[n.kind]}</span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

// ---------- overview: the connected core, and a shelf of the communities that touch nothing else ----------

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
  const linked = useMemo(() => new Set(o.links.flatMap((l) => [l.a, l.b])), [o]);
  const core = o.communities.filter((c) => linked.has(c.id));
  const shelf = o.communities.filter((c) => !linked.has(c.id));
  const { nodes, edges } = useMemo(() => {
    const max = Math.max(...core.map((c) => c.size), 1);
    const nodes: LiveNode[] = core.map((c, i) => ({
      id: `c${c.id}`,
      label: c.label ?? `community ${c.id}`,
      group: "other" as Group,
      size: 4 + 16 * Math.sqrt(c.size / max),
      hub: i < 12,
    }));
    const edges: LiveEdge[] = o.links.map((l) => ({ id: `l${l.a}-${l.b}`, source: `c${l.a}`, target: `c${l.b}`, label: `${l.edges} shared ${l.edges === 1 ? "fact" : "facts"}` }));
    return { nodes, edges };
    // `core` is derived from `o`.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [o]);
  const c = picked != null ? o.communities.find((x) => x.id === picked) : null;
  const maxShelf = Math.max(...shelf.map((x) => x.size), 1);

  return (
    <div className={s.stage}>
      <div className={s.canvas}>
        <LiveGraph
          nodes={nodes}
          edges={edges}
          selected={picked != null ? `c${picked}` : null}
          onSelect={(id) => setPicked(id ? Number(id.slice(1)) : null)}
          focusOnSelect={false}
          ariaLabel={`${core.length} communities that share facts with others, joined where they do`}
        />
      </div>
      <aside className={s.panel}>
        {c ? (
          <div className={s.card}>
            <p className={s.kind}>community</p>
            <h2 className={s.cardTitle}>{c.label}</h2>
            <p className={s.muted}>
              <span className="num">{fmt(c.size)}</span> nodes: <span className="num">{fmt(c.documents)}</span> documents,{" "}
              <span className="num">{fmt(c.entities)}</span> entities (<span className="num">{fmt(c.placed)}</span> on the map)
            </p>
            <p className="label">its most connected members</p>
            <TopMembers ids={c.top} go={go} />
          </div>
        ) : (
          <p className={s.lede}>
            The graph without its hubs, grouped into communities. <b className="num">{fmt(core.length)}</b> share facts
            with one another and are drawn on the left; <b className="num">{fmt(shelf.length)}</b> touch no other and wait
            on the shelf below. Choose any to see what it is made of.
          </p>
        )}
        <h3 className={s.shelfTitle}>
          The shelf <span className="num">{fmt(shelf.length)}</span>
        </h3>
        <ul className={s.shelf}>
          {shelf.map((x) => (
            <li key={x.id}>
              <button onClick={() => setPicked(x.id)} aria-pressed={picked === x.id}>
                <span className={s.shelfName}>{x.label ?? `community ${x.id}`}</span>
                <span className={s.shelfBar} aria-hidden>
                  <i style={{ width: `${(100 * x.size) / maxShelf}%` }} />
                </span>
                <span className="num">{fmt(x.size)}</span>
              </button>
            </li>
          ))}
        </ul>
        <p className={s.muted}>
          Left out: <span className="num">{fmt(o.others.communities)}</span> communities under {o.min_size} nodes (
          <span className="num">{fmt(o.others.nodes)}</span> nodes in all).
        </p>
        <MarginNote>
          <p>
            Communities are found by the Louvain method with a fixed seed, on the graph without its hubs. They are a way
            to look at the graph, not a finding about heritage.
          </p>
        </MarginNote>
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
                <i className={s[`g_${groupOf(n.kind, n.type)}`]} aria-hidden /> <Names labels={n.labels} fallback={n.id} />
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
  near: Map<string, string>; // the node each one grew out of
}

const pairKey = (a: string, b: string) => (a < b ? `${a}|${b}` : `${b}|${a}`);
const edgeKey = (e: GraphEdge) => `${e.source}|${e.relation}|${e.target}`;

function merge(into: Merged, v: EgoView, grewFrom: string): Merged {
  const out: Merged = { nodes: new Map(into.nodes), edges: new Map(into.edges), bundles: new Map(into.bundles), near: new Map(into.near) };
  const ring = v.ring ?? {};
  for (const n of v.nodes) {
    if (!out.nodes.has(n.id)) {
      // Grow out of a neighbour that is already placed, nearer the centre if the view says which.
      const parent = v.edges
        .filter((e) => e.source === n.id || e.target === n.id)
        .map((e) => (e.source === n.id ? e.target : e.source))
        .filter((m) => out.nodes.has(m) || (ring[m] ?? 9) < (ring[n.id] ?? 9))
        .sort((a, b) => (ring[a] ?? 9) - (ring[b] ?? 9))[0];
      out.near.set(n.id, parent ?? grewFrom);
    }
    out.nodes.set(n.id, n);
  }
  v.edges.forEach((e) => out.edges.set(edgeKey(e), e));
  v.bundles.forEach((b) => out.bundles.set(`${v.center}|${b.relation}|${b.direction}|${b.kind}`, { ...b, owner: v.center }));
  return out;
}

function Neighbourhood({ centre, go }: { centre: string; go: (id: string | null) => void }) {
  const first = useResource(() => api.ego(centre, 150, undefined, 2), `ego2|${centre}`);
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
  const [view, setView] = useState<Merged>(() => merge({ nodes: new Map(), edges: new Map(), bundles: new Map(), near: new Map() }, first, centre));
  const [selected, setSelected] = useState<string | null>(centre);
  const [path, setPath] = useState<PathView | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const marks = view.nodes.size + view.bundles.size;

  const { nodes, edges } = useMemo(() => {
    const maxDeg = Math.max(...[...view.nodes.values()].filter((n) => n.kind !== "period").map((n) => n.degree), 1);
    const nodes: LiveNode[] = [...view.nodes.values()].map((n) => ({
      id: n.id,
      label: label(n.labels, n.id),
      group: groupOf(n.kind, n.type),
      size: n.id === centre ? 15 : n.kind === "document" ? (n.image ? 6 : 3.5) : n.kind === "period" ? 5 : 4.5 + 9 * Math.sqrt(Math.min(n.degree, maxDeg) / maxDeg),
      hub: n.hub || n.id === centre,
      image: n.kind === "document" ? n.image : undefined,
      near: view.near.get(n.id),
    }));
    // One line per pair of nodes; several facts between a pair are named together on it.
    const pairs = new Map<string, LiveEdge>();
    for (const e of view.edges.values()) {
      const k = pairKey(e.source, e.target);
      const prev = pairs.get(k);
      pairs.set(k, prev ? { ...prev, label: `${prev.label} · ${e.relation_label}` } : { id: k, source: e.source, target: e.target, label: e.relation_label });
    }
    const edges = [...pairs.values()];
    for (const [k, b] of view.bundles) {
      nodes.push({ id: `bundle:${k}`, label: `+${fmt(b.count)} ${KINDS_PLURAL[b.kind]}`, group: "bundle", size: 4, near: b.owner });
      edges.push({ id: `bundle-edge:${k}`, source: b.owner, target: `bundle:${k}`, label: b.relation_label });
    }
    return { nodes, edges };
  }, [view, centre]);

  const highlight = useMemo(() => {
    const p = path?.paths[0];
    if (!p) return null;
    return { nodes: p.nodes.map((n) => n.id), edges: p.edges.map((e) => pairKey(e.source, e.target)) };
  }, [path]);

  const expand = async (id: string) => {
    setBusy(true);
    setMessage(null);
    try {
      const room = Math.min(150, GLOBAL_BUDGET - marks + 1);
      if (room <= 2) {
        setMessage(`The picture holds ${GLOBAL_BUDGET} marks at most. Centre on this node instead to see its own neighbourhood.`);
        return;
      }
      const v = await api.ego(id, room);
      setView((cur) => merge(cur, v, id));
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
      setView((cur) => {
        let out = cur;
        for (const pp of p.paths) out = merge(out, { center: centre, budget: 0, nodes: pp.nodes, edges: pp.edges, bundles: [], neighbours: 0, shown: 0, center_is_hub: false }, centre);
        return out;
      });
      setPath(p);
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const sel = selected && !selected.startsWith("bundle:") ? view.nodes.get(selected) : null;
  const bundle = selected?.startsWith("bundle:") ? view.bundles.get(selected.slice(7)) : null;

  return (
    <div className={s.stage}>
      <div className={s.canvas} aria-busy={busy}>
        <LiveGraph
          nodes={nodes}
          edges={edges}
          selected={selected}
          path={highlight}
          onSelect={setSelected}
          ariaLabel={`Neighbourhood of ${label(centreCard?.labels ?? {}, centre)}: ${view.nodes.size} nodes`}
        />
        <p className={s.canvasHint}>
          drag to move · scroll to zoom · hover to light a node&apos;s facts · click to choose
        </p>
      </div>
      <aside className={s.panel}>
        <p className={s.budget}>
          <span className="num">{fmt(view.nodes.size)}</span> nodes · <span className="num">{fmt(view.bundles.size)}</span>{" "}
          bundles · two steps out{first.second_ring ? "" : " (a hub opens one step)"} ·{" "}
          <button className={s.linkish} onClick={() => go(null)}>
            all communities
          </button>
        </p>
        {first.center_is_hub ? (
          <p className={s.hubNote}>
            <Seal kind="pending">hub</Seal> This node joins <span className="num">{fmt(first.neighbours)}</span> others; its{" "}
            <span className="num">{fmt(first.shown)}</span> most connected are drawn and the rest folded into bundles.
          </p>
        ) : null}
        {message ? <p className={s.message}>{message}</p> : null}

        {sel ? (
          <div className={s.card}>
            <p className={s.kind}>
              <i className={s[`g_${groupOf(sel.kind, sel.type)}`]} aria-hidden />
              {KINDS[sel.kind]}
              {sel.type ? ` · ${sel.type}` : ""}
              {sel.hub ? " · hub" : ""}
            </p>
            <h2 className={s.cardTitle}>
              <Names labels={sel.labels} fallback={sel.id} size="title" />
            </h2>
            {sel.image ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img className={s.cardImage} src={sel.image.thumb} alt="" referrerPolicy="no-referrer" onError={(e) => (e.currentTarget.style.display = "none")} />
            ) : null}
            <p className={s.muted}>
              <span className="num">{fmt(sel.degree)}</span> connections
              {sel.documents ? (
                <>
                  {" "}
                  · <span className="num">{fmt(sel.documents)}</span> documents about it
                </>
              ) : null}
            </p>
            <div className={s.actions}>
              {sel.id !== centre ? <button onClick={() => go(sel.id)}>Centre here</button> : null}
              <button onClick={() => expand(sel.id)} disabled={busy}>
                Grow from here
              </button>
              {sel.id !== centre ? (
                <button onClick={() => findPath(sel.id)} disabled={busy}>
                  Walk the path
                </button>
              ) : null}
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
              {bundle.relation_label}”, folded so the picture stays readable. A few of them:
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

        {!sel && !bundle ? <p className={s.muted}>Choose a node to see its facts, grow the graph from it, or walk a path to it.</p> : null}
        {path ? <PathCard path={path} onClear={() => setPath(null)} /> : null}

        <MarginNote>
          <p>
            Every line is a fact from Wikidata (with the revision it was read at) or a link from a document to what it is
            about. Nothing here is drawn because two texts look alike.
          </p>
          <p>
            Colours group the entity types in three: sites and places, people and polities, culture and style; the type is
            always named in words too. Photographs are museum objects under open licences.
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
            <span className={s.rel}>{stepLabel(e, id)}</span>
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
        {path.through_hubs ? <Seal kind="pending">only through a hub</Seal> : path.through_hubs === false ? <Seal kind="graph">avoids hubs</Seal> : null}
      </p>
      {path.paths.length === 0 ? (
        <p>No path of four steps or fewer joins them.</p>
      ) : (
        <ol className={s.ribbon}>
          {path.paths[0]!.nodes.map((n, j) => (
            <li key={n.id}>
              <span>{label(n.labels, n.id)}</span>
              {path.paths[0]!.edges[j] ? <em>{stepLabel(path.paths[0]!.edges[j]!, n.id)}</em> : null}
            </li>
          ))}
        </ol>
      )}
      <button className={s.linkish} onClick={onClear}>
        clear the path
      </button>
      <Link className={s.linkish} href={`/lab/`}>
        why hubs matter
      </Link>
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
