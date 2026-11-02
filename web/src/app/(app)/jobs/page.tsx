"use client";

import { App, Button, Card, Flex, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, errorMessage, formatDateTime, type JobRow } from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import { usePolling } from "@/lib/polling";

const REFRESH_MS = 5000;
const PAGE_SIZE = 300; // JOB_LIST_LIMIT in the api

const STATUS: Record<JobRow["status"], { label: string; color: string }> = {
  queued: { label: "Chờ", color: "processing" },
  running: { label: "Đang chạy", color: "processing" },
  done: { label: "Xong", color: "success" },
  failed: { label: "Lỗi", color: "error" },
  cancelled: { label: "Đã hủy", color: "default" },
};

function duration(seconds: number | null): string {
  if (seconds === null) {
    return "—";
  }
  // Round once, then split: 59.6 s is "1 phút 0 giây", never "60 giây".
  const total = Math.round(seconds);
  return total < 60 ? `${total} giây` : `${Math.floor(total / 60)} phút ${total % 60} giây`;
}

/** Rows from `fresh` replace the same jobs in `rows`; the result stays newest first. */
function merge(fresh: JobRow[], rows: JobRow[]): JobRow[] {
  const byId = new Map(rows.map((row) => [row.id, row]));
  for (const row of fresh) {
    byId.set(row.id, row);
  }
  return [...byId.values()].sort((a, b) => b.id - a.id);
}

export default function JobsPage() {
  const { message } = App.useApp();
  const router = useRouter();
  const [shown, setShown] = useState<JobRow[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  // Once older pages are loaded, polling merges the newest page into what is shown instead of replacing
  // it, so jobs that slide out of the newest page do not vanish between the two.
  const pagedBack = useRef(false);

  const reload = useCallback(
    async (quiet = false) => {
      try {
        const page = await api<JobRow[]>("/jobs");
        setShown((rows) => (pagedBack.current ? merge(page, rows) : page));
        setHasMore((more) => more || page.length === PAGE_SIZE);
      } catch (err) {
        if (!quiet) {
          message.error(errorMessage(err));
        }
      } finally {
        setLoading(false);
      }
    },
    [message],
  );

  async function loadOlder() {
    setLoadingMore(true);
    try {
      const page = await api<JobRow[]>(`/jobs?before=${shown[shown.length - 1].id}`);
      pagedBack.current = true;
      setShown((rows) => merge(page, rows));
      setHasMore(page.length === PAGE_SIZE);
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setLoadingMore(false);
    }
  }

  useEffect(() => {
    void reload();
  }, [reload]);
  usePolling(() => reload(true), REFRESH_MS);

  const columns: ColumnsType<JobRow> = [
    {
      title: "Video",
      key: "video",
      // A long title takes one line, in full on hover, instead of squeezing to a word per line.
      width: 240,
      render: (_, row) => (
        <Typography.Text ellipsis={{ tooltip: row.video_title }} style={{ maxWidth: 220 }}>
          {row.video_title}
        </Typography.Text>
      ),
    },
    { title: "Loại", dataIndex: "kind_label", width: 130 },
    {
      title: "Trạng thái",
      key: "status",
      width: 120,
      render: (_, row) => {
        const status = STATUS[row.status] ?? { label: row.status, color: "default" };
        return <Tag color={status.color}>{status.label}</Tag>;
      },
    },
    { title: "Người bấm", dataIndex: "created_by", width: 170 },
    {
      title: "Bắt đầu",
      key: "started",
      width: 150,
      render: (_, row) => (row.started_at ? formatDateTime(row.started_at) : "—"),
    },
    { title: "Thời lượng", key: "duration", width: 120, render: (_, row) => duration(row.duration_seconds) },
    {
      title: "Lần gọi AI",
      key: "calls",
      width: 120,
      align: "right",
      render: (_, row) => (row.kind === "image" ? row.image_calls : row.claude_calls),
    },
    {
      title: "Mô hình",
      key: "llm",
      width: 220,
      render: (_, row) => row.llm ?? <Typography.Text type="secondary">—</Typography.Text>,
    },
    {
      title: "Lỗi",
      key: "error",
      render: (_, row) =>
        row.error ? (
          <Typography.Text type="danger" ellipsis={{ tooltip: row.error }}>
            {row.error}
          </Typography.Text>
        ) : (
          ""
        ),
    },
  ];

  return (
    <>
      <PageHeader title="Nhật ký job" />
      <Card styles={{ body: { padding: 0 } }}>
        <Table<JobRow>
          rowKey="id"
          columns={columns}
          dataSource={shown}
          loading={loading}
          pagination={{ pageSize: 50, hideOnSinglePage: true }}
          scroll={{ x: 1300 }}
          locale={{ emptyText: "Chưa có job nào" }}
          onRow={(row) => ({ onClick: () => router.push(`/videos/${row.video_id}`), style: { cursor: "pointer" } })}
        />
      </Card>
      {hasMore && (
        <Flex justify="center" style={{ marginTop: 16 }}>
          <Button loading={loadingMore} onClick={loadOlder}>
            Xem job cũ hơn
          </Button>
        </Flex>
      )}
    </>
  );
}
