"use client";

import { useState } from "react";

import { Load, MarginNote, Seal, fmt } from "@/components/ui";
import { api, type LedgerRow } from "@/lib/api";
import { SUPERSEDED } from "@/lib/names";
import { useResource } from "@/lib/useResource";

import s from "../pages.module.css";

export default function Ledger() {
  const rows = useResource(api.ledger, "ledger");
  const health = useResource(api.health, "health");
  return (
    <article className="page">
      <header className={s.head}>
        <h1 className={s.title}>Where every number comes from</h1>
        <p className={s.lede}>
          Each figure on this site is read from a file that a script in the repository wrote. Here they are, with the
          date each was built and the commit of the code that built it, so any number can be traced and rebuilt.
        </p>
      </header>

      <section className="folio">
        <div>
          <h2 className={s.h2}>The parts of the system</h2>
          <Load res={health} what="the parts">
            {(h) => (
              <div className={s.scroll} role="region" aria-label="Parts of the system" tabIndex={0}>
              <table className={s.table}>
                <thead>
                  <tr>
                    <th scope="col">Part</th>
                    <th scope="col">State</th>
                    <th scope="col">Detail</th>
                  </tr>
                </thead>
                <tbody>
                  {(["corpus", "graph", "keyword"] as const).map((k) => (
                    <tr key={k}>
                      <td>{k}</td>
                      <td>{h[k].status === "ok" ? <Seal kind="measured">running</Seal> : <Seal kind="missing">missing</Seal>}</td>
                      <td className={s.small}>
                        {h[k].status === "ok"
                          ? Object.entries(h[k])
                              .filter(([key]) => key !== "status")
                              .map(([key, v]) => `${key}: ${typeof v === "object" ? JSON.stringify(v) : String(v)}`)
                              .join(" · ")
                          : `${h[k].reason}. To fix: ${h[k].fix}`}
                      </td>
                    </tr>
                  ))}
                  {Object.entries(h.planned).map(([k, v]) => (
                    <tr key={k}>
                      <td>{k.replace(/_/g, " ")}</td>
                      <td>
                        <Seal kind="pending">not built yet</Seal>
                      </td>
                      <td className={s.small}>{v.see}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              </div>
            )}
          </Load>

          <h2 className={s.h2}>Result files</h2>
          <Load res={rows} what="the result files">
            {(r) => <Files rows={r} />}
          </Load>
        </div>
        <aside>
          <MarginNote>
            <p>
              A commit is a fixed version of the code. When a file names one, checking out that commit and running the
              script named in the file&apos;s folder rebuilds it.
            </p>
            <p>
              Files from before the corpus was rebuilt live in <code>legacy/</code> and are not listed; the one such
              file still in <code>results/</code> is marked superseded. They trace the conference version and are never
              used as evidence.
            </p>
          </MarginNote>
        </aside>
      </section>
    </article>
  );
}

function Files({ rows }: { rows: LedgerRow[] }) {
  const [q, setQ] = useState("");
  const [order, setOrder] = useState<"name" | "built">("name");
  const term = q.trim().toLowerCase();
  const shown = rows
    .filter((r) => !term || r.file.toLowerCase().includes(term) || (r.commit ?? "").startsWith(term))
    .sort((a, b) => (order === "built" ? (b.built ?? "").localeCompare(a.built ?? "") || a.file.localeCompare(b.file) : a.file.localeCompare(b.file)));
  const groups = new Map<string, LedgerRow[]>();
  for (const r of shown) {
    const folder = r.file.split("/").slice(0, 2).join("/");
    groups.set(folder, [...(groups.get(folder) ?? []), r]);
  }
  return (
    <>
      <div className={s.tools}>
        <label className="visually-hidden" htmlFor="ledger-q">
          Filter result files
        </label>
        <input id="ledger-q" className={s.filter} placeholder="Filter by file name or commit" value={q} onChange={(e) => setQ(e.target.value)} />
        <div className={s.segmented} role="group" aria-label="Order">
          <button aria-pressed={order === "name"} onClick={() => setOrder("name")}>
            by name
          </button>
          <button aria-pressed={order === "built"} onClick={() => setOrder("built")}>
            newest first
          </button>
        </div>
        <span className={s.small}>
          <span className="num">{fmt(shown.length)}</span> of <span className="num">{fmt(rows.length)}</span> files
        </span>
      </div>
      {shown.length === 0 ? <p className={s.small}>No result file matches that.</p> : null}
      {[...groups.entries()].map(([folder, files]) => (
        <details key={folder} className={s.group} open>
          <summary className={s.h3}>
            <code>{folder}/</code> <span className={s.small}>{files.length} files</span>
          </summary>
          <div className={s.scroll} role="region" aria-label={`Result files in ${folder}`} tabIndex={0}>
            <table className={s.table}>
              <thead>
                <tr>
                  <th scope="col">File</th>
                  <th scope="col">Built</th>
                  <th scope="col">Commit</th>
                  <th scope="col">Size</th>
                </tr>
              </thead>
              <tbody>
                {files.map((f) => (
                  <tr key={f.file}>
                    <td className={s.file}>
                      <code>{f.file.slice(folder.length + 1)}</code>
                      {SUPERSEDED[f.file] ? (
                        <span className={s.small}>
                          {" "}
                          <Seal kind="pending">superseded</Seal> {SUPERSEDED[f.file]}
                        </span>
                      ) : null}
                    </td>
                    <td className="num">{f.built ? f.built.slice(0, 10) : <span className={s.faint}>not recorded</span>}</td>
                    <td className="num">{f.commit ? f.commit.slice(0, 7) : <span className={s.faint}>not recorded</span>}</td>
                    <td className="num">{fmt(f.bytes / 1024, 1)} KB</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      ))}
    </>
  );
}
