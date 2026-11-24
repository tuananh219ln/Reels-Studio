"use client";

import { useEffect, useRef, useState } from "react";

/*
 * The team's Chrome extension "Reels Studio – Google Ảnh" (extension/ at the repo root): the page asks it for photos
 * from Google Ảnh through window.postMessage, because Google answers only a real browser (docs/decisions.md,
 * 2026-11-08). Without the extension nothing here shows.
 */

export type GooglePhoto = { url: string; width: number; height: number };
export type GoogleSearch = { results: { keyword: string; photos: GooglePhoto[] }[]; captcha?: boolean };

const FROM_PAGE = "reels-page";
const FROM_EXTENSION = "reels-extension";
// Twenty searches 1.5 s apart, each up to 20 s: well within this.
const FIND_TIMEOUT_MS = 8 * 60 * 1000;

// Remembered for the page's lifetime, so a dialog opened later knows at once.
let ready = false;

/** Whether the extension answered on this page. */
export function useGoogleExtension(): boolean {
  const [present, setPresent] = useState(ready);
  useEffect(() => {
    const listen = (event: MessageEvent) => {
      if (event.source === window && event.data?.source === FROM_EXTENSION && event.data.type === "ready") {
        ready = true;
        setPresent(true);
      }
    };
    window.addEventListener("message", listen);
    window.postMessage({ source: FROM_PAGE, type: "hello" }, window.location.origin);
    return () => window.removeEventListener("message", listen);
  }, []);
  return present;
}

/** Photos from Google Ảnh for each keyword, searched one after another in the member's own Chrome. */
export function findGooglePhotos(keywords: string[]): Promise<GoogleSearch> {
  const id = `find-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(() => {
      window.removeEventListener("message", listen);
      reject(new Error("Tiện ích Google Ảnh không trả lời, hãy tải lại trang rồi thử lại"));
    }, FIND_TIMEOUT_MS);
    function listen(event: MessageEvent) {
      const data = event.data;
      if (event.source !== window || data?.source !== FROM_EXTENSION || data.type !== "answer" || data.id !== id) {
        return;
      }
      window.clearTimeout(timer);
      window.removeEventListener("message", listen);
      resolve({ results: data.results ?? [], captcha: Boolean(data.captcha) });
    }
    window.addEventListener("message", listen);
    window.postMessage({ source: FROM_PAGE, type: "find", id, keywords }, window.location.origin);
  });
}

// A slot of a title's "Tiêu đề động" the extension sends to instead of its scene, until it expires (the member is
// off to find a photo for it) or a scene is searched for.
const CELL_TARGET_MS = 10 * 60 * 1000;
let cellTarget: { sceneId: number; index: number; until: number } | null = null;

/** The scene "Gửi ảnh vào Reels Studio" on an image's right-click menu sends to. */
export function setGoogleTarget(sceneId: number, label: string): void {
  cellTarget = null;
  window.postMessage({ source: FROM_PAGE, type: "target", target: { sceneId, label } }, window.location.origin);
}

/** The same, for one slot of the title scene `sceneId`: photos sent from now on go to that slot, for 10 minutes. */
export function setGoogleCellTarget(sceneId: number, index: number, label: string): void {
  window.postMessage({ source: FROM_PAGE, type: "target", target: { sceneId, label } }, window.location.origin);
  cellTarget = { sceneId, index, until: Date.now() + CELL_TARGET_MS };
}

/** The slot of the title scene `sceneId` that sent photos go to now, or null: they go to the scene. */
export function googleCellTarget(sceneId: number): number | null {
  if (cellTarget && cellTarget.sceneId === sceneId && cellTarget.until > Date.now()) {
    return cellTarget.index;
  }
  return null;
}

export function clearGoogleCellTarget(): void {
  cellTarget = null;
}

/**
 * A photo sent with "Gửi ảnh vào Reels Studio" to one of this page's scenes. With `forCell` it is the title's slot
 * that receives it (and `onImage` gets the slot's number); otherwise only photos not meant for a slot arrive.
 */
export function useSentImage(
  sceneId: number,
  onImage: (url: string, cell: number | null) => void,
  forCell = false,
): void {
  const latest = useRef(onImage);
  useEffect(() => {
    latest.current = onImage;
  });
  useEffect(() => {
    const listen = (event: MessageEvent) => {
      const data = event.data;
      if (event.source === window && data?.source === FROM_EXTENSION && data.type === "send-image") {
        if (data.sceneId === sceneId && typeof data.url === "string") {
          const cell = googleCellTarget(sceneId);
          if ((cell !== null) === forCell) {
            latest.current(data.url, cell);
          }
        }
      }
    };
    window.addEventListener("message", listen);
    return () => window.removeEventListener("message", listen);
  }, [sceneId, forCell]);
}
