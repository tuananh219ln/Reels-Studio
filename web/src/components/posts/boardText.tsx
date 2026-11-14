"use client";

import type { StatusTone } from "@/components/StatusText";
import type { BoardPlatform, PostSource, PostState } from "@/lib/api";
import { Tag } from "antd";

export const PLATFORM_LABEL: Record<BoardPlatform, string> = {
  facebook: "Facebook",
  tiktok: "TikTok",
  youtube: "YouTube Shorts",
};

/** The dot's colour: green out, orange waiting, red failed or gone, grey cancelled. */
export const STATE_TONE: Record<PostState, StatusTone> = {
  published: "success",
  scheduled: "waiting",
  pending_link: "waiting",
  publishing: "active",
  failed: "danger",
  removed: "danger",
  cancelled: "idle",
};

export const STATE_LABEL: Record<PostState, string> = {
  published: "Đã đăng",
  scheduled: "Hẹn lịch",
  pending_link: "Chờ dán link",
  publishing: "Đang đăng…",
  failed: "Thất bại",
  removed: "Đã gỡ",
  cancelled: "Đã hủy",
};

const SOURCES: Record<PostSource, { label: string; color: string }> = {
  app_api: { label: "API", color: "blue" },
  meta_suite: { label: "Meta Suite", color: "cyan" },
  manual_link: { label: "Link tay", color: "purple" },
};

/** The small label saying where a post's numbers come from. */
export function SourceChip({ source }: { source: PostSource }) {
  const { label, color } = SOURCES[source];
  return (
    <Tag color={color} style={{ marginInlineEnd: 0, fontSize: 11, lineHeight: "16px", paddingInline: 4 }}>
      {label}
    </Tag>
  );
}

const dayMonth = new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Ho_Chi_Minh", day: "2-digit", month: "2-digit" });

/** "dd/MM" in Vietnam time. */
export function formatDayMonth(iso: string): string {
  return dayMonth.format(new Date(iso));
}

/** "3h trước", "quá 24h" past a day. */
export function hoursAgo(iso: string, now = Date.now()): string {
  const hours = Math.max(0, Math.floor((now - new Date(iso).getTime()) / 3_600_000));
  return hours >= 24 ? "quá 24h" : `${hours}h trước`;
}
