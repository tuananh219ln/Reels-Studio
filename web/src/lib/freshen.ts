import { useEffect, useRef } from "react";
import { api } from "@/lib/api";

/**
 * On opening a page whose data comes from Facebook, asks the worker (POST `path`) to read again what it has not read
 * lately, then calls `then` when something was asked, so the page shows it pending and polls until it is read. The
 * request never calls Facebook, and the api asks nothing for what was read minutes ago or is already asked for, so
 * opening the page again (or React's double mount in development) adds nothing. A failure is silent: the page still
 * shows what was read last.
 */
export function useFreshenOnOpen(path: string, then: () => unknown) {
  const latest = useRef(then);
  useEffect(() => {
    latest.current = then;
  });
  useEffect(() => {
    api<{ asked: number }>(path, "POST").then(
      (answer) => {
        if (answer.asked > 0) latest.current();
      },
      () => undefined,
    );
  }, [path]);
}
