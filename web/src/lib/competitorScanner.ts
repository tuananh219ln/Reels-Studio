"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { usePolling } from "@/lib/polling";

/*
 * "Phân tích đối thủ": this page drives the team's Chrome extension (extension/ at the repo root, 1.1.0 or newer).
 * While it is open with the extension there, it asks the api for the member's next scan (made here or by their
 * Claude through MCP), has the extension read the competitor's Reels grid in a window of the member's own Chrome, and
 * saves each batch the extension sends. The server never opens Facebook (docs/decisions/2026-11-17-competitor-analyzer.md).
 */

export type CompetitorScan = {
  id: number;
  status: "queued" | "running" | "partial" | "done" | "failed";
  videos_found: number;
  max_videos: number;
  created_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
  competitor: { id: number; fb_url: string; kind: "page" | "profile"; name: string | null; reels_url: string };
};

const FROM_PAGE = "reels-page";
const FROM_EXTENSION = "reels-extension";
const MIN_VERSION = [1, 1, 0];
// Nothing from the extension for this long: the window or the extension stopped; the scan is saved as partial.
const SILENCE_MS = 3 * 60 * 1000;

function newEnough(version: string): boolean {
  const parts = version.split(".").map((part) => Number(part) || 0);
  for (let index = 0; index < MIN_VERSION.length; index += 1) {
    if ((parts[index] ?? 0) !== MIN_VERSION[index]) {
      return (parts[index] ?? 0) > MIN_VERSION[index];
    }
  }
  return true;
}

/** The extension's version on this page, "" until it answers. */
export function useExtensionVersion(): string {
  const [version, setVersion] = useState("");
  useEffect(() => {
    const listen = (event: MessageEvent) => {
      if (event.source === window && event.data?.source === FROM_EXTENSION && event.data.type === "ready") {
        setVersion(String(event.data.version ?? "1.0.0"));
      }
    };
    window.addEventListener("message", listen);
    window.postMessage({ source: FROM_PAGE, type: "hello" }, window.location.origin);
    return () => window.removeEventListener("message", listen);
  }, []);
  return version;
}

type GridVideo = { fb_video_id: string; views_raw: string | null; position: number };
type Ended = { status: "done" | "partial" | "failed"; error?: string | null; name?: string | null };

/** Runs one claimed scan through the extension, saving batches in order; resolves with how it ended. */
function runScan(scan: CompetitorScan, onProgress: (found: number) => void): Promise<Ended> {
  return new Promise((resolve) => {
    const request = `scan-${scan.id}`;
    let saving: Promise<unknown> = Promise.resolve();
    let silence = 0;
    const quiet = () => {
      window.clearTimeout(silence);
      silence = window.setTimeout(
        () => end({ status: "partial", error: "Tiện ích ngừng trả lời; bấm Tiếp tục để đọc tiếp" }),
        SILENCE_MS,
      );
    };
    const end = (ended: Ended) => {
      window.clearTimeout(silence);
      window.removeEventListener("message", listen);
      // The last batches are saved before the scan is closed.
      void saving.then(() => resolve(ended));
    };
    function listen(event: MessageEvent) {
      const data = event.data;
      // The extension's first answer carries the request's id; its batches, progress and end the scan's id.
      const ours = data?.scanId === scan.id || data?.id === request;
      if (event.source !== window || data?.source !== FROM_EXTENSION || !ours) {
        return;
      }
      quiet();
      if (data.type === "scan-batch" && Array.isArray(data.videos)) {
        const videos = data.videos as GridVideo[];
        saving = saving
          .then(() => api<{ videos_found: number }>(`/competitors/scans/${scan.id}/videos`, "POST", { videos }))
          .then((answer) => onProgress(answer.videos_found))
          .catch(() => undefined);
      } else if (data.type === "scan-done") {
        end({ status: data.status ?? "failed", error: data.error ?? null, name: data.name ?? null });
      } else if (data.type === "answer" && data.started === false) {
        end({ status: "failed", error: data.error ?? "Tiện ích không bắt đầu quét được" });
      }
    }
    window.addEventListener("message", listen);
    quiet();
    window.postMessage(
      {
        source: FROM_PAGE,
        type: "scan-reels",
        id: request,
        scanId: scan.id,
        url: scan.competitor.reels_url,
        maxVideos: scan.max_videos,
      },
      window.location.origin,
    );
  });
}

/**
 * While the page is open with a new enough extension: claims the member's next scan and runs it. `onChange` is
 * called whenever the list should be read again. Asks once a minute (UI Rules, "Refresh"), and at once when the
 * page queues a scan; a scan in progress is driven by the extension's messages, not by polling.
 */
export function useCompetitorScanner(onChange: () => void, wakeUp: number) {
  const version = useExtensionVersion();
  const ready = version !== "" && newEnough(version);
  const [running, setRunning] = useState<{ scan: CompetitorScan; found: number } | null>(null);
  const busy = useRef(false);
  const latest = useRef(onChange);
  useEffect(() => {
    latest.current = onChange;
  });

  async function claimAndRun() {
    if (!ready || busy.current) {
      return;
    }
    busy.current = true;
    try {
      const { scan } = await api<{ scan: CompetitorScan | null }>("/competitors/scanner/claim", "POST");
      if (!scan) {
        return;
      }
      setRunning({ scan, found: scan.videos_found });
      latest.current();
      const ended = await runScan(scan, (found) => setRunning({ scan, found }));
      await api(`/competitors/scans/${scan.id}/finish`, "POST", ended).catch(() => undefined);
    } finally {
      busy.current = false;
      setRunning(null);
      latest.current();
    }
  }

  const run = useRef(claimAndRun);
  useEffect(() => {
    run.current = claimAndRun;
  });
  usePolling(claimAndRun, 60_000);
  // At once when the extension answers, and when the page has just queued a scan (`wakeUp` changes).
  useEffect(() => {
    void run.current();
  }, [ready, wakeUp]);

  return { version, ready, running };
}
