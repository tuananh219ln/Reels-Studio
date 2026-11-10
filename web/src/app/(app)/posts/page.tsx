"use client";

import { CalendarOutlined, SearchOutlined, UnorderedListOutlined } from "@ant-design/icons";
import { App, Card, Empty, Flex, Input, Segmented, Select, Spin, Table, Tabs, Tooltip, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { Suspense, useCallback, useEffect, useState } from "react";
import { api, errorMessage, formatDateTime, type PostRow } from "@/lib/api";
import { useUrlChoice, useUrlPage } from "@/lib/urlState";
import { SHOWN_STATUS, shownStatus, type ShownStatus } from "@/lib/postStatus";
import PageHeader from "@/components/PageHeader";
import PostCalendar from "@/components/PostCalendar";
import VideoTitleCell from "@/components/VideoTitleCell";
import PostActions from "@/components/video/PostActions";
import PostKpis from "@/components/PostKpis";
import PostSuggestions from "@/components/PostSuggestions";
import PostMetrics, { formatCount, viewsOf } from "@/components/PostMetrics";
import { useFreshenOnOpen } from "@/lib/freshen";
import { usePolling } from "@/lib/polling";
import StatusText from "@/components/StatusText";
import FilterSelect from "@/components/FilterSelect";
import WhoseFilter, { type Whose } from "@/components/WhoseFilter";
import { useMe } from "@/components/MeContext";

/** The order a video's status tags are listed in. */
const STATUSES: ShownStatus[] = ["failed", "pending", "scheduled", "published", "cancelled", "deleted"];

type Sort = "latest" | "views";

/** The status tabs. "Đang hoạt động" (the default) keeps every post still to do with: on its way, failed, scheduled
 * or live; cancelled and deleted ones stay one tab away, as history. */
type StatusFilter = "active" | "published" | "scheduled" | "failed" | "closed" | "all";
const FILTERS: { value: StatusFilter; label: string; holds: ShownStatus[] }[] = [
  { value: "active", label: "Đang hoạt động", holds: ["pending", "failed", "scheduled", "published"] },
  { value: "published", label: "Đã đăng", holds: ["published"] },
  { value: "scheduled", label: "Đã hẹn lịch", holds: ["scheduled"] },
  { value: "failed", label: "Thất bại", holds: ["failed"] },
  { value: "closed", label: "Đã hủy/xóa", holds: ["cancelled", "deleted"] },
  { value: "all", label: "Tất cả", holds: STATUSES },
];

function statusMatches(post: PostRow, filter: StatusFilter): boolean {
  return FILTERS.find((item) => item.value === filter)!.holds.includes(shownStatus(post));
}

type View = "list" | "calendar";

/** The posts of one video, kept in the order they are shown. */
type Group = { videoId: number; title: string; thumbnailUrl: string | null; posts: PostRow[] };

/** Lower case and one Unicode form, so a typed "Đ" or a composed vowel still finds the title. */
function folded(text: string): string {
  return text.normalize("NFC").toLocaleLowerCase("vi");
}

/** The reels on their way to Facebook, posted, scheduled, failed, cancelled or deleted, latest time first or most
 * viewed first, with their numbers on Facebook; or, as "Lịch" (`?view=calendar`), the scheduled and posted ones in a
 * month. */
export default function PostsPage() {
  // The view, search and filters come from the address, which a static page only knows in the browser: Suspense keeps
  // the rest of the app shell prerendered.
  return (
    <Suspense fallback={null}>
      <Posts />
    </Suspense>
  );
}

function Posts() {
  const { message } = App.useApp();
  const [view, setView] = useUrlChoice<View>("view", "list", ["calendar"]);
  const [posts, setPosts] = useState<PostRow[] | null>(null);
  const [query, setQuery] = useUrlChoice<string>("q", "");
  const [status, setStatus] = useUrlChoice<StatusFilter>("status", "active", [
    "published",
    "scheduled",
    "failed",
    "closed",
    "all",
  ]);
  const [fanpage, setFanpage] = useUrlChoice<string | null>("fanpage", null);
  const [sort, setSort] = useUrlChoice<Sort>("sort", "latest", ["views"]);
  const { me } = useMe();
  // "Của tôi" or "Cả đội"; null until chosen (the default follows whether the member has a post).
  const [whosePick, setWhose] = useUrlChoice<Whose | null>("whose", null, ["mine", "all"]);

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

  // "Của tôi": the posts the member made, or on a Page they own.
  const isMine = (post: PostRow) => post.created_by_id === me.id || post.fanpage_owner_id === me.id;
  const everyone = posts ?? [];
  const mineCount = everyone.filter(isMine).length;
  const whose = whosePick ?? (mineCount > 0 ? "mine" : "all");
  const all = whose === "all" ? everyone : everyone.filter(isMine);
  const whoseSwitch = <WhoseFilter value={whose} onChange={setWhose} mine={mineCount} all={everyone.length} />;
  const pages = [...new Set(all.map((post) => post.fanpage).filter((name): name is string => Boolean(name)))];
  const words = folded(query.trim());
  const others = (post: PostRow) =>
    (fanpage === null || post.fanpage === fanpage) && (!words || folded(post.title).includes(words));
  const matching = all.filter(others);
  const shown = matching.filter((post) => statusMatches(post, status));
  // The api sends the latest time first; a stable sort keeps that order among posts with the same views.
  if (sort === "views") shown.sort((a, b) => viewsOf(b) - viewsOf(a));
  const filtered = Boolean(words) || status !== "active" || fanpage !== null;
  const counts = Object.fromEntries(
    FILTERS.map(({ value }) => [value, matching.filter((post) => statusMatches(post, value)).length]),
  ) as Record<StatusFilter, number>;
  const groups = byVideo(shown);

  const viewSwitch = (
    <Segmented<View>
      aria-label="Kiểu hiển thị"
      value={view}
      onChange={setView}
      options={[
        { value: "list", icon: <UnorderedListOutlined />, label: "Danh sách" },
        { value: "calendar", icon: <CalendarOutlined />, label: "Lịch" },
      ]}
    />
  );

  if (view === "calendar") {
    return (
      <>
        <PageHeader
          title="Bài đăng"
          description="Các bài đã hẹn lịch và đã đăng theo ngày, giờ Việt Nam. Bấm một bài để mở video."
          actions={viewSwitch}
        />
        {/* "Của tôi / Cả đội" sits above the calendar, as it sits above the list. */}
        <Flex style={{ marginBottom: 12 }}>{whoseSwitch}</Flex>
        <PostCalendar posts={all} />
      </>
    );
  }

  // The filters sit on the list they filter, under the KPIs and suggestions, which they leave as they are.
  const toolbar = (
    <>
      <div role="group" aria-label="Lọc theo trạng thái">
        <Tabs
          activeKey={status}
          onChange={(key) => setStatus(key as StatusFilter)}
          items={FILTERS.map(({ value, label }) => ({ key: value, label: `${label} (${counts[value]})` }))}
          tabBarStyle={{ margin: 0, padding: "0 16px" }}
        />
      </div>
      <Flex wrap gap={12} align="center" style={{ padding: 16 }}>
        <Input
          aria-label="Tìm theo tiêu đề"
          prefix={<SearchOutlined />}
          placeholder="Tìm theo tiêu đề…"
          allowClear
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          style={{ width: 320, maxWidth: "100%" }}
        />
        {whoseSwitch}
        {pages.length > 0 && (
          <FilterSelect
            aria-label="Lọc theo Fanpage"
            placeholder="Mọi Fanpage"
            value={fanpage}
            onChange={(value) => setFanpage(value ?? null)}
            options={pages.map((name) => ({ value: name, label: name }))}
            style={{ width: 220, maxWidth: "100%" }}
          />
        )}
        <Select
          aria-label="Sắp xếp"
          value={sort}
          onChange={setSort}
          options={[
            { value: "latest", label: "Giờ đăng mới nhất" },
            { value: "views", label: "Nhiều view nhất" },
          ]}
          style={{ width: 180, marginLeft: "auto" }}
        />
      </Flex>
    </>
  );

  return (
    <>
      <PageHeader
        title="Bài đăng"
        description="Theo dõi các bài đang đăng, đã hẹn lịch, đã đăng hoặc thất bại trên mọi Fanpage."
        actions={viewSwitch}
      />
      <PostKpis posts={posts} />
      <PostSuggestions posts={posts} />
      <Card styles={{ body: { padding: 0 } }} data-testid="post-list">
        {toolbar}
        {posts === null ? (
          <Flex justify="center" style={{ padding: 48 }}>
            <Spin />
          </Flex>
        ) : groups.length === 0 ? (
          <Empty
            style={{ padding: "32px 0" }}
            description={
              filtered
                ? "Không có bài đăng nào khớp"
                : all.length > 0
                  ? "Không có bài nào đang hoạt động"
                  : whose === "mine"
                    ? "Bạn chưa có bài đăng nào. Chọn “Cả đội” để xem của mọi người."
                    : "Chưa có video nào đã đăng hoặc hẹn lịch"
            }
          />
        ) : (
          <GroupTable groups={groups} onDone={load} />
        )}
      </Card>
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

/** The post's status; a failed one has Facebook's or the app's reason under it. */
function StatusTag({ post }: { post: PostRow }) {
  const shown = SHOWN_STATUS[shownStatus(post)];
  const reason = post.attempt?.state === "failed" ? post.attempt.error : null;
  return (
    <Flex vertical gap={2} align="flex-start">
      <StatusText tone={shown.tone}>{shown.label}</StatusText>
      {reason && (
        <Tooltip title={reason}>
          <Typography.Text type="danger" style={{ fontSize: 12, maxWidth: 200 }} ellipsis data-testid="post-error">
            {reason}
          </Typography.Text>
        </Tooltip>
      )}
    </Flex>
  );
}

/** "Đã đăng 2", one status per kind among the video's posts. */
function StatusSummary({ posts }: { posts: PostRow[] }) {
  const counts = STATUSES.map((value) => [value, posts.filter((post) => shownStatus(post) === value).length] as const);
  return (
    <Flex wrap gap={12}>
      {counts
        .filter(([, number]) => number > 0)
        .map(([value, number]) => (
          <StatusText key={value} tone={SHOWN_STATUS[value].tone}>
            {SHOWN_STATUS[value].label}
            {number > 1 && ` ${number}`}
          </StatusText>
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
  // The table's page is in the address too, back to 1 when a filter changes.
  const tablePage = useUrlPage();
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
            sub={`${group.posts.length} bài đăng, ${pages}`}
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
    <Table<Group>
      rowKey="videoId"
      columns={columns}
      dataSource={groups}
      pagination={{ pageSize: 50, hideOnSinglePage: true, showSizeChanger: false, ...tablePage }}
      scroll={{ x: 900 }}
      onRow={() => ({ "data-testid": "post-group", style: { cursor: "pointer" } }) as React.HTMLAttributes<HTMLElement>}
      expandable={{
        expandRowByClick: true,
        expandedRowRender: (group) => <PostTable posts={group.posts} onDone={onDone} />,
      }}
    />
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
              {post.status === "deleted" ? "Xóa" : "Hủy"}: {post.closed_by ?? "Trên Facebook"},{" "}
              {formatDateTime(post.closed_at)}
            </Typography.Text>
          )}
        </Flex>
      ),
    },
    {
      title: "Trạng thái",
      key: "status",
      width: 220,
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
        <PostActions
          post={post}
          disabled={post.busy}
          onDone={onDone}
          compact
          retryJobId={post.attempt?.state === "failed" ? post.attempt.job_id : null}
        />
      ),
    },
  ];
  return (
    <div data-testid="post-rows">
      <Table<PostRow>
        rowKey="id"
        size="small"
        columns={columns}
        dataSource={posts}
        pagination={false}
        // On a phone the columns scroll inside the card instead of being cut off.
        scroll={{ x: "max-content" }}
      />
    </div>
  );
}
