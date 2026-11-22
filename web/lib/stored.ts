"use client";

import { useCallback, useSyncExternalStore } from "react";

// Per-viewer conveniences only (theme, a dismissed hint). Storage can be blocked or empty; every read falls back.
const EVENT = "heritagerec-stored";

function read(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function subscribe(notify: () => void) {
  window.addEventListener("storage", notify);
  window.addEventListener(EVENT, notify);
  return () => {
    window.removeEventListener("storage", notify);
    window.removeEventListener(EVENT, notify);
  };
}

/** A value kept in this browser; the pre-rendered page always starts from `fallback`. */
export function useStored(key: string, fallback: string): [string, (v: string) => void] {
  const value = useSyncExternalStore(
    subscribe,
    () => read(key) ?? fallback,
    () => fallback,
  );
  const set = useCallback(
    (v: string) => {
      try {
        localStorage.setItem(key, v);
      } catch {
        /* ignored: the value then lasts for this page only */
      }
      window.dispatchEvent(new Event(EVENT));
    },
    [key],
  );
  return [value, set];
}
