"use client";

import EmptyState from "@/components/EmptyState";
import VideoTitleCell from "@/components/VideoTitleCell";
import { formatNumber } from "@/components/page/Figures";
import { api, errorMessage, formatDateTime, type PageCompare as Compare } from "@/lib/api";
import { usePolling } from "@/lib/polling";
import { App, Card, Table, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useCallback, useEffect, useState } from "react";

const REFRESH_MS = 60_000;
type Row = Compare["videos"][number];
type Side = NonNullable<Row["facebook"]>;

function Cell({ side, pick }: { side: Side | null; pick: (side: Side) => number | null }) {
  if (side === null) return <Typography.Text type="secondary">Chưa đăng</Typography.Text>;
  return <>{formatNumber(pick(side))}</>;
}

/** "So sánh": the same video on Facebook and Instagram side by side, so a member sees which platform a video suits.
 * Each platform's numbers are its own: Facebook counts plays, Instagram counts views, and neither is the other's. */
export default function PageCompare({ pageId, days }: { pageId: number; days: number }) {
  const { message } = App.useApp();
  const [data, setData] = useState<Compare | null>(null);

  const load = useCallback(
    async (quiet = false) => {
      try {
        setData(await api<Compare>(`/fanpages/${pageId}/compare?days=${days}`));
      } catch (err) {
        if (!quiet) message.error(errorMessage(err));
      }
    },
    [pageId, days, message],
  );
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- loads on mount and on a new period; state is set only after the request answers
    void load();
  }, [load]);
  usePolling(() => load(true), REFRESH_MS);

  const group = (title: string, key: "facebook" | "instagram") => ({
    title,
    children: [
      {
        title: "Lượt xem",
        key: `${key}-views`,
        align: "right" as const,
        render: (_: unknown, row: Row) => <Cell side={row[key]} pick={(side) => side.views} />,
      },
      {
        title: "Tiếp cận",
        key: `${key}-reach`,
        align: "right" as const,
        render: (_: unknown, row: Row) => <Cell side={row[key]} pick={(side) => side.reach} />,
      },
      {
        title: "Tương tác",
        key: `${key}-interactions`,
        align: "right" as const,
        render: (_: unknown, row: Row) => <Cell side={row[key]} pick={(side) => side.interactions} />,
      },
    ],
  });
  const columns: ColumnsType<Row> = [
    {
      title: "Video",
      key: "video",
      width: 300,
      render: (_, row) => (
        <VideoTitleCell
          id={row.video.id}
          title={row.video.title}
          thumbnailUrl={row.video.thumbnail_url}
          sub={formatDateTime((row.facebook ?? row.instagram)!.live_at)}
        />
      ),
    },
    group("Facebook", "facebook"),
    group("Instagram", "instagram"),
  ];
  return (
    <Card size="small" styles={{ body: { padding: 0 } }} data-testid="page-compare">
      <Table<Row>
        rowKey={(row) => row.video.id}
        size="middle"
        loading={data === null}
        dataSource={data?.videos ?? []}
        columns={columns}
        pagination={false}
        scroll={{ x: 900 }}
        locale={{ emptyText: <EmptyState description={`Chưa có video nào app đăng lên Page trong ${days} ngày`} /> }}
      />
      <Typography.Text type="secondary" style={{ display: "block", padding: "8px 16px", fontSize: 12 }}>
        Lượt xem của Facebook tính mọi lượt phát, của Instagram tính lượt xem Reel; tương tác là thích, bình luận và
        chia sẻ (Instagram thêm lưu). Hai nền tảng tính khác nhau nên so tương đối, không so từng con số.
      </Typography.Text>
    </Card>
  );
}
