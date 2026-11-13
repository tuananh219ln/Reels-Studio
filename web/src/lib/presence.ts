"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";

/** Another member with the same video open. */
export type PresentMember = { id: number; name: string; initial: string; editing: boolean };

// The api drops a page that has not reported for 30 s, so a report every 10 s survives two lost ones.
const REPORT_MS = 10_000;

/** A random id for this open page, so one member's two tabs are told apart (32 hex characters). */
function newTab(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

/** Tells the api this page is closing. `sendBeacon` is made for a closing page: unlike a `fetch` with
 * `keepalive`, the browser hands it to the network service at once, so it still arrives when the tab is
 * closed from outside (Playwright's `page.close()`, the tab's close button). Falls back to the fetch when
 * the beacon cannot be queued. */
function sendLeave(videoId: string, tab: string) {
  const body = new Blob([JSON.stringify({ tab })], { type: "application/json" });
  if (navigator.sendBeacon(`/api/presence/videos/${videoId}/leave`, body)) {
    return;
  }
  void fetch(`/api/presence/videos/${videoId}/leave`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tab }),
    keepalive: true,
  }).catch(() => undefined);
}

/**
 * Reports this page as open on the video ("Xem" or "Chỉnh sửa") and returns the other members who have it open.
 * `editing` is null until the video has loaded; nothing is reported before. Failures are ignored: this is
 * information only, and the next report tries again.
 */
export function usePresence(videoId: string, editing: boolean | null): PresentMember[] {
  const [others, setOthers] = useState<PresentMember[]>([]);
  const tab = useRef<string | null>(null);

  // One tab id per page and video; it leaves when the page closes or moves to another video.
  useEffect(() => {
    const id = newTab();
    tab.current = id;
    const onPageHide = () => sendLeave(videoId, id);
    window.addEventListener("pagehide", onPageHide);
    return () => {
      window.removeEventListener("pagehide", onPageHide);
      sendLeave(videoId, id);
      tab.current = null;
    };
  }, [videoId]);

  // Reports at once when the page opens or switches between "Xem" and "Chỉnh sửa", then every REPORT_MS.
  useEffect(() => {
    if (editing === null) {
      return;
    }
    let stopped = false;
    const report = async () => {
      if (!tab.current) {
        return;
      }
      try {
        const answer = await api<{ others: PresentMember[] }>(`/presence/videos/${videoId}`, "POST", {
          tab: tab.current,
          editing,
        });
        if (!stopped) {
          setOthers(answer.others);
        }
      } catch {
        // Information only; the next report tries again.
      }
    };
    void report();
    const timer = setInterval(report, REPORT_MS);
    // A background tab's timers are slowed down, so it may drop out; it reports again as soon as it is shown.
    const onVisible = () => {
      if (document.visibilityState === "visible") {
        void report();
      }
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      stopped = true;
      clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [videoId, editing]);

  return others;
}
