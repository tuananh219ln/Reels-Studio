"use client";

import { CalendarOutlined, SearchOutlined } from "@ant-design/icons";
import { App, Button, Card, Empty, Flex, Input, Select, Spin, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, errorMessage, formatDateTime, type PostRow, type PostStatus } from "@/lib/api";
import { POST_STATUS } from "@/lib/postStatus";
import PageHeader from "@/components/PageHeader";
import VideoTitleCell from "@/components/VideoTitleCell";
import PostActions from "@/components/video/PostActions";
import PostKpis from "@/components/PostKpis";
import PostSuggestions from "@/components/PostSuggestions";
import PostMetrics, { formatCount, viewsOf } from "@/components/PostMetrics";
import { useFreshenOnOpen } from "@/lib/freshen";
import { usePolling } from "@/lib/polling";

const STATUSES: PostStatus[] = ["scheduled", "published", "cancelled", "deleted"];

type Sort = "latest" | "views";

/** "Đang hoạt động" (the default) keeps the posts that are live or still to go out; cancelled and deleted ones stay
 * one choice away, as history. */
type StatusFilter = PostStatus | "all" | "active";
const ACTIVE: PostStatus[] = ["scheduled", "published"];

function statusMatches(post: PostRow, filter: StatusFilter): boolean {
  if (filter === "all") return true;
  if (filter === "active") return ACTIVE.includes(post.status);
  return post.status === filter;
}

/** The posts of one video, kept in the order they are shown. */
type Group = { videoId: number; title: string; thumbnailUrl: string | null; posts: PostRow[] };

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
  const [status, setStatus] = useState<StatusFilter>("active");
  const [fanpage, setFanpage] = useState<string | null>(null);
  const [sort, setSort] = useState<Sort>("latest");

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
  // Followed posts not read lately are read again on opening, without pressing "Cập nhật view" on each.
  useFreshenOnOpen("/posts/freshen", load);

  // A check, cancel, delete or "Cập nhật view" runs in the worker, so its post changes a while after the button.
  const busy = (posts ?? []).some((post) => post.busy || post.metrics.pending);
  usePolling(() => (busy ? load() : Promise.resolve()), 3000);

  const all = posts ?? [];
  const pages = [...new Set(all.map((post) => post.fanpage).filter((name): name is string => Boolean(name)))];
  const words = folded(query.trim());
  const others = (post: PostRow) =>
    (fanpage === null || post.fanpage === fanpage) && (!words || folded(post.title).includes(words));
  const shown = all.filter((post) => statusMatches(post, status) && others(post));
  // The cancelled and deleted posts "Đang hoạt động" leaves out, so nobody thinks they are lost.
  const hidden = status === "active" ? all.filter((post) => !ACTIVE.includes(post.status) && others(post)).length : 0;
  // The api sends the latest time first; a stable sort keeps that order among posts with the same views.
  if (sort === "views") shown.sort((a, b) => viewsOf(b) - viewsOf(a));
  const filtered = Boolean(words) || status !== "active" || fanpage !== null;
  const count = (which: PostStatus) => all.filter((post) => post.status === which).length;
  const groups = byVideo(shown);

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
            { value: "active", label: "Đang hoạt động" },
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
      </PageHeader>
      <PostKpis posts={posts} />
      <PostSuggestions posts={posts} />
      {posts === null ? (
        <Flex justify="center" style={{ padding: 48 }}>
          <Spin />
        </Flex>
      ) : groups.length === 0 ? (
        <Card>
          <Empty
            description={
              filtered
                ? "Không có bài đăng nào khớp"
                : all.length > 0
                  ? "Không có bài nào đang hẹn lịch hoặc đã đăng"
                  : "Chưa có video nào đã đăng hoặc hẹn lịch"
            }
          />
        </Card>
      ) : (
        <GroupTable groups={groups} onDone={load} />
      )}
      {hidden > 0 && (
        <Flex align="center" gap={4} style={{ marginTop: 8 }} data-testid="hidden-posts">
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            Đang ẩn {hidden} bài đã hủy/xóa ·
          </Typography.Text>
          <Button type="link" size="small" style={{ padding: 0, fontSize: 12 }} onClick={() => setStatus("all")}>
            Xem
          </Button>
        </Flex>
      )}
    </>
  );
}

/** One group per video, in the order its first post is shown, so sorting the posts sorts the videos. */
function byVideo(posts: PostRow[]): Group[] {
  const groups = new Map<number, Group>();
  for (const post of posts) {
    const group = groups.get(post.video_id);
    if (group) group.posts.push(post);
    else
      groups.set(post.video_id, {
        videoId: post.video_id,
        title: post.title,
        thumbnailUrl: post.thumbnail_url,
        posts: [post],
      });
  }
  return [...groups.values()];
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
      <a href={post.url} target="_blank" rel="noreferrer" style={{ whiteSpace: "nowrap" }}>
        Xem Reel
      </a>
    )
  );
}

/** "Đã đăng · 2", one tag per status among the video's posts. */
function StatusSummary({ posts }: { posts: PostRow[] }) {
  const counts = STATUSES.map((value) => [value, posts.filter((post) => post.status === value).length] as const);
  return (
    <Flex wrap gap={4}>
      {counts
        .filter(([, number]) => number > 0)
        .map(([value, number]) => (
          <Tag key={value} color={POST_STATUS[value].color} style={{ marginInlineEnd: 0 }}>
            {POST_STATUS[value].label}
            {number > 1 && ` · ${number}`}
          </Tag>
        ))}
    </Flex>
  );
}

/** The video's views on every post read so far; "—" before the first reading. */
function totalViews(posts: PostRow[]): string {
  const read = posts.filter((post) => viewsOf(post) >= 0);
  return read.length === 0 ? "—" : formatCount(read.reduce((sum, post) => sum + viewsOf(post), 0));
}

/** "Bài đăng": a row per video with what its posts add up to; opening it lists each post with its own Page, time,
 * numbers and actions. */
function GroupTable({ groups, onDone }: { groups: Group[]; onDone: () => void }) {
  const columns: ColumnsType<Group> = [
    {
      title: "Video",
      key: "video",
      render: (_, group) => {
        const pages = [...new Set(group.posts.map((post) => post.fanpage ?? "—"))].join(", ");
        return (
          <VideoTitleCell
            id={group.videoId}
            title={group.title}
            thumbnailUrl={group.thumbnailUrl}
            sub={`${group.posts.length} bài đăng · ${pages}`}
            maxWidth={480}
          />
        );
      },
    },
    { title: "Trạng thái", key: "status", width: 220, render: (_, group) => <StatusSummary posts={group.posts} /> },
    { title: "Tổng view", key: "views", width: 120, render: (_, group) => totalViews(group.posts) },
    {
      title: "Lần đăng gần nhất",
      key: "at",
      width: 170,
      render: (_, group) => formatDateTime(group.posts.map((post) => post.at).reduce((a, b) => (a > b ? a : b))),
    },
  ];
  return (
    <Card styles={{ body: { padding: 0 } }}>
      <Table<Group>
        rowKey="videoId"
        columns={columns}
        dataSource={groups}
        pagination={{ pageSize: 50, hideOnSinglePage: true }}
        scroll={{ x: 900 }}
        onRow={() =>
          ({ "data-testid": "post-group", style: { cursor: "pointer" } }) as React.HTMLAttributes<HTMLElement>
        }
        expandable={{
          expandRowByClick: true,
          expandedRowRender: (group) => <PostTable posts={group.posts} onDone={onDone} />,
        }}
      />
    </Card>
  );
}

/** The posts of one video: told apart by Page and time, each with its own numbers and actions. */
function PostTable({ posts, onDone }: { posts: PostRow[]; onDone: () => void }) {
  const columns: ColumnsType<PostRow> = [
    {
      title: "Fanpage",
      key: "fanpage",
      width: 220,
      render: (_, post) => (
        <Flex vertical>
          <Typography.Text>{post.fanpage ?? "—"}</Typography.Text>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            Người đăng: {post.created_by}
          </Typography.Text>
        </Flex>
      ),
    },
    {
      title: "Giờ đăng",
      key: "at",
      width: 230,
      render: (_, post) => (
        <Flex vertical>
          <span>{formatDateTime(post.at)}</span>
          {post.closed_at && (
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {post.status === "deleted" ? "Xóa" : "Hủy"}: {post.closed_by ?? "Trên Facebook"} ·{" "}
              {formatDateTime(post.closed_at)}
            </Typography.Text>
          )}
        </Flex>
      ),
    },
    {
      title: "Trạng thái",
      key: "status",
      width: 150,
      render: (_, post) => <StatusTag post={post} />,
    },
    {
      title: "View",
      key: "views",
      width: 150,
      render: (_, post) => <PostMetrics post={post} onAsked={onDone} compact />,
    },
    {
      title: "",
      key: "actions",
      render: (_, post) => (
        <Flex align="center" gap={12} wrap={false}>
          <ReelLink post={post} />
          <PostActions post={post} disabled={post.busy} onDone={onDone} />
        </Flex>
      ),
    },
  ];
  return (
    <div data-testid="post-rows">
      <Table<PostRow> rowKey="id" size="small" columns={columns} dataSource={posts} pagination={false} />
    </div>
  );
}
