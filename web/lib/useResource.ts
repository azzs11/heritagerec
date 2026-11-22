"use client";

import { useEffect, useState } from "react";

import { Refused, Unavailable } from "./api";

export type Resource<T> =
  | { state: "loading" }
  | { state: "ready"; data: T }
  | { state: "unavailable"; error: Unavailable }
  | { state: "refused"; error: Refused }
  | { state: "failed"; error: Error };

/** Loads once per key; a stale answer for an older key is dropped, so fast typing never shows the wrong result. */
export function useResource<T>(load: (() => Promise<T>) | null, key: string): Resource<T> {
  const [res, setRes] = useState<{ key: string; value: Resource<T> }>({ key: "", value: { state: "loading" } });
  useEffect(() => {
    if (!load) return;
    let live = true;
    load().then(
      (data) => live && setRes({ key, value: { state: "ready", data } }),
      (error: unknown) => {
        if (!live) return;
        if (error instanceof Unavailable) setRes({ key, value: { state: "unavailable", error } });
        else if (error instanceof Refused) setRes({ key, value: { state: "refused", error } });
        else setRes({ key, value: { state: "failed", error: error as Error } });
      },
    );
    return () => {
      live = false;
    };
    // `load` is rebuilt on every render by callers; the key says when the request really changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return res.key === key ? res.value : { state: "loading" };
}
