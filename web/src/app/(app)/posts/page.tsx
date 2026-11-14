"use client";

import VideoActions from "@/components/actions/VideoActions";
import EmptyState from "@/components/EmptyState";
import FilterSelect from "@/components/FilterSelect";
import PageHeader from "@/components/PageHeader";
import PostCalendar from "@/components/PostCalendar";
import { formatCount } from "@/components/PostMetrics";
import PasteLinksModal, { type PasteTarget } from "@/components/posts/PasteLinksModal";
import PlatformCell from "@/components/posts/PlatformCell";
import { formatDayMonth, PLATFORM_LABEL } from "@/components/posts/boardText";
import VideoPostsRow from "@/components/posts/VideoPostsRow";
import VideoTitleCell from "@/components/VideoTitleCell";
import WhoseFilter, { type Whose } from "@/components/WhoseFilter";
import {
  api,
  errorMessage,
  type Board,
  type BoardItem,
  type BoardPlatform,
  type BoardSort,
  type BoardTab,
  type Channels,
  type PostRow,
} from "@/lib/api";
import { useFreshenOnOpen } from "@/lib/freshen";
import { useUrlChoice, useUrlPage, useUrlParam } from "@/lib/urlState";
import {
  CalendarOutlined,
  LinkOutlined,
  ReloadOutlined,
  SearchOutlined,
  UnorderedListOutlined,
} from "@ant-design/icons";
import { App, Button, Card, DatePicker, Flex, Input, Segmented, Select, Spin, Table, Tabs, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import dayjs from "dayjs";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";

const PAGE_SIZE = 50;
const PLATFORMS: BoardPlatform[] = ["facebook", "tiktok", "youtube"];

const TABS: { value: BoardTab; label: string }[] = [
  { value: "unposted", label: "Chưa đăng" },
  { value: "pending_link", label: "Chờ dán link" },
  { value: "scheduled", label: "Đã hẹn lịch" },
  { value: "published", label: "Đã đăng" },
  { value: "failed", label: "Thất bại" },
  { value: "closed", label: "Đã gỡ/hủy" },
  { value: "all", label: "Tất cả" },
];
const TAB_VALUES = TABS.map((tab) => tab.value).filter((value) => value !== "all");

const SORTS: { value: BoardSort; label: string }[] = [
  { value: "latest", label: "Mới nhất" },
  { value: "views", label: "Tổng view" },
  { value: "views_48h", label: "View 48h" },
  { value: "oldest_render", label: "Render cũ nhất" },
];

type View = "list" | "calendar";

/** "Bài đăng": every rendered video and where it stands on Facebook, TikTok and YouTube Shorts, with the links of posts
 * made by hand pasted in; or, as "Lịch" (`?view=calendar`), the Facebook posts by day. */
export default function PostsPage() {
  // The view, tab and filters come from the address, which a static page only knows in the browser.
  return (
    <Suspense fallback={null}>
      <Posts />
    </Suspense>
  );
}

function Posts() {
  const { message } = App.useApp();
  const [view, setView] = useUrlChoice<View>("view", "list", ["calendar"]);
  const [tab, setTab] = useUrlChoice<BoardTab>("tab", "all", TAB_VALUES);
  const [platform, setPlatform] = useUrlChoice<BoardPlatform | null>("platform", null, PLATFORMS);
  const [missing, setMissing] = useUrlChoice<BoardPlatform | null>("missing", null, PLATFORMS);
  const [sort, setSort] = useUrlChoice<BoardSort | null>("sort", null, [
    "latest",
    "views",
    "views_48h",
    "oldest_render",
  ]);
  const [query, setQuery] = useUrlChoice<string>("q", "");
  const [whose, setWhose] = useUrlChoice<Whose>("whose", "all", ["mine"]);
  const [channelParam, setChannelParam] = useUrlParam("channel");
  const [from, setFrom] = useUrlParam("from");
  const [to, setTo] = useUrlParam("to");
  const tablePage = useUrlPage();
  const channels = useMemo(() => (channelParam ? channelParam.split(",") : []), [channelParam]);

  const [board, setBoard] = useState<Board | null>(null);
  const [channelList, setChannelList] = useState<Channels | null>(null);
  const [paste, setPaste] = useState<{ open: boolean; target: PasteTarget | null }>({ open: false, target: null });
  const [calendarPosts, setCalendarPosts] = useState<PostRow[] | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const page = tablePage.current;
  const params = useMemo(() => {
    const search = new URLSearchParams({
      tab,
      owner: whose === "mine" ? "me" : "team",
      cursor: String((page - 1) * PAGE_SIZE),
      limit: String(PAGE_SIZE),
    });
    if (platform) search.set("platform", platform);
    if (missing) search.set("missing_on", missing);
    if (sort) search.set("sort", sort);
    if (query.trim()) search.set("q", query.trim());
    if (from) search.set("date_from", from);
    if (to) search.set("date_to", to);
    for (const key of channels) search.append("channel", key);
    return search.toString();
  }, [tab, whose, page, platform, missing, sort, query, from, to, channels]);

  const load = useCallback(
    () =>
      api<Board>(`/posts/board?${params}`).then(setBoard, (err) => {
        message.error(errorMessage(err));
      }),
    [params, message],
  );
  useEffect(() => {
    if (view === "list") load();
  }, [load, view]);
  useEffect(() => {
    api<Channels>("/channels")
      .then(setChannelList)
      .catch(() => setChannelList(null));
  }, []);
  useEffect(() => {
    if (view === "calendar") {
      api<PostRow[]>("/posts")
        .then(setCalendarPosts)
        .catch((err) => message.error(errorMessage(err)));
    }
  }, [view, message]);
  // Followed Facebook posts not read lately are read again on opening.
  useFreshenOnOpen("/posts/freshen", load);

  const openPaste = useCallback(
    (videoId: number | null, platformOf: BoardPlatform | null) => {
      const item = board?.items.find((row) => row.video.id === videoId);
      setPaste({
        open: true,
        target:
          videoId !== null && platformOf !== null
            ? { videoId, platform: platformOf, videoName: item?.video.name ?? "" }
            : null,
      });
    },
    [board],
  );

  /** "Tải MP4" for TikTok or YouTube: the video waits for its link there, then the file downloads. */
  const download = useCallback(
    async (videoId: number, platformOf: BoardPlatform) => {
      try {
        await api("/posts/pending", "POST", { video_id: videoId, platform: platformOf });
        const link = document.createElement("a");
        link.href = `/api/videos/${videoId}/video.mp4?download=1`;
        link.download = "";
        link.click();
        await load();
      } catch (err) {
        message.error(errorMessage(err));
      }
    },
    [load, message],
  );

  async function refreshViews() {
    setRefreshing(true);
    try {
      const result = await api<{ asked: number }>("/posts/freshen", "POST");
      message.success(
        result.asked > 0 ? `Đang cập nhật view ${result.asked} bài, số liệu sẽ hiện sau ít phút` : "View đã mới",
      );
      setTimeout(load, 5000);
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setRefreshing(false);
    }
  }

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
          description="Các bài Facebook đã hẹn lịch và đã đăng theo ngày, giờ Việt Nam. Bấm một bài để mở video."
          actions={viewSwitch}
        />
        {calendarPosts === null ? <Spin /> : <PostCalendar posts={calendarPosts} />}
      </>
    );
  }

  const channelOptions = channelList
    ? [
        {
          label: "Facebook",
          options: channelList.facebook.map((page) => ({ value: `fanpage:${page.id}`, label: page.name })),
        },
        {
          label: "TikTok",
          options: channelList.tiktok.map((account) => ({ value: `tiktok:${account.id}`, label: account.name })),
        },
        {
          label: "YouTube",
          options: channelList.youtube.map((channel) => ({ value: `youtube:${channel.id}`, label: channel.name })),
        },
      ].filter((group) => group.options.length > 0)
    : [];

  const columns: ColumnsType<BoardItem> = [
    {
      title: "Video",
      key: "video",
      width: 320,
      render: (_, item) => (
        <VideoTitleCell
          id={item.video.id}
          title={item.video.name}
          thumbnailUrl={item.video.thumbnail_url}
          maxWidth={260}
          sub={
            <>
              {item.video.created_by}
              {item.video.rendered_at && ` · render ${formatDayMonth(item.video.rendered_at)}`}
              {item.video.unposted_days !== null && (
                <Typography.Text type="danger" style={{ fontSize: 12 }}>
                  {" "}
                  · chưa đăng {item.video.unposted_days} ngày
                </Typography.Text>
              )}
            </>
          }
        />
      ),
    },
    ...PLATFORMS.map((name) => ({
      title: PLATFORM_LABEL[name],
      key: name,
      width: 200,
      render: (_: unknown, item: BoardItem) => (
        <div onClick={(event) => event.stopPropagation()} data-testid={`cell-${name}`}>
          <PlatformCell
            platform={name}
            cell={item.cells[name]}
            video={item.video}
            onPaste={openPaste}
            onDownload={download}
            onChanged={load}
          />
        </div>
      ),
    })),
    {
      title: "Tổng view",
      key: "total",
      width: 110,
      align: "right",
      render: (_, item) =>
        item.total_views === null ? (
          <Typography.Text type="secondary">—</Typography.Text>
        ) : (
          <Typography.Text strong>{formatCount(item.total_views)}</Typography.Text>
        ),
    },
    {
      title: "",
      key: "actions",
      width: 56,
      render: (_, item) => (
        <VideoActions
          video={{ id: item.video.id, title: item.video.name, topic: item.video.topic, name: item.video.name }}
          onChanged={load}
        />
      ),
    },
  ];

  const filtered =
    tab !== "all" || Boolean(platform || missing || query.trim() || from || to || channels.length) || whose === "mine";

  return (
    <>
      <PageHeader
        title="Bài đăng"
        description="Video đã render và trạng thái đăng trên từng nền tảng. Facebook tự cập nhật qua API, TikTok/YouTube dán link để theo dõi view."
        actions={
          <Flex gap={8} wrap>
            <Button icon={<ReloadOutlined />} loading={refreshing} onClick={refreshViews}>
              Cập nhật view
            </Button>
            <Button icon={<LinkOutlined />} onClick={() => openPaste(null, null)}>
              Dán link bài đã đăng
            </Button>
            {viewSwitch}
          </Flex>
        }
      />
      <Card styles={{ body: { padding: 0 } }} data-testid="post-list">
        <div role="group" aria-label="Lọc theo trạng thái">
          <Tabs
            activeKey={tab}
            onChange={(key) => setTab(key as BoardTab)}
            items={TABS.map(({ value, label }) => ({
              key: value,
              label: `${label}${board ? ` (${board.counts[value]})` : ""}`,
            }))}
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
            style={{ width: 240, maxWidth: "100%" }}
          />
          <WhoseFilter value={whose} onChange={setWhose} />
          <FilterSelect
            aria-label="Nền tảng"
            placeholder="Mọi nền tảng"
            value={platform}
            onChange={(value) => setPlatform((value as BoardPlatform | undefined) ?? null)}
            options={PLATFORMS.map((name) => ({ value: name, label: PLATFORM_LABEL[name] }))}
            style={{ width: 160 }}
          />
          <FilterSelect
            aria-label="Chưa có trên"
            placeholder="Chưa có trên…"
            value={missing}
            onChange={(value) => setMissing((value as BoardPlatform | undefined) ?? null)}
            options={PLATFORMS.map((name) => ({ value: name, label: `Chưa có trên ${PLATFORM_LABEL[name]}` }))}
            style={{ width: 210 }}
          />
          {channelOptions.length > 0 && (
            <Select
              mode="multiple"
              aria-label="Kênh"
              placeholder="Mọi kênh"
              allowClear
              maxTagCount="responsive"
              value={channels}
              onChange={(values: string[]) => setChannelParam(values.length ? values.join(",") : null)}
              options={channelOptions}
              style={{ width: 240, maxWidth: "100%" }}
            />
          )}
          <DatePicker.RangePicker
            aria-label="Ngày đăng"
            format="DD/MM/YYYY"
            placeholder={tab === "unposted" ? ["Render từ", "đến"] : ["Đăng từ", "đến"]}
            value={[from ? dayjs(from) : null, to ? dayjs(to) : null]}
            onChange={(range) => {
              setFrom(range?.[0] ? range[0].format("YYYY-MM-DD") : null);
              setTo(range?.[1] ? range[1].format("YYYY-MM-DD") : null);
            }}
            allowEmpty={[true, true]}
          />
          <Select
            aria-label="Sắp xếp"
            value={sort ?? board?.sort ?? "latest"}
            onChange={setSort}
            options={SORTS}
            style={{ width: 160, marginLeft: "auto" }}
          />
        </Flex>
        {board === null ? (
          <Flex justify="center" style={{ padding: 48 }}>
            <Spin />
          </Flex>
        ) : board.items.length === 0 ? (
          <EmptyState
            description={
              filtered ? "Không có video nào khớp" : "Chưa có video nào đã render. Render một video để thấy nó ở đây."
            }
          />
        ) : (
          <Table<BoardItem>
            rowKey={(item) => item.video.id}
            columns={columns}
            dataSource={board.items}
            pagination={{
              pageSize: PAGE_SIZE,
              total: board.total,
              hideOnSinglePage: true,
              showSizeChanger: false,
              ...tablePage,
            }}
            scroll={{ x: 1180 }}
            onRow={() => ({ "data-testid": "post-group" }) as React.HTMLAttributes<HTMLElement>}
            expandable={{
              expandedRowRender: (item) => (
                <VideoPostsRow videoId={item.video.id} onPaste={openPaste} onDownload={download} onChanged={load} />
              ),
            }}
          />
        )}
      </Card>
      {/* Mounted only while open, so each opening starts empty. */}
      {paste.open && (
        <PasteLinksModal target={paste.target} onClose={() => setPaste({ open: false, target: null })} onSaved={load} />
      )}
    </>
  );
}
