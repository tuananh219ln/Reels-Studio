"use client";

import { useState } from "react";

export type View = "grid" | "list";

/** "Dạng lưới" or "Dạng danh sách" for a page, remembered in this browser under `key`; grid until chosen. */
export function useRememberedView(key: string): [View, (next: View) => void] {
  const [view, setView] = useState<View>(() => {
    try {
      return window.localStorage.getItem(key) === "list" ? "list" : "grid";
    } catch {
      return "grid";
    }
  });

  function choose(next: View) {
    setView(next);
    try {
      window.localStorage.setItem(key, next);
    } catch {
      // A browser that refuses storage just forgets the choice.
    }
  }

  return [view, choose];
}
