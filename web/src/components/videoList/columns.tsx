"use client";

import ColumnPicker, { useRememberedColumns, type PickableColumn } from "@/components/ColumnPicker";
import type { VideoRow } from "@/lib/api";
import { Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import type { ReactNode } from "react";
import { PLATFORM_LABELS } from "@/lib/postResults";
import { VideoMadeCell, VideoNumbersCell, VideoStatusCell } from "./cells";
import { count, percent, shortDate } from "./format";

type Key =
  | "id"
  | "status"
  | "numbers"
  | "made"
  | "platform"
  | "group"
  | "content_type"
  | "products"
  | "page"
  | "schedule"
  | "views_48h"
  | "share_rate";

const DETAILS = "Chi tiết về video";
const POSTING = "Đăng";
const RESULTS = "Hiệu quả";

const SPECS: (PickableColumn<Key> & { initial: boolean })[] = [
  { key: "id", title: "ID", group: DETAILS, initial: false },
  { key: "status", title: "Trạng thái", group: DETAILS, initial: true },
  { key: "numbers", title: "Số liệu", group: RESULTS, initial: true },
  { key: "made", title: "Tạo", group: DETAILS, initial: true },
  { key: "platform", title: "Nền tảng", group: DETAILS, initial: false },
  { key: "group", title: "Nhóm chủ đề", group: DETAILS, initial: false },
  { key: "content_type", title: "Loại nội dung", group: DETAILS, initial: false },
  { key: "products", title: "Sản phẩm", group: DETAILS, initial: false },
  { key: "page", title: "Page", group: POSTING, initial: false },
  { key: "schedule", title: "Lịch đăng", group: POSTING, initial: false },
  { key: "views_48h", title: "View 48h", group: RESULTS, initial: false },
  { key: "share_rate", title: "Share/view", group: RESULTS, initial: false },
];

const dash = <Typography.Text type="secondary">—</Typography.Text>;

/** One line of text, cut with "…" at `width` (in pixels, so it never stretches its column). */
function line(text: string, width: number) {
  return (
    <Typography.Text ellipsis={{ tooltip: text }} style={{ maxWidth: width }}>
      {text}
    </Typography.Text>
  );
}

/** "Lịch đăng": when it went out or is set to go, else the Page queue it waits in, else the time suggested. */
function schedule(row: VideoRow): { text: string; at: string | null } | null {
  if (row.post) {
    return { text: `${row.post.state === "scheduled" ? "Hẹn" : "Đã đăng"} ${shortDate(row.post.at)}`, at: row.post.at };
  }
  if (row.queue) return { text: "Trong hàng chờ", at: null };
  if (row.suggested_post_at) return { text: `Gợi ý ${shortDate(row.suggested_post_at)}`, at: row.suggested_post_at };
  return null;
}

/** For a sorter: a missing number or time goes last whichever way. */
const timeOf = (at: string | null | undefined) => (at ? Date.parse(at) : -1);

/** The columns every table of videos shares after the title, in the order the member left them in "Cột", remembered
 * under `storageKey`: Trạng thái, Số liệu and Tạo at first, and more to tick (ID, Nền tảng, Nhóm chủ đề, Loại nội
 * dung, Sản phẩm, Page, Lịch đăng, View 48h, Share/view). Every column has a width, so on a wide screen the spare
 * width goes to the table's empty last column (fillColumn) and the columns stay side by side. Returns the antd
 * columns and the "Cột" button for the page's toolbar. */
export function useVideoColumns({
  storageKey,
  versionsOf,
  onChanged,
  showGroup = false,
}: {
  storageKey: string;
  /** The TikTok versions shown on the row of their source video, when the list folds them in. */
  versionsOf?: (row: VideoRow) => VideoRow[];
  onChanged?: () => void;
  /** The group and plan day under the maker: for a list across groups. */
  showGroup?: boolean;
}): { columns: ColumnsType<VideoRow>; picker: ReactNode } {
  const known = SPECS.map((spec) => spec.key);
  const [shown, setShown] = useRememberedColumns<Key>(
    storageKey,
    known,
    SPECS.filter((spec) => spec.initial).map((spec) => spec.key),
  );
  const column = (key: Key): ColumnsType<VideoRow>[number] => {
    switch (key) {
      case "id":
        return {
          key,
          title: "ID",
          width: 64,
          render: (_, row) => <Typography.Text type="secondary">{row.id}</Typography.Text>,
        };
      case "status":
        return {
          key,
          title: "Trạng thái",
          width: 260,
          render: (_, row) => <VideoStatusCell row={row} versions={versionsOf?.(row)} onChanged={onChanged} />,
        };
      case "numbers":
        return {
          key,
          title: "Số liệu",
          width: 190,
          sorter: (a, b) => (a.post?.views ?? -1) - (b.post?.views ?? -1),
          render: (_, row) => <VideoNumbersCell post={row.post} />,
        };
      case "made":
        return {
          key,
          title: "Tạo",
          width: 220,
          render: (_, row) => <VideoMadeCell row={row} group={showGroup} />,
        };
      case "platform":
        return {
          key,
          title: "Nền tảng",
          width: 110,
          render: (_, row) => PLATFORM_LABELS[row.platform],
        };
      case "group":
        return {
          key,
          title: "Nhóm chủ đề",
          width: 200,
          render: (_, row) =>
            row.knowledge_topic
              ? line(
                  [row.knowledge_topic, row.plan_day ? `ngày ${row.plan_day}` : null].filter(Boolean).join(", "),
                  180,
                )
              : dash,
        };
      case "content_type":
        return {
          key,
          title: "Loại nội dung",
          width: 160,
          render: (_, row) => (row.content_type ? line(row.content_type, 140) : dash),
        };
      case "products":
        return {
          key,
          title: "Sản phẩm",
          width: 100,
          align: "right",
          sorter: (a, b) => (a.product_count ?? 0) - (b.product_count ?? 0),
          render: (_, row) => (row.product_count ? count(row.product_count) : dash),
        };
      case "page":
        return {
          key,
          title: "Page",
          width: 200,
          render: (_, row) =>
            row.post
              ? line(row.post.fanpages.join(", ") || row.post.fanpage, 180)
              : row.queue
                ? line(`${row.queue.fanpage} (hàng chờ)`, 180)
                : dash,
        };
      case "schedule":
        return {
          key,
          title: "Lịch đăng",
          width: 170,
          sorter: (a, b) => timeOf(schedule(a)?.at) - timeOf(schedule(b)?.at),
          render: (_, row) => {
            const when = schedule(row);
            return when ? <span style={{ whiteSpace: "nowrap" }}>{when.text}</span> : dash;
          },
        };
      case "views_48h":
        return {
          key,
          title: "View 48h",
          width: 110,
          align: "right",
          sorter: (a, b) => (a.post?.views_48h ?? -1) - (b.post?.views_48h ?? -1),
          render: (_, row) => (row.post?.views_48h != null ? count(row.post.views_48h) : dash),
        };
      case "share_rate":
        return {
          key,
          title: "Share/view",
          width: 110,
          align: "right",
          sorter: (a, b) => (a.post?.share_rate ?? -1) - (b.post?.share_rate ?? -1),
          render: (_, row) => (row.post?.share_rate != null ? percent(row.post.share_rate) : dash),
        };
    }
  };
  return {
    columns: shown.map(column),
    picker: <ColumnPicker<Key> columns={SPECS} shown={shown} onApply={setShown} />,
  };
}
