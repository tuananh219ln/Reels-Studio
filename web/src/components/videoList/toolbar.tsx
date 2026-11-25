"use client";

import { AppstoreOutlined, SearchOutlined, TableOutlined } from "@ant-design/icons";
import { Input, Segmented } from "antd";
import { useState } from "react";

export type VideoView = "cards" | "table";
// One choice for every list of videos, remembered in this browser.
const VIEW_KEY = "reels-studio.video-view";

/** "Thẻ | Bảng" of a list of videos, remembered in this browser under one key for every list. `fallback` is what a
 * list shows until the member chooses (a page of its own opens on cards, a group's tab on the table). `legacy`: where
 * this list kept the choice before, so nobody loses it. */
export function useVideoView(
  fallback: VideoView,
  legacy?: { key: string; values: Record<string, VideoView> },
): [VideoView, (next: VideoView) => void] {
  const [view, setView] = useState<VideoView>(() => {
    try {
      const saved = window.localStorage.getItem(VIEW_KEY);
      if (saved === "cards" || saved === "table") return saved;
      const old = legacy ? window.localStorage.getItem(legacy.key) : null;
      return (old && legacy?.values[old]) || fallback;
    } catch {
      return fallback;
    }
  });
  return [
    view,
    (next) => {
      setView(next);
      try {
        window.localStorage.setItem(VIEW_KEY, next);
      } catch {
        // A browser that refuses storage just forgets the choice.
      }
    },
  ];
}

export function ViewToggle({ value, onChange }: { value: VideoView; onChange: (next: VideoView) => void }) {
  return (
    <Segmented<VideoView>
      aria-label="Kiểu hiển thị"
      value={value}
      onChange={onChange}
      options={[
        { value: "cards", label: "Thẻ", icon: <AppstoreOutlined /> },
        { value: "table", label: "Bảng", icon: <TableOutlined /> },
      ]}
    />
  );
}

/** The search box of every list of videos: the same words and place. `label` says what it searches, for screen readers. */
export function VideoSearch({
  value,
  onChange,
  label = "Tìm theo tiêu đề hoặc chủ đề",
  width = 240,
}: {
  value: string;
  onChange: (next: string) => void;
  label?: string;
  width?: number;
}) {
  return (
    <Input
      aria-label={label}
      prefix={<SearchOutlined />}
      placeholder="Tìm theo tiêu đề hoặc chủ đề…"
      allowClear
      value={value}
      onChange={(event) => onChange(event.target.value)}
      style={{ width, maxWidth: "100%" }}
    />
  );
}
