import { useEffect, useRef } from "react";

/**
 * Calls `poll` every `everyMs` after its previous answer (never two at once, however slow the api is),
 * and not while the tab is hidden: coming back to the tab polls at once. The first load is the caller's.
 */
export function usePolling(poll: () => Promise<unknown>, everyMs: number) {
  const latest = useRef(poll);
  useEffect(() => {
    latest.current = poll;
  });

  useEffect(() => {
    let stopped = false;
    let running = false;
    let timer: number | undefined;

    const tick = async () => {
      if (stopped || running || document.hidden) {
        // Hidden: nothing is scheduled; the visibility listener starts again.
        return;
      }
      running = true;
      try {
        await latest.current();
      } catch {
        // The page shows its own errors; polling just carries on.
      } finally {
        running = false;
      }
      if (!stopped) {
        timer = window.setTimeout(tick, everyMs);
      }
    };
    const onVisibility = () => {
      if (!document.hidden) {
        window.clearTimeout(timer);
        void tick();
      }
    };

    timer = window.setTimeout(tick, everyMs);
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      stopped = true;
      window.clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [everyMs]);
}
