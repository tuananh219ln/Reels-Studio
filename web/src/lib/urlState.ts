"use client";

import { useSearchParams } from "next/navigation";
import { useCallback } from "react";

/** One value of the address's query string (`?key=value`), and a setter that replaces it in place: no new history
 * entry and no request, as Next keeps useSearchParams in step with `history.replaceState`. `null` means absent.
 * A page using it renders inside a Suspense boundary, as its address is only known in the browser. */
export function useUrlParam(key: string): [string | null, (next: string | null) => void] {
  const value = useSearchParams().get(key);
  const set = useCallback(
    (next: string | null) => {
      const url = new URL(window.location.href);
      if (next === null) url.searchParams.delete(key);
      else url.searchParams.set(key, next);
      window.history.replaceState(null, "", url.pathname + url.search + url.hash);
    },
    [key],
  );
  return [value, set];
}

/** A list's search, filter, sort or tab kept in the address, so a reload or a shared link shows the same list. The
 * `fallback` is left out of the address; a value outside `allowed` (an old or hand-typed link) reads as the fallback. */
export function useUrlChoice<T extends string | null>(
  key: string,
  fallback: T,
  allowed?: readonly NonNullable<T>[],
): [T, (next: T) => void] {
  const [raw, setRaw] = useUrlParam(key);
  const value = raw === null || (allowed && !allowed.includes(raw as NonNullable<T>)) ? fallback : (raw as T);
  const set = useCallback((next: T) => setRaw(next === fallback ? null : next), [fallback, setRaw]);
  return [value, set];
}

/** A chosen id (a Page, a group) in the address; `null` when none is chosen. */
export function useUrlId(key: string): [number | null, (next: number | null) => void] {
  const [raw, setRaw] = useUrlParam(key);
  const id = raw !== null && /^\d+$/.test(raw) ? Number(raw) : null;
  const set = useCallback((next: number | null) => setRaw(next === null ? null : String(next)), [setRaw]);
  return [id, set];
}
