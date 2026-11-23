"use client";

import EmptyState from "@/components/EmptyState";
import VideoTitleCell from "@/components/VideoTitleCell";
import { formatNumber, formatSeconds } from "@/components/page/Figures";
import { api, errorMessage, formatDateTime, type InstagramContent as Content } from "@/lib/api";
import { usePolling } from "@/lib/polling";
import { App, Card, Table, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useCallback, useEffect, useState } from "react";

const REFRESH_MS = 60_000;
type Row = Content["posts"][number];

/** The Instagram "Nội dung": the Reels the app posted to the Page's Instagram in the period, with the latest reading of
 * each (views, reach, likes, comments, shares, saves, watch time), the way Facebook's content library lists its reels. A
 * Reel posted outside the app is not known. */
export default function InstagramContent({ pageId, days }: { pageId: number; days: number }) {
  const { message } = App.useApp();
  const [data, setData] = useState<Content | null>(null);

  const load = useCallback(
    async (quiet = false) => {
      try {
        setData(await api<Content>(`/fanpages/${pageId}/instagram-content?days=${days}`));
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

  const number = (pick: (row: Row) => number | null | undefined) => (_: unknown, row: Row) =>
    row.numbers ? formatNumber(pick(row) ?? null) : "—";
  const columns: ColumnsType<Row> = [
    {
      title: "Reel",
      key: "video",
      width: 320,
      render: (_, row) => (
        <VideoTitleCell
          id={row.video.id}
          title={row.video.title}
          thumbnailUrl={row.video.thumbnail_url}
          sub={row.error ?? (row.numbers ? `Đo lúc ${formatDateTime(row.numbers.measured_at)}` : "Chưa đo")}
        />
      ),
    },
    { title: "Đăng lúc", key: "live", width: 130, render: (_, row) => formatDateTime(row.live_at) },
    { title: "Lượt xem", key: "views", align: "right", render: number((row) => row.numbers?.views) },
    { title: "Tiếp cận", key: "reach", align: "right", render: number((row) => row.numbers?.reach) },
    { title: "Thích", key: "likes", align: "right", render: number((row) => row.numbers?.likes) },
    { title: "Bình luận", key: "comments", align: "right", render: number((row) => row.numbers?.comments) },
    { title: "Chia sẻ", key: "shares", align: "right", render: number((row) => row.numbers?.shares) },
    { title: "Lưu", key: "saves", align: "right", render: number((row) => row.numbers?.saves) },
    {
      title: "Xem TB",
      key: "watch",
      align: "right",
      render: (_, row) => formatSeconds(row.numbers?.avg_watch_seconds ?? null),
    },
    {
      title: "",
      key: "open",
      width: 110,
      render: (_, row) =>
        row.url ? (
          <a href={row.url} target="_blank" rel="noreferrer">
            Mở bài ↗
          </a>
        ) : null,
    },
  ];
  return (
    <Card size="small" styles={{ body: { padding: 0 } }} data-testid="instagram-content">
      <Table<Row>
        rowKey="id"
        size="middle"
        loading={data === null}
        dataSource={data?.posts ?? []}
        columns={columns}
        pagination={false}
        scroll={{ x: 1000 }}
        locale={{
          emptyText: <EmptyState description={`Chưa có Reel nào app đăng lên Instagram trong ${days} ngày`} />,
        }}
      />
      <Typography.Text type="secondary" style={{ display: "block", padding: "8px 16px", fontSize: 12 }}>
        Số do Instagram tính, đo theo lịch như Facebook (mỗi giờ trong 48 giờ đầu rồi thưa dần). Reel đăng ngoài app
        không được tính.
      </Typography.Text>
    </Card>
  );
}
