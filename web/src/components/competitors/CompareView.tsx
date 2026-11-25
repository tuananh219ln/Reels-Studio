"use client";

import { Modal, Table, Typography } from "antd";
import { useEffect, useState } from "react";
import { api, errorMessage, formatDayTime } from "@/lib/api";
import { formatCompact, formatFull } from "@/lib/competitorFormat";

/** One competitor in "So sánh" (api competitors.compare), by its latest scan that read anything. */
type Compared = {
  competitor: { id: number; display_name: string };
  scan: {
    videos: number;
    by_type: { reel: number; video: number };
    total_views: number;
    median_views: number | null;
    max_views: number | null;
    top10_share: number | null;
    videos_per_week: number | null;
    newest_posted_at: string | null;
  } | null;
};

/** "So sánh": the ticked competitors side by side, named as everywhere else (their own name first). */
export default function CompareView({ ids, onClose }: { ids: number[]; onClose: () => void }) {
  const [rows, setRows] = useState<Compared[] | null>(null);
  const [failed, setFailed] = useState("");
  useEffect(() => {
    api<{ competitors: Compared[] }>(`/competitors/compare?ids=${ids.join(",")}`)
      .then((data) => setRows(data.competitors))
      .catch((err) => setFailed(errorMessage(err)));
  }, [ids]);
  const value = (row: Compared, read: (scan: NonNullable<Compared["scan"]>) => string) =>
    row.scan ? read(row.scan) : "Chưa quét xong";
  return (
    <Modal open title="So sánh đối thủ" footer={null} onCancel={onClose} width={960}>
      {failed && <Typography.Text type="danger">{failed}</Typography.Text>}
      <Table<Compared>
        size="small"
        rowKey={(row) => row.competitor.id}
        loading={rows === null && !failed}
        dataSource={rows ?? []}
        pagination={false}
        scroll={{ x: 820 }}
        columns={[
          { title: "Kênh", key: "name", render: (_, row) => row.competitor.display_name },
          {
            title: "Video (Reels, Video)",
            key: "videos",
            render: (_, row) =>
              value(row, (scan) => `${formatFull(scan.videos)} (${scan.by_type.reel}, ${scan.by_type.video})`),
          },
          {
            title: "Tổng view",
            key: "total",
            render: (_, row) => value(row, (scan) => formatCompact(scan.total_views)),
          },
          {
            title: "Trung vị",
            key: "median",
            render: (_, row) => value(row, (scan) => formatCompact(scan.median_views)),
          },
          { title: "Cao nhất", key: "max", render: (_, row) => value(row, (scan) => formatCompact(scan.max_views)) },
          {
            title: "Top 10 chiếm",
            key: "top10",
            render: (_, row) =>
              value(row, (scan) =>
                scan.top10_share === null ? "—" : `${Math.round(scan.top10_share * 1000) / 10}%`.replace(".", ","),
              ),
          },
          {
            title: "Video/tuần",
            key: "frequency",
            render: (_, row) =>
              value(row, (scan) =>
                scan.videos_per_week === null ? "—" : String(scan.videos_per_week).replace(".", ","),
              ),
          },
          {
            title: "Đăng gần nhất",
            key: "newest",
            render: (_, row) =>
              value(row, (scan) => (scan.newest_posted_at ? formatDayTime(scan.newest_posted_at) : "—")),
          },
        ]}
      />
      <Typography.Text type="secondary">
        Số liệu tính bằng code từ lượt quét gần nhất của từng đối thủ. Nhờ Claude (competitor_compare) để rút ra khác
        biệt về chủ đề và cách làm.
      </Typography.Text>
    </Modal>
  );
}
