"use client";

import PostMetrics, { formatCount } from "@/components/PostMetrics";
import StatusText from "@/components/StatusText";
import PostActions from "@/components/video/PostActions";
import { api, errorMessage, formatDateTime, type BoardPlatform, type VideoPost, type VideoPosts } from "@/lib/api";
import { App, Button, Flex, Input, Modal, Popconfirm, Spin, Table, Tag, Tooltip, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { usePolling } from "@/lib/polling";
import { useCallback, useEffect, useState } from "react";
import { PLATFORM_LABEL, SourceChip, STATE_LABEL, STATE_TONE } from "./boardText";

type Line = { key: string; platform: BoardPlatform; post: VideoPost | null };

/** A mark's value: "—" before it is reached, "n/a" past it with no reading around it, "ước tính" when taken
 * between two readings. */
function mark(post: VideoPost, name: "24h" | "48h" | "7d", value: number | null) {
  if (value === null) {
    return post.marks_missed.includes(name) ? (
      <Tooltip title="Không có lần đo nào quanh mốc này">
        <Typography.Text type="secondary">n/a</Typography.Text>
      </Tooltip>
    ) : (
      <Typography.Text type="secondary">—</Typography.Text>
    );
  }
  return post.marks_estimated.includes(name) ? (
    <Tooltip title="ước tính, giữa hai lần đo">
      <span>~{formatCount(value)}</span>
    </Tooltip>
  ) : (
    formatCount(value)
  );
}

/** Views over time, as a small line (at most 30 readings). */
function Sparkline({ points }: { points: number[] }) {
  if (points.length < 2) return null;
  const width = 72;
  const height = 20;
  const top = Math.max(...points);
  const bottom = Math.min(...points);
  const span = top - bottom || 1;
  const path = points
    .map((value, index) => {
      const x = (index / (points.length - 1)) * width;
      const y = height - 2 - ((value - bottom) / span) * (height - 4);
      return `${index === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  return (
    <svg width={width} height={height} role="img" aria-label="Xu hướng view" data-testid="sparkline">
      <path d={path} fill="none" stroke="currentColor" strokeWidth={1.5} opacity={0.7} />
    </svg>
  );
}

/** A video's opened row on "Bài đăng": one line per post, on every platform, with what each can still do; a
 * platform with none says "Chưa đăng" with the MP4 and its caption. */
export default function VideoPostsRow({
  videoId,
  onPaste,
  onDownload,
  onChanged,
}: {
  videoId: number;
  onPaste: (videoId: number, platform: BoardPlatform) => void;
  onDownload: (videoId: number, platform: BoardPlatform) => void;
  onChanged: () => void;
}) {
  const { message } = App.useApp();
  const [data, setData] = useState<VideoPosts | null>(null);
  const [editing, setEditing] = useState<VideoPost | null>(null);
  const [link, setLink] = useState("");

  const load = useCallback(
    () =>
      api<VideoPosts>(`/posts/videos/${videoId}`).then(setData, (err) => {
        message.error(errorMessage(err));
      }),
    [videoId, message],
  );
  useEffect(() => {
    load();
  }, [load]);
  // A check, a take-down or "Cập nhật view" on a Facebook post runs in the worker: read again until it is done,
  // and the board's row with it.
  const busy = (data?.posts ?? []).some(
    (post) => post.refreshing || (post.fb && (post.fb.busy || post.fb.metrics.pending)),
  );
  usePolling(() => (busy ? load().then(onChanged) : Promise.resolve()), 3000);

  async function changed() {
    await load();
    onChanged();
  }
  async function send(path: string, method: "PATCH" | "DELETE", body?: unknown, done?: string) {
    try {
      await api(path, method, body);
      if (done) message.success(done);
      await changed();
      return true;
    } catch (err) {
      message.error(errorMessage(err));
      return false;
    }
  }

  if (data === null) {
    return (
      <Flex justify="center" style={{ padding: 16 }}>
        <Spin size="small" />
      </Flex>
    );
  }
  const lines: Line[] = [
    ...data.posts.map((post) => ({ key: `p${post.id}`, platform: post.platform, post })),
    ...data.missing.map((platform) => ({ key: `m${platform}`, platform, post: null })),
  ];

  function actions(line: Line) {
    const { post, platform } = line;
    if (post === null) {
      return (
        <Flex gap={4} wrap>
          {platform !== "facebook" && data?.mp4_download_url && (
            <Button size="small" onClick={() => onDownload(videoId, platform)}>
              Tải MP4
            </Button>
          )}
          <Button
            size="small"
            onClick={async () => {
              try {
                await navigator.clipboard.writeText(data?.captions[platform] ?? "");
                message.success(`Đã chép caption ${PLATFORM_LABEL[platform]}`);
              } catch {
                message.error("Trình duyệt không cho chép, hãy chép tay ở trang video");
              }
            }}
          >
            Copy caption
          </Button>
        </Flex>
      );
    }
    if (post.fb) {
      return (
        <PostActions
          post={post.fb}
          disabled={post.fb.busy}
          onDone={changed}
          compact
          retryJobId={post.fb.attempt?.state === "failed" ? post.fb.attempt.job_id : null}
        />
      );
    }
    if (post.source !== "manual_link") return null;
    if (post.state === "pending_link") {
      return (
        <Flex gap={4} wrap>
          <Button size="small" type="primary" onClick={() => onPaste(videoId, platform)}>
            Dán link
          </Button>
          <Popconfirm
            title="Hủy chờ dán link?"
            okText="Hủy chờ"
            cancelText="Không"
            onConfirm={() => send(`/posts/${post.id}`, "PATCH", { status: "cancelled" }, "Đã hủy chờ")}
          >
            <Button size="small">Hủy chờ</Button>
          </Popconfirm>
        </Flex>
      );
    }
    return (
      <Flex gap={4} wrap>
        <Button
          size="small"
          onClick={() => {
            setEditing(post);
            setLink(post.url ?? "");
          }}
        >
          Sửa link
        </Button>
        <Popconfirm
          title="Gỡ bài này khỏi app?"
          description="Bài trên nền tảng vẫn còn nguyên."
          okText="Gỡ"
          cancelText="Không"
          okButtonProps={{ danger: true }}
          onConfirm={() => send(`/posts/${post.id}`, "DELETE", undefined, "Đã gỡ khỏi app")}
        >
          <Button size="small" danger>
            Gỡ
          </Button>
        </Popconfirm>
      </Flex>
    );
  }

  const columns: ColumnsType<Line> = [
    { title: "Nền tảng", key: "platform", width: 130, render: (_, line) => PLATFORM_LABEL[line.platform] },
    {
      title: "Kênh / Link",
      key: "channel",
      width: 240,
      render: (_, { post }) =>
        post === null ? (
          <StatusText tone="idle">Chưa đăng</StatusText>
        ) : (
          <Flex vertical gap={2}>
            <Flex gap={6} align="center" wrap>
              <StatusText tone={STATE_TONE[post.state]}>{STATE_LABEL[post.state]}</StatusText>
              <SourceChip source={post.source} />
            </Flex>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {post.channel ?? "—"}
              {(post.url ?? post.fb?.url) && (
                <>
                  {" · "}
                  <a href={(post.url ?? post.fb?.url)!} target="_blank" rel="noreferrer">
                    Xem bài ↗
                  </a>
                </>
              )}
            </Typography.Text>
            {post.fb?.closed_at && (
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                {post.fb.status === "deleted" ? "Xóa" : "Hủy"}: {post.fb.closed_by ?? "Trên Facebook"},{" "}
                {formatDateTime(post.fb.closed_at)}
              </Typography.Text>
            )}
            {post.error && (
              <Typography.Text type="danger" style={{ fontSize: 12 }} ellipsis={{ tooltip: post.error }}>
                {post.error}
              </Typography.Text>
            )}
          </Flex>
        ),
    },
    {
      title: "Giờ đăng",
      key: "at",
      width: 170,
      render: (_, { post }) => {
        const at = post?.published_at ?? post?.scheduled_at ?? null;
        if (!at) return <Typography.Text type="secondary">—</Typography.Text>;
        return (
          <Flex gap={4} align="center" wrap>
            {formatDateTime(at)}
            {post?.published_at_source === "api" && <Tag style={{ fontSize: 11 }}>tự lấy</Tag>}
          </Flex>
        );
      },
    },
    { title: "24h", key: "24h", width: 80, render: (_, { post }) => (post ? mark(post, "24h", post.views_24h) : null) },
    { title: "48h", key: "48h", width: 80, render: (_, { post }) => (post ? mark(post, "48h", post.views_48h) : null) },
    { title: "7 ngày", key: "7d", width: 80, render: (_, { post }) => (post ? mark(post, "7d", post.views_7d) : null) },
    {
      title: "Xu hướng",
      key: "trend",
      width: 90,
      render: (_, { post }) => (post ? <Sparkline points={post.sparkline} /> : null),
    },
    {
      title: "View",
      key: "views",
      width: 150,
      render: (_, { post }) =>
        post?.fb ? (
          <PostMetrics post={post.fb} onAsked={changed} compact />
        ) : post ? (
          <Tooltip
            title={post.metrics_updated_at ? `Cập nhật lần cuối ${formatDateTime(post.metrics_updated_at)}` : undefined}
          >
            <span>
              {post.views === null ? <Typography.Text type="secondary">—</Typography.Text> : formatCount(post.views)}
              {post.refreshing && <Spin size="small" style={{ marginLeft: 6 }} />}
            </span>
          </Tooltip>
        ) : null,
    },
    { title: "Thao tác", key: "actions", render: (_, line) => actions(line) },
  ];

  return (
    <div data-testid="post-rows">
      <Table<Line>
        rowKey="key"
        size="small"
        columns={columns}
        dataSource={lines}
        pagination={false}
        scroll={{ x: "max-content" }}
      />
      <Modal
        open={editing !== null}
        title="Sửa link bài"
        okText="Lưu"
        cancelText="Hủy"
        onCancel={() => setEditing(null)}
        onOk={async () => {
          if (editing && (await send(`/posts/${editing.id}`, "PATCH", { url: link }, "Đã sửa link"))) setEditing(null);
        }}
      >
        <Input aria-label="Link bài" value={link} onChange={(event) => setLink(event.target.value)} />
      </Modal>
    </div>
  );
}
