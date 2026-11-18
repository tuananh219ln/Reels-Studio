"use client";

import EmptyState from "@/components/EmptyState";
import WhoseFilter, { type Whose } from "@/components/WhoseFilter";
import { api, errorMessage, formatDayTime, type CommentTrackerData, type TrackedPost } from "@/lib/api";
import { usePolling } from "@/lib/polling";
import { useUrlChoice } from "@/lib/urlState";
import { App, Card, Flex, Progress, Segmented, Spin, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

const STATE: Record<TrackedPost["state"], { label: string; color: string }> = {
  queued: { label: "Đang chờ đăng", color: "processing" },
  daily: { label: "Mỗi ngày 1 bình luận", color: "cyan" },
  stopped: { label: "Đã dừng (quá 3 ngày)", color: "default" },
  done: { label: "Đã lên đủ", color: "success" },
  not_asked: { label: "Chưa nhờ đăng", color: "warning" },
  failed: { label: "Lỗi", color: "error" },
  no_extras: { label: "Chưa có bình luận chi tiết", color: "default" },
  manual: { label: "Dán link tay", color: "default" },
};

const STAGE: Record<TrackedPost["stage"], string> = {
  new: "Mới",
  daily: "Ngày 2–3",
  stopped: "Quá 3 ngày",
};

type Filter = "all" | "queued" | "todo" | "done";

const FILTERS: { value: Filter; label: string }[] = [
  { value: "all", label: "Tất cả" },
  { value: "queued", label: "Đang chờ đăng" },
  { value: "todo", label: "Cần xử lý" },
  { value: "done", label: "Đã lên đủ" },
];

function matches(post: TrackedPost, filter: Filter): boolean {
  if (filter === "queued") return post.state === "queued" || post.state === "daily";
  if (filter === "done") return post.state === "done";
  if (filter === "todo") return ["not_asked", "failed", "no_extras"].includes(post.state);
  return true;
}

/** "Bình luận" of "Bài đăng": the week's reels and how far the Page's comments under each have gone up. */
export default function CommentTracker() {
  const { message } = App.useApp();
  const [data, setData] = useState<CommentTrackerData | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  // The member's own Pages first: "Cả đội" shows every Page's reels.
  const [whose, setWhose] = useUrlChoice<Whose>("owner", "mine", ["all"]);

  const load = useCallback(
    () =>
      api<CommentTrackerData>(`/posts/comments?owner=${whose === "mine" ? "me" : "team"}`).then(setData, (err) => {
        message.error(errorMessage(err));
      }),
    [message, whose],
  );
  useEffect(() => {
    load();
  }, [load]);
  // The worker writes a comment every minute or so; the table follows it.
  usePolling(load, 30000);

  const rows = useMemo(() => (data?.posts ?? []).filter((post) => matches(post, filter)), [data, filter]);

  if (data === null) return <Spin />;

  const columns: ColumnsType<TrackedPost> = [
    {
      title: "Video",
      key: "video",
      render: (_, post) => (
        <Flex vertical gap={2}>
          <Link href={`/videos/${post.video_id}`}>{post.title}</Link>
          <Typography.Text type="secondary">
            {STAGE[post.stage]} · {post.fanpage ?? "Page đã gỡ"} · lên {formatDayTime(post.live_at)} ·{" "}
            <a href={post.url} target="_blank" rel="noreferrer">
              Mở reel
            </a>
          </Typography.Text>
        </Flex>
      ),
    },
    {
      title: "Bình luận chi tiết đã lên",
      key: "written",
      width: 200,
      render: (_, post) =>
        post.saved === 0 ? (
          <Typography.Text type="secondary">Chưa có ({post.scenes} cảnh)</Typography.Text>
        ) : (
          <Flex vertical gap={0}>
            <Typography.Text>
              {post.written}/{post.saved} bình luận · {post.scenes} cảnh
            </Typography.Text>
            <Progress percent={Math.round((post.written / post.saved) * 100)} size="small" showInfo={false} />
          </Flex>
        ),
    },
    {
      title: "Còn chờ",
      dataIndex: "left",
      width: 90,
      render: (left: number) => (left > 0 ? `${left} bình luận` : "–"),
    },
    {
      title: "Trạng thái",
      key: "state",
      width: 230,
      render: (_, post) => (
        <Flex vertical gap={2} align="start">
          <Tag color={STATE[post.state].color}>{STATE[post.state].label}</Tag>
          {post.state === "not_asked" && (
            <Typography.Text type="secondary">Bấm “Bình luận ngay” trên trang video</Typography.Text>
          )}
          {post.error && <Typography.Text type="danger">{post.error}</Typography.Text>}
          {post.resting_until && (
            <Typography.Text type="secondary">
              {post.state === "daily" ? "Bình luận tiếp theo" : "Nghỉ tới"} {formatDayTime(post.resting_until)}
            </Typography.Text>
          )}
        </Flex>
      ),
    },
    {
      title: "Lượt",
      dataIndex: "position",
      width: 70,
      render: (position: number | null) => (position ? `#${position}` : "–"),
    },
    {
      title: "Dự kiến lên đủ",
      dataIndex: "eta",
      width: 130,
      render: (eta: string | null) => (eta ? `~ ${formatDayTime(eta)}` : "–"),
    },
  ];

  return (
    <Flex vertical gap={16}>
      <Card size="small">
        <Flex vertical gap={4}>
          {data.pages.map((page) => (
            <Typography.Text key={page.id}>
              <b>{page.name}</b>: hôm nay đã bình luận {page.today}/{data.day_cap}
              {page.resting_until ? ` · Page nghỉ tới ${formatDayTime(page.resting_until)}` : ""}
            </Typography.Text>
          ))}
          <Typography.Text type="secondary">
            Reel mới (24 giờ đầu): Page đăng đủ bình luận trong một lượt, cách nhau 45–75 giây. Ngày 2–3: mỗi ngày thêm
            1 bình luận vào giờ ngẫu nhiên 9h–21h. Quá 3 ngày: không thêm bình luận mới. Tối đa {data.day_cap} bình luận
            một Page một ngày. Giờ dự kiến là ước tính, giờ Việt Nam.
          </Typography.Text>
        </Flex>
      </Card>
      <Flex gap={12} wrap>
        <WhoseFilter value={whose} onChange={setWhose} />
        <Segmented<Filter> aria-label="Lọc bình luận" value={filter} onChange={setFilter} options={FILTERS} />
      </Flex>
      {rows.length === 0 ? (
        <EmptyState description="Không có reel nào trong 3 ngày qua ở mục này" />
      ) : (
        <Table<TrackedPost>
          rowKey="post_id"
          columns={columns}
          dataSource={rows}
          pagination={false}
          scroll={{ x: 900 }}
          size="middle"
        />
      )}
    </Flex>
  );
}
