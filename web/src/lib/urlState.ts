"use client";

import { useSearchParams } from "next/navigation";
import { useCallback, useState } from "react";

const PAGE_KEY = "page";

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
      // A new search, filter, sort or tab starts its table on page 1 again.
      if (key !== PAGE_KEY) url.searchParams.delete(PAGE_KEY);
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

/** A table's page in the address (`?page=2`), spread into antd's `pagination`; page 1 is left out, and any other
 * change to the address goes back to it. */
export function useUrlPage(): { current: number; onChange: (page: number) => void } {
  const [page, setPage] = useUrlId(PAGE_KEY);
  return { current: page !== null && page > 0 ? page : 1, onChange: (next) => setPage(next === 1 ? null : next) };
}

/** useUrlChoice for a part of the page that may be hidden (a Kho kiến thức group opened earlier stays mounted): only
 * the shown one reads and writes the address, a hidden one keeps its own value. */
export function useUrlChoiceIf<T extends string | null>(
  shown: boolean,
  key: string,
  fallback: T,
  allowed?: readonly NonNullable<T>[],
): [T, (next: T) => void] {
  const inAddress = useUrlChoice(key, fallback, allowed);
  const own = useState<T>(fallback);
  return shown ? inAddress : own;
}

/** useUrlPage for a table that may be hidden, as useUrlChoiceIf. */
export function useUrlPageIf(shown: boolean): { current: number; onChange: (page: number) => void } {
  const inAddress = useUrlPage();
  const [current, onChange] = useState(1);
  return shown ? inAddress : { current, onChange };
}

/** Keeps only `keep` in the address, for a new group or tab whose lists start without the last one's filters. */
export function keepOnlyInAddress(keep: Record<string, string>) {
  const next = new URLSearchParams(keep);
  const query = next.toString();
  window.history.replaceState(null, "", window.location.pathname + (query ? `?${query}` : ""));
}
