"use client";

import { useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";

import { groupOf } from "@/components/LiveGraph";
import { api, label, type NodeCard } from "@/lib/api";
import { useResource } from "@/lib/useResource";

import s from "./Finder.module.css";

interface Option {
  key: string;
  title: string;
  hint: string;
  href: string;
  dot?: string;
}

/**
 * The search box in the masthead: as the reader types it offers "search for these words" first, then the places,
 * people and dynasties the graph knows by that name. Arrow keys move, Enter opens, Escape closes; "/" or Cmd/Ctrl+K
 * focuses it from anywhere on the site.
 */
export function Finder() {
  const router = useRouter();
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const list = useId();
  const term = q.trim();
  const found = useResource(term.length >= 2 ? () => api.find(term) : null, `mast|${term}`);

  useEffect(() => {
    const onKey = (e: globalThis.KeyboardEvent) => {
      const typing = e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement || e.target instanceof HTMLSelectElement;
      if ((e.key === "k" && (e.metaKey || e.ctrlKey)) || (e.key === "/" && !typing && !location.pathname.startsWith("/cases"))) {
        e.preventDefault();
        input.current?.focus();
        input.current?.select();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const options: Option[] = term
    ? [
        { key: "search", title: `Search for “${term}”`, hint: "both lenses", href: `/cases/?q=${encodeURIComponent(term)}` },
        ...(found.state === "ready"
          ? found.data.slice(0, 6).map((n: NodeCard) => ({
              key: n.id,
              title: label(n.labels, n.id),
              hint: n.kind === "document" ? "document" : (n.type ?? n.kind),
              href: n.kind === "document" ? `/document/?id=${encodeURIComponent(n.id)}` : `/graph/?node=${encodeURIComponent(n.id)}`,
              dot: groupOf(n.kind, n.type),
            }))
          : []),
      ]
    : [];

  const go = (o: Option | undefined) => {
    if (!o) return;
    router.push(o.href);
    setOpen(false);
    setQ("");
    input.current?.blur();
  };

  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setOpen(true);
      setActive((a) => Math.min(a + 1, options.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => Math.max(a - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      go(options[active] ?? options[0]);
    } else if (e.key === "Escape") {
      setOpen(false);
      input.current?.blur();
    }
  };

  const showList = open && options.length > 0;
  return (
    <div className={s.finder} role="search">
      <span className={s.glass} aria-hidden>
        ⌕
      </span>
      <input
        ref={input}
        role="combobox"
        aria-expanded={showList}
        aria-controls={list}
        aria-activedescendant={showList ? `${list}-${active}` : undefined}
        aria-label="Search the archive, or find a place, person or dynasty"
        placeholder="Search · खोजें · ಹುಡುಕಿ"
        value={q}
        onChange={(e) => {
          setQ(e.target.value);
          setActive(0);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => window.setTimeout(() => setOpen(false), 120)}
        onKeyDown={onKey}
        autoComplete="off"
      />
      {q ? (
        <button className={s.clear} onClick={() => (setQ(""), input.current?.focus())} aria-label="Clear">
          ×
        </button>
      ) : (
        <kbd className={s.kbd} aria-hidden>
          /
        </kbd>
      )}
      {showList ? (
        <ul id={list} role="listbox" className={s.list}>
          {options.map((o, i) => (
            <li
              key={o.key}
              id={`${list}-${i}`}
              role="option"
              aria-selected={i === active}
              className={i === active ? s.active : undefined}
              onMouseEnter={() => setActive(i)}
              onMouseDown={(e) => (e.preventDefault(), go(o))}
            >
              {o.dot ? <i className={`${s.dot} ${s[`d_${o.dot}`]}`} aria-hidden /> : <span className={s.arrow} aria-hidden>→</span>}
              <span className={s.title}>{o.title}</span>
              <span className={s.hint}>{o.hint}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
