"use client";

import { AppstoreOutlined, CalendarOutlined, SearchOutlined, UnorderedListOutlined } from "@ant-design/icons";
import { App, Button, Card, Col, Empty, Flex, Input, Row, Segmented, Select, Spin, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, errorMessage, formatDateTime, type PostRow, type PostStatus } from "@/lib/api";
import { POST_STATUS } from "@/lib/postStatus";
import PageHeader from "@/components/PageHeader";
import VideoThumbnail from "@/components/VideoThumbnail";
import PostActions from "@/components/video/PostActions";
import PostMetrics, { viewsOf } from "@/components/PostMetrics";
import { usePolling } from "@/lib/polling";
import { useRememberedView, type View } from "@/lib/view";

const VIEW_KEY = "reels-studio.posts-view";
const STATUSES: PostStatus[] = ["scheduled", "published", "cancelled", "deleted"];

type Sort = "latest" | "views";

/** Lower case and one Unicode form, so a typed "Đ" or a composed vowel still finds the title. */
function folded(text: string): string {
  return text.normalize("NFC").toLocaleLowerCase("vi");
}

/** The reels posted, scheduled, cancelled or deleted from their video page or here, latest time first or most viewed
 * first, with their numbers on Facebook. */
export default function PostsPage() {
  const { message } = App.useApp();
  const [posts, setPosts] = useState<PostRow[] | null>(null);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<PostStatus | "all">("all");
  const [fanpage, setFanpage] = useState<string | null>(null);
  const [sort, setSort] = useState<Sort>("latest");
  const [view, chooseView] = useRememberedView(VIEW_KEY);

  const load = useCallback(
    () =>
      api<PostRow[]>("/posts")
        .then(setPosts)
        .catch((err) => message.error(errorMessage(err))),
    [message],
  );

  useEffect(() => {
    load();
  }, [load]);

  // A check, cancel, delete or "Cập nhật view" runs in the worker, so its post changes a while after the button.
  const busy = (posts ?? []).some((post) => post.busy || post.metrics.pending);
  usePolling(() => (busy ? load() : Promise.resolve()), 3000);

  const all = posts ?? [];
  const pages = [...new Set(all.map((post) => post.fanpage).filter((name): name is string => Boolean(name)))];
  const words = folded(query.trim());
  const shown = all.filter(
    (post) =>
      (status === "all" || post.status === status) &&
      (fanpage === null || post.fanpage === fanpage) &&
      (!words || folded(post.title).includes(words)),
  );
  // The api sends the latest time first; a stable sort keeps that order among posts with the same views.
  if (sort === "views") shown.sort((a, b) => viewsOf(b) - viewsOf(a));
  const filtered = Boolean(words) || status !== "all" || fanpage !== null;
  const count = (which: PostStatus) => all.filter((post) => post.status === which).length;

  return (
    <>
      <PageHeader
        title="Bài đăng"
        description={all.length > 0 && `${count("scheduled")} bài đã hẹn lịch · ${count("published")} bài đã đăng.`}
        actions={
          <Link prefetch={false} href="/calendar">
            <Button icon={<CalendarOutlined />}>Xem dạng lịch</Button>
          </Link>
        }
      >
        <Input
          aria-label="Tìm theo tiêu đề"
          prefix={<SearchOutlined />}
          placeholder="Tìm theo tiêu đề"
          allowClear
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          style={{ width: 320, maxWidth: "100%" }}
        />
        <Select
          aria-label="Lọc theo trạng thái"
          value={status}
          onChange={setStatus}
          options={[
            { value: "all", label: "Mọi trạng thái" },
            ...STATUSES.map((value) => ({ value, label: POST_STATUS[value].label })),
          ]}
          style={{ width: 170 }}
        />
        <Select
          aria-label="Sắp xếp"
          value={sort}
          onChange={setSort}
          options={[
            { value: "latest", label: "Giờ đăng mới nhất" },
            { value: "views", label: "Nhiều view nhất" },
          ]}
          style={{ width: 180 }}
        />
        {pages.length > 1 && (
          <Select
            aria-label="Lọc theo Fanpage"
            allowClear
            placeholder="Mọi Fanpage"
            value={fanpage}
            onChange={(value) => setFanpage(value ?? null)}
            options={pages.map((name) => ({ value: name, label: name }))}
            style={{ width: 220 }}
          />
        )}
        <Segmented
          aria-label="Kiểu hiển thị"
          value={view}
          onChange={(value) => chooseView(value as View)}
          style={{ marginLeft: "auto" }}
          options={[
            { value: "grid", icon: <AppstoreOutlined />, title: "Dạng lưới" },
            { value: "list", icon: <UnorderedListOutlined />, title: "Dạng danh sách" },
          ]}
        />
      </PageHeader>
      {posts === null ? (
        <Flex justify="center" style={{ padding: 48 }}>
          <Spin />
        </Flex>
      ) : shown.length === 0 ? (
        <Card>
          <Empty description={filtered ? "Không có bài đăng nào khớp" : "Chưa có video nào đã đăng hoặc hẹn lịch"} />
        </Card>
      ) : view === "grid" ? (
        <Row gutter={[16, 16]}>
          {shown.map((post) => (
            <Col key={post.id} xs={12} sm={8} md={6} xl={4} style={{ display: "flex" }}>
              <PostCard post={post} onDone={load} />
            </Col>
          ))}
        </Row>
      ) : (
        <PostTable posts={shown} onDone={load} />
      )}
    </>
  );
}

function StatusTag({ post }: { post: PostRow }) {
  return (
    <Tag color={POST_STATUS[post.status].color} style={{ marginInlineEnd: 0 }}>
      {POST_STATUS[post.status].label}
    </Tag>
  );
}

function ReelLink({ post }: { post: PostRow }) {
  return (
    post.url && (
      <a href={post.url} target="_blank" rel="noreferrer">
        Xem Reel
      </a>
    )
  );
}

/** Who cancelled or deleted the post and when; "Trên Facebook" when a check found it so. */
function closedLine(post: PostRow): string | null {
  return post.closed_at && `${post.closed_by ?? "Trên Facebook"} · ${formatDateTime(post.closed_at)}`;
}

/** One post: a video posted to two Pages has two cards with the same thumbnail, told apart by Page and time. */
function PostCard({ post, onDone }: { post: PostRow; onDone: () => void }) {
  const closed = closedLine(post);
  return (
    <Card
      data-testid="post-card"
      style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}
      styles={{ body: { padding: 12, flex: 1, display: "flex", flexDirection: "column", gap: 6 } }}
      cover={
        <Link prefetch={false} href={`/videos/${post.video_id}`} aria-label={post.title} tabIndex={-1}>
          <VideoThumbnail name={post.title} url={post.thumbnail_url} />
        </Link>
      }
    >
      <Link prefetch={false} href={`/videos/${post.video_id}`}>
        <Typography.Paragraph strong ellipsis={{ rows: 2 }} style={{ margin: 0 }}>
          {post.title}
        </Typography.Paragraph>
      </Link>
      <Flex wrap gap={6} align="center">
        <StatusTag post={post} />
        <ReelLink post={post} />
      </Flex>
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        {post.fanpage ?? "—"}
        <br />
        {formatDateTime(post.at)} · {post.created_by}
        {closed && (
          <>
            <br />
            Hủy/xóa: {closed}
          </>
        )}
      </Typography.Text>
      <PostMetrics post={post} onAsked={onDone} />
      <div style={{ marginTop: "auto" }}>
        <PostActions post={post} disabled={post.busy} onDone={onDone} />
      </div>
    </Card>
  );
}

/** "Dạng danh sách": one row per post, to scan many at once. */
function PostTable({ posts, onDone }: { posts: PostRow[]; onDone: () => void }) {
  const columns: ColumnsType<PostRow> = [
    {
      title: "Video",
      key: "video",
      render: (_, post) => (
        <Flex align="center" gap={12}>
          <VideoThumbnail name={post.title} url={post.thumbnail_url} width={36} />
          <Link prefetch={false} href={`/videos/${post.video_id}`} style={{ minWidth: 0 }}>
            <Typography.Text strong ellipsis style={{ maxWidth: 360 }}>
              {post.title}
            </Typography.Text>
          </Link>
        </Flex>
      ),
    },
    { title: "Fanpage", key: "fanpage", width: 200, render: (_, post) => post.fanpage ?? "—" },
    { title: "Trạng thái", key: "status", width: 120, render: (_, post) => <StatusTag post={post} /> },
    { title: "Giờ đăng", key: "at", width: 150, render: (_, post) => formatDateTime(post.at) },
    { title: "View", key: "views", width: 230, render: (_, post) => <PostMetrics post={post} onAsked={onDone} /> },
    { title: "Người đăng", dataIndex: "created_by", width: 160 },
    { title: "Hủy/xóa", key: "closed", width: 190, render: (_, post) => closedLine(post) },
    { title: "", key: "reel", width: 90, render: (_, post) => <ReelLink post={post} /> },
    {
      title: "",
      key: "actions",
      width: 170,
      render: (_, post) => <PostActions post={post} disabled={post.busy} onDone={onDone} />,
    },
  ];
  return (
    <Card styles={{ body: { padding: 0 } }}>
      <Table<PostRow>
        rowKey="id"
        columns={columns}
        dataSource={posts}
        pagination={{ pageSize: 50, hideOnSinglePage: true }}
        scroll={{ x: 1430 }}
      />
    </Card>
  );
}
