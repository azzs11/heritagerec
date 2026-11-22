"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect } from "react";

import { useStored } from "@/lib/stored";

import s from "./Masthead.module.css";

const SECTIONS: [string, string, string][] = [
  ["/", "Story", "i"],
  ["/atlas/", "Atlas", "ii"],
  ["/cases/", "Cases", "iii"],
  ["/graph/", "Graph", "iv"],
  ["/ledger/", "Ledger", "v"],
  ["/lab/", "Lab", "vi"],
  ["/guide/", "Guide", "vii"],
];

type Theme = "auto" | "light" | "dark";

export function Masthead() {
  const path = usePathname() ?? "/";
  const [stored, setTheme] = useStored("theme", "auto");
  const theme: Theme = stored === "light" || stored === "dark" ? stored : "auto";

  useEffect(() => {
    const root = document.documentElement;
    if (theme === "auto") root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", theme);
  }, [theme]);

  const next: Record<Theme, Theme> = { auto: "light", light: "dark", dark: "auto" };

  return (
    <header className={s.masthead}>
      <a href="#main" className={s.skip}>
        Skip to the page
      </a>
      <div className={s.bar}>
        <Link href="/" className={s.title}>
          Heritage<span>Rec</span>
        </Link>
        <p className={s.question}>Does the shape of knowledge find what words miss?</p>
        <button className={s.theme} onClick={() => setTheme(next[theme])} aria-label={`Theme: ${theme}. Change theme`}>
          {theme === "auto" ? "◐ auto" : theme === "light" ? "○ paper" : "● night"}
        </button>
      </div>
      <nav aria-label="Sections" className={s.nav}>
        {SECTIONS.map(([href, name, folio]) => {
          const here = href === "/" ? path === "/" : path.startsWith(href.replace(/\/$/, ""));
          return (
            <Link key={href} href={href} className={s.link} aria-current={here ? "page" : undefined}>
              <span className={s.folio}>{folio}</span>
              {name}
            </Link>
          );
        })}
      </nav>
    </header>
  );
}
