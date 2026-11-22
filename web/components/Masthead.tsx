"use client";

import Link from "next/link";
import { motion, useReducedMotion } from "motion/react";
import { usePathname } from "next/navigation";
import { useEffect } from "react";

import { Finder } from "@/components/Finder";

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
  const reduce = useReducedMotion();
  const [stored, setTheme] = useStored("theme", "auto");
  const [notes, setNotes] = useStored("notes", "off");
  const theme: Theme = stored === "light" || stored === "dark" ? stored : "auto";
  const health = useResource(api.health, "health");

  useEffect(() => {
    const root = document.documentElement;
    if (theme === "auto") root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", theme);
  }, [theme]);

  const next: Record<Theme, Theme> = { auto: "light", light: "dark", dark: "auto" };

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
          {SECTIONS.map(([href, name]) => {
            const here = path.startsWith(href.slice(0, -1));
            return (
              <Link key={href} href={href} className={s.link} aria-current={here ? "page" : undefined}>
                {name}
                {/* One underline that slides from the old section to the new one. */}
                {here ? (
                  <motion.span layoutId="nav-underline" className={s.underline} transition={reduce ? { duration: 0 } : { type: "spring", stiffness: 520, damping: 40 }} />
                ) : null}
              </Link>
            );
          })}
        </nav>
        {path.startsWith("/cases") ? null : <Finder />}
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
          <button className={`${s.tool} ${s.theme}`} onClick={() => setTheme(next[theme])} aria-label={`Theme: ${theme}. Change theme`} title={`Theme: ${theme}`}>
            <motion.svg
              key={theme}
              viewBox="0 0 16 16"
              width="15"
              height="15"
              aria-hidden
              initial={reduce ? false : { rotate: -90, opacity: 0 }}
              animate={{ rotate: 0, opacity: 1 }}
              transition={{ duration: 0.3, ease: [0.2, 0.8, 0.2, 1] }}
            >
              {theme === "light" ? (
                <g fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                  <circle cx="8" cy="8" r="3" />
                  {[0, 45, 90, 135, 180, 225, 270, 315].map((a) => (
                    <line key={a} x1="8" y1="1.5" x2="8" y2="3" transform={`rotate(${a} 8 8)`} />
                  ))}
                </g>
              ) : theme === "dark" ? (
                <path d="M12.5 10.5A5.5 5.5 0 0 1 5.5 3.5a5.5 5.5 0 1 0 7 7z" fill="currentColor" />
              ) : (
                <g>
                  <circle cx="8" cy="8" r="5.5" fill="none" stroke="currentColor" strokeWidth="1.5" />
                  <path d="M8 2.5a5.5 5.5 0 0 1 0 11z" fill="currentColor" />
                </g>
              )}
            </motion.svg>
          </button>
        </div>
      </div>
    </header>
  );
}
