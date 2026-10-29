"use client";

import { createContext, useContext } from "react";
import type { Me } from "@/lib/api";

export const MeContext = createContext<{ me: Me; setMe: (me: Me) => void } | null>(null);

export function useMe() {
  const value = useContext(MeContext);
  if (!value) {
    throw new Error("useMe must be used inside AppShell");
  }
  return value;
}
