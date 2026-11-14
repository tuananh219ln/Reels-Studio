"use client";

import EmptyState from "@/components/EmptyState";
import { formatCount } from "@/components/PostMetrics";
import VideoThumbnail from "@/components/VideoThumbnail";
import { api, errorMessage, formatDateTime, type UnmatchedPost, type VideoRow } from "@/lib/api";
import { App, Button, Flex, Popconfirm, Select, Spin, Table, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useCallback, useEffect, useState } from "react";

/** "Chưa khớp": reels posted on a Page outside the app (Meta Business Suite), imported with no video yet. Each is
 * confirmed with its suggestion, given another video, kept as "Video ngoài" (followed without a video) or ignored
 * (hidden, no longer read). Several confirmed at once with "Xác nhận tất cả gợi ý". */
export default function UnmatchedTable({ platform, onChanged }: { platform: string | null; onChanged: () => void }) {
  const { message } = App.useApp();
  const [rows, setRows] = useState<UnmatchedPost[] | null>(null);
  const [videos, setVideos] = useState<{ value: number; label: string }[]>([]);
  const [picked, setPicked] = useState<number[]>([]);
  const [choosing, setChoosing] = useState<number | null>(null);

  const load = useCallback(
    () =>
      api<UnmatchedPost[]>(`/posts/unmatched${platform ? `?platform=${platform}` : ""}`).then(setRows, (err) => {
        message.error(errorMessage(err));
      }),
    [platform, message],
  );
  useEffect(() => {
    load();
  }, [load]);
  useEffect(() => {
    api<VideoRow[]>("/videos").then(
      (list) => setVideos(list.map((video) => ({ value: video.id, label: video.name || video.title || video.topic }))),
      () => setVideos([]),
    );
  }, []);

  async function send(path: string, method: "PATCH" | "POST", body: unknown, done: string) {
    try {
      await api(path, method, body);
      message.success(done);
      setPicked([]);
      setChoosing(null);
      await load();
      onChanged();
    } catch (err) {
      message.error(errorMessage(err));
    }
  }

  if (rows === null) {
    return (
      <Flex justify="center" style={{ padding: 48 }}>
        <Spin />
      </Flex>
    );
  }
  if (rows.length === 0) {
    return <EmptyState description="Không có bài nào chưa khớp. Bài đăng ngoài app được đồng bộ mỗi giờ." />;
  }

  const columns: ColumnsType<UnmatchedPost> = [
    {
      title: "Bài trên nền tảng",
      key: "post",
      width: 360,
      render: (_, post) => (
        <Flex gap={12} align="center">
          <VideoThumbnail name={post.caption || "Reel"} url={post.thumbnail_url} width={36} />
          <Flex vertical style={{ minWidth: 0 }}>
            <Typography.Text ellipsis={{ tooltip: post.caption }} style={{ maxWidth: 280 }}>
              {post.caption || "(không có caption)"}
            </Typography.Text>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {post.channel ?? "—"} · {post.published_at ? formatDateTime(post.published_at) : "—"} ·{" "}
              {post.views === null ? "— view" : `${formatCount(post.views)} view`}
              {post.url && (
                <>
                  {" · "}
                  <a href={post.url} target="_blank" rel="noreferrer">
                    Xem bài ↗
                  </a>
                </>
              )}
            </Typography.Text>
          </Flex>
        </Flex>
      ),
    },
    {
      title: "Gợi ý video",
      key: "suggested",
      width: 300,
      render: (_, post) =>
        choosing === post.id ? (
          <Select
            showSearch
            autoFocus
            size="small"
            aria-label="Chọn video"
            placeholder="Tìm video theo tiêu đề"
            optionFilterProp="label"
            options={videos}
            onChange={(value: number) => send(`/posts/${post.id}`, "PATCH", { video_id: value }, "Đã gắn video")}
            style={{ width: 260 }}
          />
        ) : post.suggested ? (
          <Flex gap={8} align="center">
            <VideoThumbnail name={post.suggested.name} url={post.suggested.thumbnail_url} width={24} />
            <Typography.Text ellipsis style={{ maxWidth: 200 }}>
              {post.suggested.name}
            </Typography.Text>
            <Typography.Text type="secondary">{post.suggested.score ?? 0}%</Typography.Text>
          </Flex>
        ) : (
          <Typography.Text type="secondary">Không có gợi ý</Typography.Text>
        ),
    },
    {
      title: "Thao tác",
      key: "actions",
      render: (_, post) => (
        <Flex gap={4} wrap>
          {post.suggested && (
            <Button
              size="small"
              type="primary"
              onClick={() => send(`/posts/${post.id}`, "PATCH", { video_id: post.suggested!.id }, "Đã xác nhận")}
            >
              Xác nhận
            </Button>
          )}
          <Button size="small" onClick={() => setChoosing(choosing === post.id ? null : post.id)}>
            Chọn video khác
          </Button>
          <Button
            size="small"
            onClick={() => send(`/posts/${post.id}`, "PATCH", { match_status: "external" }, "Đã để là video ngoài")}
          >
            Video ngoài
          </Button>
          <Popconfirm
            title="Bỏ qua bài này?"
            description="Bài bị ẩn và không đo view nữa."
            okText="Bỏ qua"
            cancelText="Không"
            onConfirm={() => send(`/posts/${post.id}`, "PATCH", { match_status: "ignored" }, "Đã bỏ qua")}
          >
            <Button size="small">Bỏ qua</Button>
          </Popconfirm>
        </Flex>
      ),
    },
  ];

  const withSuggestion = picked.filter((id) => rows.some((row) => row.id === id && row.suggested));
  return (
    <div data-testid="unmatched">
      <Flex gap={8} align="center" style={{ padding: "0 16px 12px" }}>
        <Button
          disabled={withSuggestion.length === 0}
          onClick={() =>
            send(
              "/posts/unmatched/confirm",
              "POST",
              { post_ids: withSuggestion },
              `Đã xác nhận ${withSuggestion.length} bài`,
            )
          }
        >
          Xác nhận tất cả gợi ý ({withSuggestion.length})
        </Button>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          Chọn các dòng có gợi ý rồi xác nhận một lần.
        </Typography.Text>
      </Flex>
      <Table<UnmatchedPost>
        rowKey="id"
        size="small"
        columns={columns}
        dataSource={rows}
        pagination={{ pageSize: 50, hideOnSinglePage: true, showSizeChanger: false }}
        rowSelection={{ selectedRowKeys: picked, onChange: (keys) => setPicked(keys as number[]) }}
        scroll={{ x: "max-content" }}
      />
    </div>
  );
}
