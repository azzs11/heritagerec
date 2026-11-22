"use client";

import { useState } from "react";

import { fmt } from "./ui";
import s from "./BarList.module.css";

/** One series of counts as thin ruled bars with direct labels, and the same numbers as a table on request. */
export function BarList({
  title,
  rows,
  source,
  tone = "ink",
}: {
  title: string;
  rows: { key: string; label: string; value: number }[];
  source: string;
  tone?: "ink" | "text" | "graph";
}) {
  const [table, setTable] = useState(false);
  const max = Math.max(1, ...rows.map((r) => r.value));
  const total = rows.reduce((a, r) => a + r.value, 0);
  return (
    <figure className={s.figure}>
      <figcaption className={s.caption}>
        <span>{title}</span>
        <button className={s.toggle} onClick={() => setTable(!table)} aria-pressed={table}>
          {table ? "show bars" : "show table"}
        </button>
      </figcaption>
      {table ? (
        <table className={s.table}>
          <thead>
            <tr>
              <th scope="col">Group</th>
              <th scope="col">Count</th>
              <th scope="col">Share</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.key}>
                <td>{r.label}</td>
                <td className="num">{fmt(r.value)}</td>
                <td className="num">{fmt((100 * r.value) / total, 1)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <ul className={s.list}>
          {rows.map((r) => (
            <li key={r.key} className={s.row} title={`${r.label}: ${fmt(r.value)} (${fmt((100 * r.value) / total, 1)}%)`}>
              <span className={s.name}>{r.label}</span>
              <span className={s.track} aria-hidden>
                <span className={`${s.bar} ${s[tone]}`} style={{ width: `${Math.max(0.6, (100 * r.value) / max)}%` }} />
              </span>
              <span className={`${s.value} num`}>{fmt(r.value)}</span>
            </li>
          ))}
        </ul>
      )}
      <p className={s.source}>
        from <code>{source}</code>
      </p>
    </figure>
  );
}
