"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { usePolling } from "@/lib/polling";

/*
 * "Phân tích đối thủ": this page drives the team's Chrome extension (extension/ at the repo root, 1.5.0 or newer).
 * While it is open with the extension there and a second Facebook account saved in it, it asks the api for the
 * member's next scan (made here or by their Claude through MCP), has the extension read the competitor's Reels grid
 * in an incognito window signed in as that account, saves each batch, then sends back the most viewed reels for the
 * extension to open one by one (caption, sound, reactions). The server never opens Facebook and never sees the
 * account's cookies (docs/decisions/2026-11-17-competitor-analyzer.md).
 */

export type CompetitorScan = {
  id: number;
  status: "queued" | "running" | "partial" | "done" | "failed";
  videos_found: number;
  max_videos: number;
  fetch_captions_top_n: number;
  created_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
  include_videos: boolean;
  /** "Cập nhật thông tin kênh": reads only the Page's header, no videos. */
  meta_only: boolean;
  competitor: {
    id: number;
    fb_url: string;
    kind: "page" | "profile";
    name: string | null;
    reels_url: string;
    videos_url: string;
  };
};

/** The second account saved in the extension (its Facebook id), and whether it may open incognito windows. */
export type ScanAccount = { userId: string | null; incognito: boolean };

/** Where a running scan is: reading the grid (videos found) or opening the top reels (read of total). */
export type ScanProgress = { scan: CompetitorScan; found: number; details?: { read: number; of: number } };

const FROM_PAGE = "reels-page";
const FROM_EXTENSION = "reels-extension";
// 1.5.0 reads the Page's header (name, followers, badge, avatar) and runs header-only scans.
const MIN_VERSION = [1, 5, 0];
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

function fromExtension(event: MessageEvent): boolean {
  return event.source === window && event.data?.source === FROM_EXTENSION;
}

/** The extension's version on this page, "" until it answers. */
export function useExtensionVersion(): string {
  const [version, setVersion] = useState("");
  useEffect(() => {
    const listen = (event: MessageEvent) => {
      if (fromExtension(event) && event.data.type === "ready") {
        setVersion(String(event.data.version ?? "1.0.0"));
      }
    };
    window.addEventListener("message", listen);
    window.postMessage({ source: FROM_PAGE, type: "hello" }, window.location.origin);
    return () => window.removeEventListener("message", listen);
  }, []);
  return version;
}

/*
 * A copy of the second account's cookies in this Chrome's storage for this site, never sent to the api: removing the
 * extension deletes its own storage, and an extension installed again takes the copy back when this page asks
 * (extension/scan-account.js syncScanAccount). Storage that cannot be read or written (a private window, blocked site
 * data) only means no copy.
 */
const COPY_KEY = "reels-studio-scan-account";

type AccountCopy = { cookies: { name: string; value: string }[]; userId: string; savedAt: string };

function readCopy(): AccountCopy | null {
  try {
    const copy = JSON.parse(window.localStorage.getItem(COPY_KEY) ?? "null");
    return copy && Array.isArray(copy.cookies) && typeof copy.savedAt === "string" ? copy : null;
  } catch {
    return null;
  }
}

function writeCopy(copy: AccountCopy | null): void {
  try {
    if (copy) {
      window.localStorage.setItem(COPY_KEY, JSON.stringify(copy));
    } else {
      window.localStorage.removeItem(COPY_KEY);
    }
  } catch {
    // No copy kept; the cookies stay in the extension.
  }
}

/** Asks the extension whose cookies it holds; read again when the member comes back from its options page. */
function useScanAccount(enabled: boolean): ScanAccount | null {
  const [account, setAccount] = useState<ScanAccount | null>(null);
  useEffect(() => {
    if (!enabled) {
      return;
    }
    const id = `scan-account-${Math.random().toString(36).slice(2, 8)}`;
    const listen = (event: MessageEvent) => {
      if (fromExtension(event) && event.data.type === "answer" && event.data.id === id) {
        setAccount({ userId: event.data.userId ?? null, incognito: Boolean(event.data.incognito) });
        // The extension hands its newer cookies over for the copy, or says the copy is to go ("Xóa").
        if (event.data.backup) {
          writeCopy(event.data.backup);
        } else if (event.data.forget) {
          writeCopy(null);
        }
      }
    };
    const ask = () =>
      window.postMessage({ source: FROM_PAGE, type: "scan-account", id, backup: readCopy() }, window.location.origin);
    const onVisible = () => {
      if (!document.hidden) ask();
    };
    window.addEventListener("message", listen);
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("focus", ask);
    ask();
    return () => {
      window.removeEventListener("message", listen);
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("focus", ask);
    };
  }, [enabled]);
  return account;
}

/** "Cài đặt tài khoản phụ": the extension's options page, where the cookies are pasted. */
export function openExtensionOptions(): void {
  window.postMessage({ source: FROM_PAGE, type: "open-options" }, window.location.origin);
}

/** A video the extension opens on its own page (api competitors.enrich_targets). */
type EnrichTarget = { fb_video_id: string; url: string; comments: boolean };

type GridVideo = { fb_video_id: string; views_raw: string | null; position: number; type?: "reel" | "video" };
type Ended = {
  status: "done" | "partial" | "failed";
  error?: string | null;
  name?: string | null;
  /** What the Page's header gave, saved with the end of the scan (api competitors.finish). */
  followers?: string | null;
  is_verified?: boolean | null;
  avatar?: string | null;
};

/** Runs one claimed scan through the extension, saving everything in order; resolves with how it ended. */
function runScan(scan: CompetitorScan, onProgress: (progress: ScanProgress) => void): Promise<Ended> {
  return new Promise((resolve) => {
    const request = `scan-${scan.id}`;
    let saving: Promise<unknown> = Promise.resolve();
    let found = scan.videos_found;
    let name: string | null = null;
    let silence = 0;
    const save = (step: () => Promise<unknown>) => {
      saving = saving.then(step).catch(() => undefined);
    };
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
      // What the extension sent last is saved before the scan is closed.
      void saving.then(() => resolve({ ...ended, name: ended.name ?? name }));
    };
    function listen(event: MessageEvent) {
      const data = event.data;
      // The extension's first answer carries the request's id; everything after it, the scan's id.
      if (!fromExtension(event) || !(data?.scanId === scan.id || data?.id === request)) {
        return;
      }
      quiet();
      if (data.type === "scan-batch" && Array.isArray(data.videos)) {
        const videos = data.videos as GridVideo[];
        save(async () => {
          const answer = await api<{ videos_found: number }>(`/competitors/scans/${scan.id}/videos`, "POST", {
            videos,
          });
          found = answer.videos_found;
          onProgress({ scan, found });
        });
      } else if (data.type === "scan-grid-done") {
        name = data.name ?? null;
        // Once the grid is saved, the api names the most viewed reels; the extension opens them one by one.
        save(async () => {
          // Not answered: no reels are opened and the extension closes the scan with the grid saved.
          // The first of them (comment_ids) also have a sample of their comments read.
          // Then a few videos spread down each grid, only for their posting date (M5). Each has its own address.
          const empty = { targets: [] as EnrichTarget[], fb_video_ids: [] as string[], comment_ids: [] as string[] };
          const targets = await api<typeof empty>(`/competitors/scans/${scan.id}/enrich-targets`, "POST").catch(
            () => empty,
          );
          onProgress({ scan, found, details: { read: 0, of: targets.targets.length } });
          window.postMessage(
            {
              source: FROM_PAGE,
              type: "scan-details",
              scanId: scan.id,
              targets: targets.targets,
              ids: targets.fb_video_ids,
              commentIds: targets.comment_ids,
            },
            window.location.origin,
          );
        });
      } else if (data.type === "scan-detail" && data.video) {
        const video = data.video;
        save(() => api(`/competitors/scans/${scan.id}/details`, "POST", { videos: [video] }));
      } else if (data.type === "scan-tick" && typeof data.of === "number") {
        onProgress({ scan, found, details: { read: data.read, of: data.of } });
      } else if (data.type === "scan-done") {
        end({
          status: data.status ?? "failed",
          error: data.error ?? null,
          name: data.name ?? null,
          followers: data.followers ?? null,
          is_verified: typeof data.is_verified === "boolean" ? data.is_verified : null,
          avatar: typeof data.avatar === "string" ? data.avatar : null,
        });
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
        // M5: the Videos tab after Reels, when the scan asks for it.
        videosUrl: scan.include_videos ? scan.competitor.videos_url : undefined,
        maxVideos: scan.max_videos,
        metaOnly: scan.meta_only,
      },
      window.location.origin,
    );
  });
}

/**
 * While the page is open with a new enough extension holding a second account: claims the member's next scan and
 * runs it, then the next one at once. `onChange` is called whenever the list should be read again. Asks once a minute
 * (UI Rules, "Refresh"), and at once when the page queues a scan; a scan in progress is driven by the extension's
 * messages, not by polling.
 */
export function useCompetitorScanner(onChange: () => void, wakeUp: number) {
  const version = useExtensionVersion();
  const current = version !== "" && newEnough(version);
  const account = useScanAccount(current);
  const ready = current && Boolean(account?.userId) && Boolean(account?.incognito);
  const [running, setRunning] = useState<ScanProgress | null>(null);
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
    let ran = false;
    try {
      const { scan } = await api<{ scan: CompetitorScan | null }>("/competitors/scanner/claim", "POST");
      if (!scan) {
        return;
      }
      ran = true;
      setRunning({ scan, found: scan.videos_found });
      latest.current();
      const ended = await runScan(scan, setRunning);
      await api(`/competitors/scans/${scan.id}/finish`, "POST", ended).catch(() => undefined);
    } finally {
      busy.current = false;
      setRunning(null);
      latest.current();
    }
    // The next waiting scan starts at once, not at the next minute's poll (several "Cập nhật thông tin kênh" in a
    // row took a minute each). The loop ends when the api has nothing left to claim.
    if (ran) {
      void run.current();
    }
  }

  const run = useRef(claimAndRun);
  useEffect(() => {
    run.current = claimAndRun;
  });
  usePolling(claimAndRun, 60_000);
  // At once when the extension and its account are ready, and when the page has just queued a scan.
  useEffect(() => {
    void run.current();
  }, [ready, wakeUp]);

  return { version, current, account, ready, running };
}
