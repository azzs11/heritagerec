"use client";

import { useCallback, useEffect, useSyncExternalStore } from "react";

// The reader's own path through the archive in this tab: searches, documents, entities, places.
// Kept in sessionStorage (a per-tab convenience); the page works the same without it.

export interface Step {
  kind: "search" | "document" | "entity" | "place";
  label: string;
  href: string;
}

const KEY = "trail";
const EVENT = "heritagerec-trail";
const MAX = 7;
const EMPTY: Step[] = [];
let cache: { raw: string | null; steps: Step[] } = { raw: null, steps: EMPTY };

function read(): Step[] {
  let raw: string | null = null;
  try {
    raw = sessionStorage.getItem(KEY);
  } catch {
    return EMPTY;
  }
  if (raw !== cache.raw) {
    try {
      cache = { raw, steps: raw ? (JSON.parse(raw) as Step[]) : EMPTY };
    } catch {
      cache = { raw, steps: EMPTY };
    }
  }
  return cache.steps;
}

function subscribe(notify: () => void) {
  window.addEventListener(EVENT, notify);
  return () => window.removeEventListener(EVENT, notify);
}

function write(steps: Step[]) {
  try {
    sessionStorage.setItem(KEY, JSON.stringify(steps));
  } catch {
    /* blocked storage: the trail simply stays empty */
  }
  window.dispatchEvent(new Event(EVENT));
}

export function useTrail(): [Step[], () => void] {
  const steps = useSyncExternalStore(subscribe, read, () => EMPTY);
  const clear = useCallback(() => write([]), []);
  return [steps, clear];
}

/** Adds a step when a page shows something; revisiting a step moves it to the end instead of repeating it. */
export function useTrailStep(step: Step | null) {
  const key = step ? `${step.kind}|${step.href}|${step.label}` : "";
  useEffect(() => {
    if (!step) return;
    const rest = read().filter((s) => s.href !== step.href);
    write([...rest, step].slice(-MAX));
    // `key` identifies the step; the object itself is rebuilt on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
}
