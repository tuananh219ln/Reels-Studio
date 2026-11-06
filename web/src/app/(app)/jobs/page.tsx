"use client";

import { SearchOutlined } from "@ant-design/icons";
import { App, Button, Card, Flex, Input, Segmented, Table, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, errorMessage, formatDateTime, type JobRow } from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import UserAvatar from "@/components/UserAvatar";
import { usePolling } from "@/lib/polling";
import StatusText, { type StatusTone } from "@/components/StatusText";
import FilterSelect from "@/components/FilterSelect";

const REFRESH_MS = 5000;
const PAGE_SIZE = 300; // JOB_LIST_LIMIT in the api

const STATUS: Record<JobRow["status"], { label: string; tone: StatusTone }> = {
  queued: { label: "Chờ", tone: "waiting" },
  running: { label: "Đang chạy", tone: "active" },
  done: { label: "Xong", tone: "success" },
  failed: { label: "Lỗi", tone: "danger" },
  cancelled: { label: "Đã hủy", tone: "idle" },
};

/** The status filter: "Đang chạy" also holds the jobs still waiting for the worker. */
type View = "all" | "active" | "failed" | "done";
const VIEWS: { value: View; label: string; statuses: JobRow["status"][] | null }[] = [
  { value: "all", label: "Tất cả", statuses: null },
  { value: "active", label: "Đang chạy", statuses: ["queued", "running"] },
  { value: "failed", label: "Lỗi", statuses: ["failed"] },
  { value: "done", label: "Xong", statuses: ["done"] },
];

function options(values: string[]): { value: string; label: string }[] {
  return [...new Set(values)].sort((a, b) => a.localeCompare(b, "vi")).map((value) => ({ value, label: value }));
}

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
  const [view, setView] = useState<View>("all");
  const [kind, setKind] = useState<string | null>(null);
  const [person, setPerson] = useState<string | null>(null);
  const [search, setSearch] = useState("");

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

  const counts = useMemo(
    () =>
      Object.fromEntries(
        VIEWS.map(({ value, statuses }) => [
          value,
          statuses ? shown.filter((row) => statuses.includes(row.status)).length : shown.length,
        ]),
      ) as Record<View, number>,
    [shown],
  );

  const filtered = useMemo(() => {
    const statuses = VIEWS.find((item) => item.value === view)?.statuses;
    const words = search.trim().toLocaleLowerCase("vi");
    return shown.filter(
      (row) =>
        (!statuses || statuses.includes(row.status)) &&
        (!kind || row.kind_label === kind) &&
        (!person || row.created_by === person) &&
        (!words || row.video_title.toLocaleLowerCase("vi").includes(words)),
    );
  }, [shown, view, kind, person, search]);
  const filtering = view !== "all" || kind !== null || person !== null || search.trim() !== "";

  const columns: ColumnsType<JobRow> = [
    {
      title: "Job",
      key: "job",
      width: 300,
      // A long title takes one line, in full on hover, instead of squeezing to a word per line.
      render: (_, row) => (
        <Flex vertical style={{ minWidth: 0 }}>
          <Typography.Text strong ellipsis={{ tooltip: row.video_title }} style={{ maxWidth: 280 }}>
            {row.video_title}
          </Typography.Text>
          <Typography.Text type="secondary" style={{ fontSize: 13 }}>
            {row.kind_label}, #{row.id}
          </Typography.Text>
        </Flex>
      ),
    },
    {
      title: "Trạng thái",
      key: "status",
      width: 130,
      render: (_, row) => {
        const status = STATUS[row.status] ?? { label: row.status, tone: "idle" as const };
        return <StatusText tone={status.tone}>{status.label}</StatusText>;
      },
    },
    {
      title: "Người bấm",
      key: "created_by",
      width: 170,
      render: (_, row) => (
        <Flex gap={8} align="center">
          <UserAvatar initial={row.created_by.charAt(0).toUpperCase()} size={24} />
          <Typography.Text ellipsis={{ tooltip: row.created_by }}>{row.created_by}</Typography.Text>
        </Flex>
      ),
    },
    {
      title: "Bắt đầu",
      key: "started",
      width: 160,
      render: (_, row) => (
        <Flex vertical>
          <span>{row.started_at ? formatDateTime(row.started_at) : "—"}</span>
          <Typography.Text type="secondary" style={{ fontSize: 13 }}>
            {duration(row.duration_seconds)}
          </Typography.Text>
        </Flex>
      ),
    },
    {
      title: "AI",
      key: "ai",
      width: 220,
      render: (_, row) => {
        const calls = row.kind === "image" ? row.image_calls : row.claude_calls;
        return (
          <Flex vertical style={{ minWidth: 0 }}>
            <span>{calls > 0 ? `${calls} lượt gọi` : "Không gọi AI"}</span>
            {row.llm && (
              <Typography.Text type="secondary" ellipsis={{ tooltip: row.llm }} style={{ fontSize: 13, maxWidth: 200 }}>
                {row.llm}
              </Typography.Text>
            )}
          </Flex>
        );
      },
    },
    {
      title: "Lỗi",
      key: "error",
      render: (_, row) =>
        row.error ? (
          <Typography.Paragraph
            type="danger"
            ellipsis={{ rows: 2, tooltip: row.error }}
            style={{ margin: 0, minWidth: 220 }}
          >
            {row.error}
          </Typography.Paragraph>
        ) : (
          <Typography.Text type="secondary">—</Typography.Text>
        ),
    },
  ];

  return (
    <>
      <PageHeader
        title="Nhật ký job"
        description="Mọi việc chạy nền: viết kịch bản, render, đăng và kiểm tra bài Facebook. Danh sách tự cập nhật; bấm một dòng để mở video của nó."
      >
        <Input
          allowClear
          aria-label="Tìm theo video"
          placeholder="Tìm theo tên video"
          prefix={<SearchOutlined />}
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          style={{ width: 240 }}
        />
        <Segmented<View>
          aria-label="Trạng thái"
          value={view}
          onChange={setView}
          options={VIEWS.map(({ value, label }) => ({ value, label: `${label} (${counts[value]})` }))}
        />
        <FilterSelect
          aria-label="Loại"
          placeholder="Mọi loại"
          value={kind}
          onChange={(value) => setKind(value ?? null)}
          options={options(shown.map((row) => row.kind_label))}
          style={{ minWidth: 170 }}
        />
        <FilterSelect
          aria-label="Người bấm"
          placeholder="Mọi người"
          value={person}
          onChange={(value) => setPerson(value ?? null)}
          options={options(shown.map((row) => row.created_by))}
          style={{ minWidth: 150 }}
        />
      </PageHeader>
      <Card styles={{ body: { padding: 0 } }}>
        <Table<JobRow>
          rowKey="id"
          columns={columns}
          dataSource={filtered}
          loading={loading}
          pagination={{ pageSize: 50, hideOnSinglePage: true, showSizeChanger: false }}
          scroll={{ x: 1200 }}
          locale={{ emptyText: filtering ? "Không có job nào khớp" : "Chưa có job nào" }}
          onRow={(row) => ({
            // A plan job has no video: it opens Kho kiến thức, where the plan is; an article's job opens the article.
            onClick: () =>
              router.push(
                row.article_id !== null
                  ? `/articles/${row.article_id}`
                  : row.video_id === null
                    ? "/knowledge"
                    : `/videos/${row.video_id}`,
              ),
            style: { cursor: "pointer" },
          })}
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
