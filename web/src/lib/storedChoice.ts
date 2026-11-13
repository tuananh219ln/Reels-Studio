import { useCallback, useSyncExternalStore } from "react";

const listeners = new Set<() => void>();

/** A small choice kept on this browser only (a folded menu, a filter): `[value, set]`, the server and a browser with
 * no storage reading `fallback`. */
export function useStoredChoice<T extends string>(key: string, fallback: T): [T, (next: T) => void] {
  const read = useCallback((): T => {
    try {
      return (window.localStorage.getItem(key) as T | null) ?? fallback;
    } catch {
      return fallback;
    }
  }, [key, fallback]);
  const value = useSyncExternalStore(
    (notify) => {
      listeners.add(notify);
      return () => void listeners.delete(notify);
    },
    read,
    () => fallback,
  );
  function set(next: T) {
    try {
      window.localStorage.setItem(key, next);
    } catch {}
    listeners.forEach((notify) => notify());
  }
  return [value, set];
}
