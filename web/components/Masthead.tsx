"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { api } from "@/lib/api";
import { useStored } from "@/lib/stored";
import { useResource } from "@/lib/useResource";

import s from "./Masthead.module.css";

const SECTIONS: [string, string][] = [
  ["/cases/", "Search"],
  ["/atlas/", "Atlas"],
  ["/graph/", "Graph"],
  ["/lab/", "Lab"],
  ["/ledger/", "Ledger"],
  ["/guide/", "Guide"],
];

type Theme = "auto" | "light" | "dark";

export function Masthead() {
  const path = usePathname() ?? "/";
  const router = useRouter();
  const [stored, setTheme] = useStored("theme", "auto");
  const [notes, setNotes] = useStored("notes", "off");
  const theme: Theme = stored === "light" || stored === "dark" ? stored : "auto";
  const [q, setQ] = useState("");
  const health = useResource(api.health, "health");

  useEffect(() => {
    const root = document.documentElement;
    if (theme === "auto") root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", theme);
  }, [theme]);

  const next: Record<Theme, Theme> = { auto: "light", light: "dark", dark: "auto" };
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (q.trim()) router.push(`/cases/?q=${encodeURIComponent(q.trim())}`);
  };

  let running = 0;
  let pending = 0;
  if (health.state === "ready") {
    running = (["corpus", "graph", "keyword"] as const).filter((k) => health.data[k].status === "ok").length;
    pending = Object.keys(health.data.planned).length;
  }

  return (
    <header className={s.masthead}>
      <a href="#main" className={s.skip}>
        Skip to the page
      </a>
      <div className={s.bar}>
        <Link href="/" className={s.mark} aria-label="HeritageRec, home">
          HeritageRec
        </Link>
        <nav aria-label="Sections" className={s.nav}>
          {SECTIONS.map(([href, name]) => (
            <Link key={href} href={href} className={s.link} aria-current={path.startsWith(href.slice(0, -1)) ? "page" : undefined}>
              {name}
            </Link>
          ))}
        </nav>
        {path.startsWith("/cases") ? null : (
          <form className={s.search} onSubmit={submit} role="search">
            <label htmlFor="mast-q" className="visually-hidden">
              Search the corpus
            </label>
            <input id="mast-q" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search · खोजें · ಹುಡುಕಿ" autoComplete="off" />
          </form>
        )}
        <div className={s.tools}>
          <Link href="/ledger/" className={s.status} title="Parts of the system that are running, and those not built yet">
            {health.state === "ready" ? (
              <>
                <i className={s.dotOk} aria-hidden /> {running} running <i className={s.dotPending} aria-hidden /> {pending} not built
              </>
            ) : health.state === "loading" ? (
              "…"
            ) : (
              <>
                <i className={s.dotPending} aria-hidden /> server not answering
              </>
            )}
          </Link>
          <button className={s.tool} aria-pressed={notes === "on"} onClick={() => setNotes(notes === "on" ? "off" : "on")}>
            Notes
          </button>
          <button className={s.tool} onClick={() => setTheme(next[theme])} aria-label={`Theme: ${theme}. Change theme`}>
            {theme === "auto" ? "Auto" : theme === "light" ? "Light" : "Dark"}
          </button>
        </div>
      </div>
    </header>
  );
}
