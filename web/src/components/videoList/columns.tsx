"use client";

import ColumnPicker, { useRememberedColumns, type PickableColumn } from "@/components/ColumnPicker";
import type { VideoRow } from "@/lib/api";
import { Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import type { ReactNode } from "react";
import { VideoMadeCell, VideoNumbersCell, VideoStatusCell } from "./cells";

type Key = "id" | "status" | "numbers" | "made";

const SPECS: (PickableColumn<Key> & { initial: boolean })[] = [
  { key: "id", title: "ID", group: "Chi tiết về video", initial: false },
  { key: "status", title: "Trạng thái", group: "Chi tiết về video", initial: true },
  { key: "numbers", title: "Số liệu", group: "Hiệu quả", initial: true },
  { key: "made", title: "Tạo", group: "Chi tiết về video", initial: true },
];

/** The columns every table of videos shares after the title: ID (off until ticked), Trạng thái, Số liệu and Tạo, in
 * the order the member left them in "Cột", remembered under `storageKey`. Returns the antd columns and the "Cột"
 * button for the page's toolbar. */
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
    }
  };
  return {
    columns: shown.map(column),
    picker: <ColumnPicker<Key> columns={SPECS} shown={shown} onApply={setShown} />,
  };
}
