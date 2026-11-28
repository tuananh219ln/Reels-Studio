"use client";

import { useEffect, useState } from "react";

/*
 * "Chuyển bằng tiện ích Chrome" (docs/decisions/2026-11-28-shopee-auto-link.md): the team's Chrome extension turns
 * product pages into the member's own affiliate links with Shopee Affiliate's Custom Link, in the member's logged-in
 * affiliate.shopee.vn tab. Without a version of the extension that says it can, nothing here shows.
 */

const FROM_PAGE = "reels-page";
const FROM_EXTENSION = "reels-extension";
// 500 links at 20 a request, 1.5 s apart, is about 40 s; the tab may also have to load first.
const CONVERT_TIMEOUT_MS = 3 * 60 * 1000;

export type ConvertedLink = { original: string; short: string; failCode?: number };
export type ConvertAnswer = {
  rows?: ConvertedLink[];
  /** `login`: no signed-in Shopee Affiliate tab; `refused`: Shopee did not answer as expected (see `detail`). */
  error?: "login" | "refused";
  detail?: { status?: number; csrf?: boolean; body?: string };
};

let supported = false;

/** Whether the extension on this page can convert Shopee links (a version from 1.8.0 says so). */
export function useShopeeConvert(): boolean {
  const [can, setCan] = useState(supported);
  useEffect(() => {
    const listen = (event: MessageEvent) => {
      const data = event.data;
      if (event.source === window && data?.source === FROM_EXTENSION && data.type === "ready") {
        supported = Array.isArray(data.features) && data.features.includes("shopee-convert");
        setCan(supported);
      }
    };
    window.addEventListener("message", listen);
    window.postMessage({ source: FROM_PAGE, type: "hello" }, window.location.origin);
    return () => window.removeEventListener("message", listen);
  }, []);
  return can;
}

/** The affiliate link of each product page, made in the member's own Chrome with `subId1` as Sub_id1. */
export function convertShopeeLinks(links: string[], subId1: string): Promise<ConvertAnswer> {
  const id = `shopee-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(() => {
      window.removeEventListener("message", listen);
      reject(new Error("Tiện ích Chrome không trả lời, hãy tải lại trang rồi thử lại"));
    }, CONVERT_TIMEOUT_MS);
    function listen(event: MessageEvent) {
      const data = event.data;
      if (event.source !== window || data?.source !== FROM_EXTENSION || data.type !== "answer" || data.id !== id) {
        return;
      }
      window.clearTimeout(timer);
      window.removeEventListener("message", listen);
      resolve({ rows: data.rows, error: data.error, detail: data.detail });
    }
    window.addEventListener("message", listen);
    window.postMessage({ source: FROM_PAGE, type: "shopee-convert", id, links, subId1 }, window.location.origin);
  });
}

/** The rows as the CSV Shopee's Custom Link gives back, so the import reads them like a file. */
export function convertedFile(rows: ConvertedLink[]): File {
  const cell = (value: string) => `"${value.replaceAll('"', '""')}"`;
  const lines = rows.map((row) =>
    [
      cell(row.original),
      cell(row.short),
      cell(row.short ? "" : `Shopee từ chối link này (mã ${row.failCode ?? "?"})`),
    ].join(","),
  );
  const text = ["Liên kết gốc,Liên kết chuyển đổi,Lí do thất bại", ...lines].join("\r\n");
  return new File(["﻿" + text], "tien-ich-chrome.csv", { type: "text/csv" });
}
