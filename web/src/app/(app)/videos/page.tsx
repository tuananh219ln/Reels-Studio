"use client";

import {
  AppstoreOutlined,
  ClockCircleOutlined,
  EditOutlined,
  EyeOutlined,
  PlusOutlined,
  SearchOutlined,
  UnorderedListOutlined,
} from "@ant-design/icons";
import {
  Alert,
  App,
  Button,
  Card,
  Checkbox,
  Col,
  Empty,
  Flex,
  Form,
  Input,
  Row,
  Segmented,
  Select,
  Spin,
  Table,
  theme,
  Typography,
} from "antd";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Fragment, useCallback, useEffect, useState } from "react";
import { useMe } from "@/components/MeContext";
import VideoStatusTags, { platformName } from "@/components/VideoStatusTags";
import VideoThumbnail from "@/components/VideoThumbnail";
import VideoTitleCell from "@/components/VideoTitleCell";
import {
  api,
  errorMessage,
  formatDateTime,
  postForm,
  type ActiveLlm,
  type Knowledge,
  type KnowledgeTopic,
  type Plan,
  type PlanItem,
  type PlanToday,
  type SampleSummary,
  type VideoDetail,
  type VideoRow,
  type VideoRowPost,
} from "@/lib/api";
import { COLORS } from "@/app/theme";
import StatusText, { type StatusTone } from "@/components/StatusText";
import FilterSelect from "@/components/FilterSelect";
import PageHeader from "@/components/PageHeader";
import { usePolling } from "@/lib/polling";
import { useRememberedView, type View } from "@/lib/view";
import FormDrawer from "@/components/FormDrawer";
import SampleFields, { type SampleValues } from "@/components/video/SampleFields";

const REFRESH_MS = 5000;
/** From this many times its Page's median at 48 hours a post is drawn as a standout (docs/content.md). */
const STANDOUT_TIMES = 10;

type Sort = "new" | "views";
const VIEW_KEY = "reels-studio.videos-view";
const GROUP_KEY = "reels-studio.videos-group";

/** From this many times its Page's median at 48 hours a Facebook video without a TikTok version suggests making one. */
const TIKTOK_NUDGE_TIMES = 3;
/** A draft older than this many days waits on someone ("Cần làm"). */
const STALE_DRAFT_DAYS = 2;

type StatusFilter = "all" | "todo" | "draft" | "working" | "done" | "failed" | "outdated";

/** Out on Facebook (or set for later) or recorded as posted on TikTok. */
const isOut = (row: VideoRow) => row.post !== null || row.tiktok_posted;

/** "Cần làm": what waits on a member, to start the day with: a draft left for days, a failed job, an MP4 behind the
 * edits, or a finished video not posted anywhere yet. */
function needsWork(row: VideoRow): boolean {
  const age = Date.now() - Date.parse(row.created_at);
  return (
    (row.status === "draft" && age > STALE_DRAFT_DAYS * 86_400_000) ||
    row.status === "failed" ||
    row.rerender_failed ||
    row.mp4_outdated ||
    (row.status === "done" && !isOut(row))
  );
}

/** The status filter's groups: a job in any stage counts as "Đang xử lý". */
const STATUS_FILTERS: { value: StatusFilter; label: string; match: (row: VideoRow) => boolean }[] = [
  { value: "all", label: "Mọi trạng thái", match: () => true },
  { value: "todo", label: "Cần làm", match: needsWork },
  { value: "draft", label: "Nháp", match: (row) => row.status === "draft" },
  {
    value: "working",
    label: "Đang xử lý",
    match: (row) => !["draft", "done", "failed"].includes(row.status),
  },
  { value: "done", label: "Xong", match: (row) => row.status === "done" },
  { value: "failed", label: "Lỗi", match: (row) => row.status === "failed" || row.rerender_failed },
  { value: "outdated", label: "MP4 cần render lại", match: (row) => row.mp4_outdated },
];

export default function VideosPage() {
  const { message } = App.useApp();
  const [rows, setRows] = useState<VideoRow[] | null>(null);
  const [query, setQuery] = useState("");
  const [creating, setCreating] = useState(false);
  // The 30-day plan idea "Tạo video" starts from: "Làm tiếp" here, or "Tạo video" on an idea in Kho kiến thức.
  const [startItem, setStartItem] = useState<PlanItem | null>(null);
  // The sample video "Tạo thêm video từ mẫu này" on a video page starts from ("Từ video mẫu", way "reuse").
  const [startSample, setStartSample] = useState<number | null>(null);
  // A new dialog each time it opens, so it starts from `startItem` and nothing picked before.
  const [opened, setOpened] = useState(0);
  const [today, setToday] = useState<PlanToday[]>([]);
  const router = useRouter();
  const { me } = useMe();
  const [status, setStatus] = useState<StatusFilter>("all");
  // Null is everyone; a name is that member's videos ("Của tôi" is the signed-in member).
  const [creator, setCreator] = useState<string | null>(null);
  const [platform, setPlatform] = useState<"all" | "facebook" | "tiktok">("all");
  const [fanpage, setFanpage] = useState<string | null>(null);
  // The topic group shown, remembered in this browser: a member usually works on one group at a time.
  const [group, setGroup] = useState<string | null>(() => {
    try {
      return window.localStorage.getItem(GROUP_KEY);
    } catch {
      return null;
    }
  });
  const [view, chooseView] = useRememberedView(VIEW_KEY);
  const [sort, setSort] = useState<Sort>("new");

  function startFrom(item: PlanItem | null, sample: number | null = null) {
    setStartItem(item);
    setStartSample(sample);
    setOpened((count) => count + 1);
    setCreating(true);
  }

  const reload = useCallback(
    async (q: string, quiet = false) => {
      try {
        setRows(await api<VideoRow[]>(`/videos?q=${encodeURIComponent(q)}`));
      } catch (err) {
        if (!quiet) {
          message.error(errorMessage(err));
        }
      }
    },
    [message],
  );

  useEffect(() => {
    const timer = setTimeout(() => reload(query), 250);
    return () => clearTimeout(timer);
  }, [query, reload]);
  // Statuses change in the worker: keep the list current without a reload.
  usePolling(() => reload(query, true), REFRESH_MS);

  useEffect(() => {
    api<PlanToday[]>("/plans/today")
      .then(setToday)
      // Only a suggestion: without it the page works as before.
      .catch(() => setToday([]));
  }, []);

  // /videos?plan_item=<id>: opened from an idea's "Tạo video" in Kho kiến thức.
  // /videos?reference=<id>: "Tạo thêm video từ mẫu này" on a video made from a sample video.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const sample = Number(params.get("reference"));
    if (sample > 0) {
      router.replace("/videos");
      // Opens once the sample is known to be there, so a deleted one says so instead of an empty choice.
      api<SampleSummary>(`/references/${sample}`)
        .then(() => startFrom(null, sample))
        .catch((err) => message.error(errorMessage(err)));
      return;
    }
    const id = params.get("plan_item");
    if (!id) {
      return;
    }
    router.replace("/videos");
    api<PlanItem>(`/plans/items/${id}`)
      .then((item) => {
        startFrom(item);
      })
      .catch((err) => message.error(errorMessage(err)));
  }, [router, message]);

  function chooseGroup(next: string | null) {
    setGroup(next);
    try {
      if (next) {
        window.localStorage.setItem(GROUP_KEY, next);
      } else {
        window.localStorage.removeItem(GROUP_KEY);
      }
    } catch {
      // A browser that refuses storage just forgets the choice.
    }
  }

  const match = STATUS_FILTERS.find((item) => item.value === status)!.match;
  const kept = (rows ?? []).filter(
    (row) =>
      match(row) &&
      (!creator || row.created_by === creator) &&
      (platform === "all" || row.platform === platform) &&
      (!fanpage || Boolean(row.post?.fanpages.includes(fanpage))) &&
      (!group || row.knowledge_topic === group),
  );
  const groupCounts = new Map<string, number>();
  for (const row of rows ?? []) {
    if (row.knowledge_topic) {
      groupCounts.set(row.knowledge_topic, (groupCounts.get(row.knowledge_topic) ?? 0) + 1);
    }
  }
  const groups = [...groupCounts.keys()].sort((a, b) => a.localeCompare(b, "vi"));
  const week = group ? weekOf((rows ?? []).filter((row) => row.knowledge_topic === group)) : null;
  const creators = [...new Set((rows ?? []).map((row) => row.created_by))]
    .filter((name) => name !== me.name)
    .sort((a, b) => a.localeCompare(b, "vi"));
  const pages = [...new Set((rows ?? []).flatMap((row) => row.post?.fanpages ?? []))].sort((a, b) =>
    a.localeCompare(b, "vi"),
  );
  // The api lists the newest first; "Nhiều view nhất" puts videos without views after, newest first among them.
  const sorted = sort === "views" ? [...kept].sort((a, b) => (b.post?.views ?? -1) - (a.post?.views ?? -1)) : kept;
  const { shown, versions } = withVersions(sorted, platform === "all");
  const filtered =
    Boolean(query.trim()) ||
    status !== "all" ||
    Boolean(creator) ||
    platform !== "all" ||
    Boolean(fanpage) ||
    Boolean(group);

  return (
    <>
      <PageHeader
        title="Video"
        actions={
          <Button type="primary" icon={<PlusOutlined />} onClick={() => startFrom(null)}>
            Tạo video
          </Button>
        }
      >
        <Input
          aria-label="Tìm theo tiêu đề hoặc chủ đề"
          prefix={<SearchOutlined />}
          placeholder="Tìm theo tiêu đề hoặc chủ đề"
          allowClear
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          style={{ width: 230, maxWidth: "100%" }}
        />
        <FilterSelect<StatusFilter>
          aria-label="Lọc theo trạng thái"
          placeholder="Mọi trạng thái"
          value={status === "all" ? null : status}
          onChange={(value) => setStatus(value ?? "all")}
          options={STATUS_FILTERS.filter(({ value }) => value !== "all").map(({ value, label }) => ({ value, label }))}
          style={{ width: 160 }}
        />
        <FilterSelect<"facebook" | "tiktok">
          aria-label="Lọc theo nền tảng"
          placeholder="Mọi nền tảng"
          value={platform === "all" ? null : platform}
          onChange={(value) => setPlatform(value ?? "all")}
          options={[
            { value: "facebook", label: "Facebook" },
            { value: "tiktok", label: "TikTok" },
          ]}
          style={{ width: 140 }}
        />
        <FilterSelect<string>
          aria-label="Lọc theo Fanpage"
          placeholder="Mọi Fanpage"
          value={fanpage}
          onChange={(value) => setFanpage(value ?? null)}
          options={pages.map((name) => ({ value: name, label: name }))}
          style={{ width: 160 }}
        />
        <FilterSelect<string>
          aria-label="Lọc theo nhóm chủ đề"
          placeholder="Mọi nhóm chủ đề"
          value={group}
          onChange={(value) => chooseGroup(value ?? null)}
          options={groups.map((name) => ({ value: name, label: `${name} (${groupCounts.get(name)})` }))}
          style={{ width: 170 }}
        />
        <FilterSelect<string>
          aria-label="Người tạo"
          placeholder="Cả đội"
          value={creator}
          onChange={(value) => setCreator(value ?? null)}
          options={[{ value: me.name, label: "Của tôi" }, ...creators.map((name) => ({ value: name, label: name }))]}
          style={{ width: 140 }}
        />
        <Select<Sort>
          aria-label="Sắp xếp"
          value={sort}
          onChange={setSort}
          options={[
            { value: "new", label: "Mới nhất" },
            { value: "views", label: "Nhiều view nhất" },
          ]}
          style={{ width: 140 }}
        />
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
      {week && (
        <Typography.Paragraph type="secondary" data-testid="group-week" style={{ marginTop: -4 }}>
          {group}, tuần này (từ thứ Hai): {week.made} video mới, {week.out} đã đăng, {week.drafts} còn nháp
        </Typography.Paragraph>
      )}
      <PlanBanners today={today} onContinue={startFrom} />
      {rows === null ? (
        <Flex justify="center" style={{ padding: 48 }}>
          <Spin />
        </Flex>
      ) : shown.length === 0 ? (
        <Card>
          <Empty description={filtered ? "Không có video nào khớp" : "Chưa có video nào"} />
        </Card>
      ) : view === "grid" ? (
        <Row gutter={[16, 16]}>
          {shown.map((row) => (
            <Col key={row.id} xs={24} md={12} xl={8} xxl={6} style={{ display: "flex" }}>
              <VideoCard row={row} versions={versions.get(row.id) ?? []} />
            </Col>
          ))}
        </Row>
      ) : (
        <VideoTable rows={shown} versions={versions} />
      )}
      <NewVideoModal
        key={opened}
        open={creating}
        startItem={startItem}
        startSample={startSample}
        today={today}
        onClose={() => {
          setCreating(false);
          setStartItem(null);
          setStartSample(null);
        }}
      />
    </>
  );
}

/**
 * A TikTok version goes on its source's card instead of a card of its own, so the same video is not listed twice.
 * It keeps its own card when its source is filtered out, and every card shows alone when `together` is off (a
 * platform is chosen).
 */
function withVersions(rows: VideoRow[], together: boolean): { shown: VideoRow[]; versions: Map<number, VideoRow[]> } {
  const versions = new Map<number, VideoRow[]>();
  if (!together) {
    return { shown: rows, versions };
  }
  const listed = new Set(rows.map((row) => row.id));
  const shown: VideoRow[] = [];
  for (const row of rows) {
    if (row.variant_of_id !== null && listed.has(row.variant_of_id)) {
      versions.set(row.variant_of_id, [...(versions.get(row.variant_of_id) ?? []), row]);
    } else {
      shown.push(row);
    }
  }
  return { shown, versions };
}

/** The Monday 00:00 that starts this week in Vietnam time (UTC+7 all year), as a timestamp. */
function weekStart(now = Date.now()): number {
  const OFFSET = 7 * 3_600_000;
  const vn = new Date(now + OFFSET);
  const daysSinceMonday = (vn.getUTCDay() + 6) % 7;
  return Date.UTC(vn.getUTCFullYear(), vn.getUTCMonth(), vn.getUTCDate() - daysSinceMonday) - OFFSET;
}

/** A topic group's videos made this week: how many, how many are out, how many still drafts. */
function weekOf(rows: VideoRow[]): { made: number; out: number; drafts: number } {
  const since = weekStart();
  const made = rows.filter((row) => Date.parse(row.created_at) >= since);
  return {
    made: made.length,
    out: made.filter(isOut).length,
    drafts: made.filter((row) => row.status === "draft").length,
  };
}

/** A small rounded link inside a card, which is itself a link: it opens its own page, not the card's. */
function CardChip({
  href,
  label,
  testId,
  children,
}: {
  href: string;
  label: string;
  testId: string;
  children: React.ReactNode;
}) {
  const router = useRouter();
  const { token } = theme.useToken();
  const open = (event: React.SyntheticEvent) => {
    event.preventDefault();
    event.stopPropagation();
    router.push(href);
  };
  return (
    <span
      role="link"
      tabIndex={0}
      aria-label={label}
      data-testid={testId}
      onClick={open}
      onKeyDown={(event) => event.key === "Enter" && open(event)}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        padding: "0 8px",
        lineHeight: "22px",
        borderRadius: 11,
        border: `1px solid ${token.colorBorderSecondary}`,
        fontSize: 12,
        cursor: "pointer",
        whiteSpace: "nowrap",
      }}
    >
      {children}
    </span>
  );
}

/** "TikTok · Nháp", "TikTok · Đã đăng": the versions on a card or row, each opening its own page. */
function VersionLinks({ versions }: { versions: VideoRow[] }) {
  const { token } = theme.useToken();
  return versions.map((version) => (
    <CardChip
      key={version.id}
      href={`/videos/${version.id}`}
      label={`Mở bản TikTok: ${version.title || version.topic}`}
      testId="video-version"
    >
      <span style={{ color: token.colorTextSecondary }}>TikTok</span>
      <StatusText tone={version.tiktok_posted ? "success" : cardTone(version)}>
        {version.tiktok_posted ? "Đã đăng" : version.status_label}
      </StatusText>
    </CardChip>
  ));
}

/** A Facebook video doing well at 48 hours with no TikTok version yet: the card offers to make one. */
function wantsTikTok(row: VideoRow): boolean {
  return (
    row.platform === "facebook" &&
    !row.has_tiktok_version &&
    row.post?.state === "posted" &&
    row.post.times_median !== null &&
    row.post.times_median >= TIKTOK_NUDGE_TIMES
  );
}

/** "800", "12,4K", "1,2M": how the team says view counts. */
function compactViews(views: number): string {
  const short = (value: number, unit: string) =>
    `${value.toLocaleString("vi-VN", { maximumFractionDigits: value < 100 ? 1 : 0 })}${unit}`;
  if (views >= 1_000_000) return short(views / 1_000_000, "M");
  if (views >= 1_000) return short(views / 1_000, "K");
  return views.toLocaleString("vi-VN");
}

function percent(rate: number): string {
  return `${(rate * 100).toLocaleString("vi-VN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`;
}

/** "03/11 07:00" (or "03/11" without `time`), in Vietnam time; the year only when it is not this one. */
function shortDate(iso: string, time = true): string {
  const full = formatDateTime(iso); // "03/11/2026 07:00"
  const thisYear = formatDateTime(new Date().toISOString()).slice(6, 10);
  const day = full.slice(6, 10) === thisYear ? full.slice(0, 5) : full.slice(0, 10);
  return time ? `${day} ${full.slice(11, 16)}` : day;
}

/** "Sức khỏe, ngày 1, NamTC, 03/11": where it comes from and who made it; the card keeps the date short. */
function madeLine(row: VideoRow, short = false): string {
  return [
    row.knowledge_topic,
    row.plan_day ? `ngày ${row.plan_day}` : null,
    row.created_by,
    short ? shortDate(row.created_at, false) : formatDateTime(row.created_at),
  ]
    .filter(Boolean)
    .join(", ");
}

/** "Vườn nhà, 03/11/2026 07:00 (+1 trang)": the post the card counts, and how many Pages more. */
function postLine(post: VideoRowPost): string {
  const more = post.pages > 1 ? ` (+${post.pages - 1} trang)` : "";
  return `${post.fanpage}, ${post.state === "scheduled" ? "hẹn " : ""}${formatDateTime(post.at)}${more}`;
}

/** The card's status: grey for a draft, blue while a job runs, green once out, amber while waiting. */
function cardTone(row: VideoRow): StatusTone {
  if (row.post?.state === "posted") return "success";
  if (row.post?.state === "scheduled") return "waiting";
  if (row.status === "failed") return "danger";
  if (row.status === "done") return "done";
  if (row.status === "draft") return "idle";
  return "active";
}

/** A card on its side. The thumbnail is left as it is but for its views, in the corner as on a profile grid; the
 * text reads top to bottom: what it is, where it went, how it did, and who made it. */
function VideoCard({ row, versions }: { row: VideoRow; versions: VideoRow[] }) {
  const { token } = theme.useToken();
  const name = row.title || row.topic;
  const post = row.post;
  const standout = post?.times_median != null && post.times_median >= STANDOUT_TIMES;
  // A job's stage or a warning, said in words after the status rather than as more tags.
  const warning = row.rerender_failed
    ? "render lại lỗi"
    : row.mp4_outdated
      ? "MP4 chưa cập nhật theo bản sửa"
      : post && !["done", "draft"].includes(row.status)
        ? row.status_label.toLowerCase()
        : null;
  const small = { fontSize: 12, lineHeight: "18px" } as const;
  return (
    <Link
      prefetch={false}
      href={`/videos/${row.id}`}
      aria-label={name}
      data-testid="video-card"
      style={{ display: "flex", flex: 1, minWidth: 0 }}
    >
      <Card
        hoverable
        style={{ flex: 1, minWidth: 0, borderColor: token.colorBorderSecondary }}
        styles={{ body: { padding: 12, display: "flex", gap: 14 } }}
      >
        <div style={{ position: "relative", width: 92, flex: "none" }}>
          <VideoThumbnail name={name} url={row.thumbnail_url} width={92} plain />
          {post && (post.state === "scheduled" || post.views !== null) && (
            <span
              data-testid="video-card-views"
              style={{
                position: "absolute",
                right: 4,
                bottom: 4,
                display: "inline-flex",
                alignItems: "center",
                gap: 3,
                padding: "0 4px",
                lineHeight: "16px",
                borderRadius: 4,
                background: "rgba(0, 0, 0, 0.72)",
                color: "#fff",
                fontSize: 11,
                fontWeight: 600,
                fontVariantNumeric: "tabular-nums",
                whiteSpace: "nowrap",
              }}
            >
              {post.state === "scheduled" ? (
                <>
                  <ClockCircleOutlined /> {shortDate(post.at).slice(0, 5)}
                </>
              ) : (
                <>
                  <EyeOutlined /> {compactViews(post.views!)}
                </>
              )}
            </span>
          )}
        </div>
        <Flex vertical style={{ minWidth: 0, flex: 1 }}>
          <Typography.Paragraph strong ellipsis={{ rows: 2, tooltip: name }} style={{ margin: 0, lineHeight: "20px" }}>
            {name}
          </Typography.Paragraph>
          {post ? (
            <div style={{ marginTop: 6 }}>
              <Typography.Text type="secondary" style={small} ellipsis={{ tooltip: post.fanpage }}>
                {post.fanpage}
                {post.pages > 1 && ` và ${post.pages - 1} trang khác`}
              </Typography.Text>
              <div>
                <Typography.Text type="secondary" style={small}>
                  {post.state === "scheduled" ? `Hẹn đăng ${shortDate(post.at)}` : `Đăng ${shortDate(post.at)}`}
                </Typography.Text>
              </div>
            </div>
          ) : (
            <Typography.Text type="secondary" style={{ ...small, marginTop: 6 }}>
              Chưa đăng
            </Typography.Text>
          )}
          {post && (post.times_median !== null || post.share_rate !== null) && (
            <Flex gap={12} wrap style={{ marginTop: 6, ...small, fontVariantNumeric: "tabular-nums" }}>
              {post.times_median !== null && (
                <Typography.Text
                  strong={standout}
                  style={{ ...small, color: standout ? COLORS.primary : undefined }}
                  data-testid="video-card-times"
                >
                  {post.times_median.toLocaleString("vi-VN", { maximumFractionDigits: 1 })}× trung vị
                </Typography.Text>
              )}
              {post.share_rate !== null && (
                <Typography.Text
                  type={post.share_met ? "success" : "secondary"}
                  style={small}
                  title={post.share_met ? "Đạt mục tiêu share/view" : "Chưa đạt mục tiêu share/view"}
                >
                  {percent(post.share_rate)} share
                </Typography.Text>
              )}
            </Flex>
          )}
          <Flex justify="space-between" align="flex-end" gap={8} style={{ marginTop: "auto", paddingTop: 10 }}>
            <Flex gap={10} align="center" style={small}>
              <StatusText tone={cardTone(row)} data-testid="video-status">
                {post ? (post.state === "posted" ? "Đã đăng" : "Đã lên lịch") : row.status_label}
              </StatusText>
              <span data-testid="video-platform" style={{ color: token.colorTextSecondary }}>
                {platformName(row)}
              </span>
            </Flex>
            <Typography.Text type="secondary" style={{ ...small, textAlign: "right", flex: "none" }}>
              {row.created_by}, {shortDate(row.created_at, false)}
            </Typography.Text>
          </Flex>
          {(versions.length > 0 || wantsTikTok(row)) && (
            <Flex gap={6} wrap style={{ marginTop: 6 }}>
              <VersionLinks versions={versions} />
              {wantsTikTok(row) && (
                <CardChip
                  href={`/videos/${row.id}?clone=tiktok`}
                  label={`Tạo bản TikTok cho ${name}`}
                  testId="card-make-tiktok"
                >
                  <PlusOutlined style={{ color: COLORS.primary }} />
                  <span style={{ color: COLORS.primary }}>Tạo bản TikTok</span>
                </CardChip>
              )}
            </Flex>
          )}
          {/* Said on a line of its own, so the status line never breaks. */}
          {warning && (
            <Typography.Text style={{ ...small, color: token.colorWarningText }}>
              {warning[0].toUpperCase() + warning.slice(1)}
            </Typography.Text>
          )}
          {(row.knowledge_topic || row.plan_day) && (
            <Typography.Text type="secondary" style={{ ...small, fontSize: 11 }} ellipsis>
              {row.knowledge_topic}
              {row.plan_day ? `, ngày ${row.plan_day} kế hoạch` : ""}
            </Typography.Text>
          )}
        </Flex>
      </Card>
    </Link>
  );
}

/** "Dạng danh sách": one row per video, to scan many at once. */
function VideoTable({ rows, versions }: { rows: VideoRow[]; versions: Map<number, VideoRow[]> }) {
  const router = useRouter();
  return (
    <Card styles={{ body: { padding: 0 } }}>
      <Table<VideoRow>
        rowKey="id"
        dataSource={rows}
        pagination={{ pageSize: 50, hideOnSinglePage: true }}
        scroll={{ x: 1180 }}
        onRow={(row) => ({
          onClick: () => router.push(`/videos/${row.id}`),
          style: { cursor: "pointer" },
          "data-testid": "video-row",
        })}
        columns={[
          {
            title: "Video",
            key: "video",
            render: (_, row) => (
              <VideoTitleCell
                id={row.id}
                title={row.title || row.topic}
                thumbnailUrl={row.thumbnail_url}
                sub={row.title && `Chủ đề: ${row.topic}`}
              />
            ),
          },
          {
            title: "Trạng thái",
            key: "status",
            width: 200,
            render: (_, row) => (
              <Flex vertical gap={4} align="flex-start">
                <VideoStatusTags video={row} />
                {row.post && (
                  <StatusText tone={row.post.state === "posted" ? "success" : "waiting"} style={{ fontSize: 13 }}>
                    {row.post.state === "posted" ? "Đã đăng" : "Đã lên lịch"}
                  </StatusText>
                )}
                <VersionLinks versions={versions.get(row.id) ?? []} />
              </Flex>
            ),
          },
          {
            title: "Đăng",
            key: "post",
            width: 220,
            render: (_, row) =>
              row.post ? postLine(row.post) : <Typography.Text type="secondary">Chưa đăng</Typography.Text>,
          },
          {
            title: "View",
            key: "views",
            width: 100,
            align: "right",
            sorter: (a, b) => (a.post?.views ?? -1) - (b.post?.views ?? -1),
            render: (_, row) =>
              row.post?.views !== null && row.post?.views !== undefined ? (
                <Typography.Text strong>{row.post.views.toLocaleString("vi-VN")}</Typography.Text>
              ) : (
                <Typography.Text type="secondary">—</Typography.Text>
              ),
          },
          {
            title: "48h",
            key: "h48",
            width: 150,
            render: (_, row) => {
              const post = row.post;
              if (!post || (post.times_median === null && post.share_rate === null)) {
                return <Typography.Text type="secondary">—</Typography.Text>;
              }
              const standout = post.times_median !== null && post.times_median >= STANDOUT_TIMES;
              return (
                <Typography.Text strong={standout} style={standout ? { color: COLORS.primary } : undefined}>
                  {post.times_median !== null
                    ? `${post.times_median.toLocaleString("vi-VN", { maximumFractionDigits: 1 })}×`
                    : "chưa đủ dữ liệu"}
                  {post.share_rate !== null && (
                    <Typography.Text type="secondary" style={{ display: "block", fontSize: 12 }}>
                      {percent(post.share_rate)} share
                    </Typography.Text>
                  )}
                </Typography.Text>
              );
            },
          },
          {
            title: "Tạo",
            key: "made",
            width: 260,
            render: (_, row) => <Typography.Text type="secondary">{madeLine(row, true)}</Typography.Text>,
          },
        ]}
      />
    </Card>
  );
}

/** "Hôm nay còn X/Y video" for every topic group whose 30-day plan has a today. */
function PlanBanners({ today, onContinue }: { today: PlanToday[]; onContinue: (item: PlanItem) => void }) {
  return (
    <>
      {today
        .filter((group) => group.ideas.length > 0)
        .map((group) => {
          const left = group.ideas.filter((idea) => idea.status === "idea");
          // Videos made ahead for the coming days, so their posts can be scheduled.
          const ahead =
            group.prepared_through !== null && group.prepared_through > group.day
              ? `, đã làm trước đến ngày ${group.prepared_through}`
              : "";
          return (
            <Alert
              key={group.topic_id}
              type={left.length ? "info" : "success"}
              showIcon
              style={{ marginBottom: 16 }}
              data-testid="plan-banner"
              title={
                left.length
                  ? `Kế hoạch ${group.name}, ngày ${group.day}: hôm nay còn ${left.length}/${group.ideas.length} video`
                  : `Kế hoạch ${group.name}, ngày ${group.day}: đã làm đủ ${group.ideas.length} video hôm nay${ahead}`
              }
              action={
                left.length > 0 && (
                  <Button size="small" type="primary" onClick={() => onContinue(left[0])}>
                    Làm tiếp
                  </Button>
                )
              }
            />
          );
        })}
    </>
  );
}

type NewVideo = { topic: string; knowledge_topic_id: number; script?: string } & Partial<SampleValues>;

/** "Từ video mẫu" ("sample") learns the script from a sample video (components/video/SampleFields). */
type Mode = "ai" | "sample" | "manual";

const SCRIPT_HINT = `Mỗi đoạn (cách nhau một dòng trống) là một cảnh. Dòng bắt đầu bằng “Đọc:” là lời đọc của cảnh.

Vừng đen *giàu canxi*
Đọc: Vừng đen giàu canxi, giúp xương chắc khỏe hơn.

Cá hồi giảm đau khớp
Đọc: Omega 3 trong cá hồi giúp khớp bớt đau.`;

/** How many coming days of ideas the dialog lists before "Xem thêm". */
const NEXT_DAYS = 3;

type IdeaSection = { key: string; title: string; ideas: PlanItem[]; more?: boolean };

/** The ideas still without a video: today's, the coming days', the past days' left undone, then the Backlog. */
function ideaSections(plan: Plan, allNext: boolean): IdeaSection[] {
  const free = plan.items.filter((item) => item.status === "idea");
  const today = plan.today_day;
  const running = today !== null && today >= 1 && today <= 30;
  // Before the start (or without a start date) every day is to come; after the end, every day is past.
  const after = running ? today : today !== null && today > 30 ? 31 : 0;
  const coming = free.filter((item) => item.day !== null && item.day > after);
  const comingDays = [...new Set(coming.map((item) => item.day))];
  const shownDays = allNext ? comingDays : comingDays.slice(0, NEXT_DAYS);
  const sections: IdeaSection[] = [
    { key: "today", title: `Hôm nay, ngày ${today}`, ideas: running ? free.filter((item) => item.day === today) : [] },
    {
      key: "next",
      title: "Ngày tới",
      ideas: coming.filter((item) => shownDays.includes(item.day)),
      more: shownDays.length < comingDays.length,
    },
    { key: "late", title: "Ngày đã qua chưa làm", ideas: free.filter((item) => item.day !== null && item.day < after) },
    { key: "backlog", title: "Backlog", ideas: free.filter((item) => item.day === null) },
  ];
  return sections.filter((section) => section.ideas.length > 0);
}

/** Topics compare like the api's: case, spacing and Unicode form do not count. */
function sameTopic(a: string, b: string): boolean {
  const key = (text: string) => text.normalize("NFC").split(/\s+/).filter(Boolean).join(" ").toLowerCase();
  return key(a) === key(b);
}

function NewVideoModal({
  open,
  startItem,
  startSample,
  today,
  onClose,
}: {
  open: boolean;
  startItem: PlanItem | null;
  startSample: number | null;
  today: PlanToday[];
  onClose: () => void;
}) {
  const { message } = App.useApp();
  const { token } = theme.useToken();
  const router = useRouter();
  const [form] = Form.useForm<NewVideo>();
  const [busy, setBusy] = useState(false);
  const [topics, setTopics] = useState<KnowledgeTopic[] | null>(null);
  const [llm, setLlm] = useState<ActiveLlm | null>(null);
  // The plan idea the video is made from; typing a topic by hand works as before.
  const [picked, setPicked] = useState<PlanItem | null>(startItem);
  // "Tự viết": no AI call, so any group can be used and the script is pasted or left for the video page.
  const [mode, setMode] = useState<Mode>(startSample ? "sample" : "ai");
  const manual = mode === "manual";
  const sample = mode === "sample";
  // The samples learned before, for the way "Dùng mẫu đã học"; asked for once "Từ video mẫu" is chosen.
  const [samples, setSamples] = useState<SampleSummary[] | null>(null);
  const sampleMode = Form.useWatch("sample_mode", form);
  const wantsSamples = open && sample && samples === null;
  useEffect(() => {
    if (!wantsSamples) {
      return;
    }
    let live = true;
    api<SampleSummary[]>("/references")
      .then((list) => live && setSamples(list))
      .catch((err) => {
        if (live) {
          setSamples([]);
          message.error(errorMessage(err));
        }
      });
    return () => {
      live = false;
    };
  }, [wantsSamples, message]);
  // "AI gợi ý hiệu ứng": the same script call also picks each scene's transition, colour, sound and a line of text.
  const [aiEffects, setAiEffects] = useState(false);
  const groupId = Form.useWatch("knowledge_topic_id", form);
  const typed = Form.useWatch("topic", form) ?? "";
  const plan = today.find((group) => group.topic_id === groupId);
  const outsidePlan = !picked && plan && typed.trim() && !plan.topics.some((topic) => sameTopic(topic, typed));
  // The group's whole plan: ideas of the coming days and of the Backlog can be made ahead, to schedule their posts.
  const [groupPlan, setGroupPlan] = useState<Plan | null>(null);
  const [allNext, setAllNext] = useState(false);
  useEffect(() => {
    if (!open || !groupId) {
      return;
    }
    let live = true;
    api<Plan>(`/plans/${groupId}`)
      .then((fresh) => live && setGroupPlan(fresh))
      // Only a suggestion: without it the dialog works as before.
      .catch(() => live && setGroupPlan(null));
    return () => {
      live = false;
    };
  }, [open, groupId]);
  const sections = groupPlan && groupPlan.topic_id === groupId ? ideaSections(groupPlan, allNext) : [];

  function pick(item: PlanItem) {
    setPicked(item);
    form.setFieldsValue({ topic: item.topic });
  }

  useEffect(() => {
    if (open) {
      api<Knowledge>("/knowledge")
        .then((data) => setTopics(data.topics))
        .catch((err) => message.error(errorMessage(err)));
      // Only informative: a failure here leaves the line out and never blocks creating the video.
      api<ActiveLlm>("/settings/llm/active")
        .then(setLlm)
        .catch(() => setLlm(null));
    }
  }, [open, message]);

  async function submit(values: NewVideo) {
    setBusy(true);
    try {
      const video = sample
        ? await fromSample(values)
        : await api<VideoDetail>("/videos", "POST", {
            topic: values.topic,
            knowledge_topic_id: values.knowledge_topic_id,
            plan_item_id: picked?.id,
            mode,
            script: manual ? (values.script ?? "") : "",
            ai_effects: mode === "ai" && aiEffects,
          });
      router.push(`/videos/${video.id}`);
    } catch (err) {
      message.error(errorMessage(err));
      setBusy(false);
    }
  }

  /** "Từ video mẫu": the api stores the link or file and queues the learn job; the video page shows its progress. */
  function fromSample(values: NewVideo): Promise<VideoDetail> {
    const way = values.sample_mode ?? "quick";
    const fields: Record<string, string> = {
      topic: values.topic,
      knowledge_topic_id: String(values.knowledge_topic_id),
      mode: way,
    };
    if (way === "reuse") {
      fields.reference_id = String(values.reference_id ?? "");
      return postForm<VideoDetail>("/references/videos", fields);
    }
    if (values.sample_source === "file") {
      return postForm<VideoDetail>("/references/videos", fields, values.sample_file?.[0]?.originFileObj ?? null);
    }
    fields.url = values.sample_url ?? "";
    return postForm<VideoDetail>("/references/videos", fields);
  }

  // The idea picked from elsewhere ("Tạo video" in Kho kiến thức) stays listed even after it is unpicked.
  const listed = sections.some((section) => section.ideas.some((idea) => idea.id === startItem?.id));
  if (startItem && !listed && startItem.knowledge_topic_id === groupId) {
    sections.unshift({ key: "picked", title: "Ý tưởng đã chọn", ideas: [startItem] });
  }
  // "Từ video mẫu" writes from the sample, not from a plan idea, so the ideas are not listed there.
  const ideas = !sample ? sections.flatMap((section) => section.ideas) : [];
  const footer = (
    <Flex justify="space-between" align="center" gap={12} wrap>
      <div style={{ flex: 1, minWidth: 200, textAlign: "start" }}>
        {llm && !manual && (
          <Typography.Text type={llm.problem ? "danger" : "secondary"} data-testid="llm-line">
            {llm.problem ? (
              <>
                {llm.problem}.{" "}
                <Link prefetch={false} href="/settings/ai">
                  Mở Cài đặt › Mô hình AI
                </Link>
              </>
            ) : (
              <>
                Viết bằng: {llm.name} · {llm.model} (
                <Link prefetch={false} href="/settings/ai">
                  đổi trong Cài đặt
                </Link>
                )
              </>
            )}
          </Typography.Text>
        )}
      </div>
      <Flex gap={8}>
        <Button onClick={onClose}>Huỷ</Button>
        <Button
          type="primary"
          icon={manual ? <PlusOutlined /> : <EditOutlined />}
          loading={busy}
          disabled={topics === null}
          onClick={() => form.submit()}
        >
          {manual ? "Tạo video" : sample && sampleMode === "review" ? "Phân tích video mẫu" : "Viết kịch bản"}
        </Button>
      </Flex>
    </Flex>
  );

  return (
    <FormDrawer
      title="Tạo video"
      open={open}
      onClose={onClose}
      footer={footer}
      width={ideas.length > 0 ? 920 : 640}
      destroyOnHidden
    >
      {topics === null ? (
        <Flex justify="center" style={{ padding: 24 }}>
          <Spin />
        </Flex>
      ) : (
        <Form
          form={form}
          layout="vertical"
          requiredMark={false}
          onFinish={submit}
          initialValues={{
            knowledge_topic_id: startItem?.knowledge_topic_id ?? topics.find((topic) => topic.script_prompt)?.id,
            topic: startItem?.topic,
            sample_mode: startSample ? "reuse" : "quick",
            sample_source: "link",
            reference_id: startSample ?? undefined,
          }}
          onValuesChange={(changed: Partial<NewVideo>) => {
            const group = changed.knowledge_topic_id;
            if (picked && group !== undefined && group !== picked.knowledge_topic_id) {
              setPicked(null);
            }
          }}
        >
          <Typography.Paragraph type="secondary" style={{ marginTop: -4 }}>
            {manual
              ? "Tự viết: không gọi AI, video mở ra với các cảnh để sửa tiếp."
              : sample
                ? "Từ video mẫu: AI xem khung hình và lời thoại của video mẫu, viết kịch bản mới theo khung đó và cắt đoạn của video mẫu làm nền cho từng cảnh."
                : "AI viết kịch bản theo prompt của nhóm chủ đề, rồi video mở ra để duyệt và sửa."}
          </Typography.Paragraph>
          <div
            style={{
              background: token.colorFillQuaternary,
              border: `1px solid ${token.colorBorderSecondary}`,
              borderRadius: token.borderRadiusLG,
              padding: "12px 16px",
              marginBottom: 16,
            }}
          >
            <Flex wrap gap={16} align="center">
              <Flex align="center" gap={8}>
                <Typography.Text type="secondary">Cách viết</Typography.Text>
                <Segmented
                  aria-label="Cách viết kịch bản"
                  value={mode}
                  onChange={(value) => setMode(value as Mode)}
                  options={[
                    { value: "ai", label: "AI viết kịch bản" },
                    { value: "sample", label: "Từ video mẫu" },
                    { value: "manual", label: "Tự viết" },
                  ]}
                />
              </Flex>
              <Form.Item
                label="Nhóm chủ đề"
                name="knowledge_topic_id"
                layout="horizontal"
                rules={[{ required: true, message: "Hãy chọn nhóm chủ đề" }]}
                style={{ marginBottom: 0, flex: 1, minWidth: 260 }}
              >
                <Select
                  options={topics.map((topic) => ({
                    value: topic.id,
                    // Only the AI's way needs the group's script prompt; a sample video has a default prompt.
                    label: topic.script_prompt || mode !== "ai" ? topic.name : `${topic.name} (chưa có prompt)`,
                    disabled: !topic.script_prompt && mode === "ai",
                  }))}
                />
              </Form.Item>
            </Flex>
            <Typography.Text type="secondary" style={{ display: "block", marginTop: 8, fontSize: 12 }}>
              {manual
                ? "Nhóm chủ đề quyết định từ cấm và mặc định của video, sửa trong Kho kiến thức."
                : sample
                  ? "Nhóm chủ đề quyết định prompt học từ video mẫu và từ cấm dùng cho video, sửa trong Kho kiến thức."
                  : "Nhóm chủ đề quyết định prompt và từ cấm dùng cho video, sửa trong Kho kiến thức."}
            </Typography.Text>
          </div>
          <Row gutter={[16, 16]}>
            {ideas.length > 0 && (
              <Col xs={24} md={9}>
                <Flex
                  vertical
                  gap={6}
                  data-testid="plan-suggestions"
                  style={{ maxHeight: 520, overflowY: "auto", paddingRight: 4 }}
                >
                  {ideas.map((idea, index) => {
                    const chosen = picked?.id === idea.id;
                    const section = sections.find((item) => item.ideas[0]?.id === idea.id);
                    return (
                      <Fragment key={idea.id}>
                        {section && (
                          <Flex justify="space-between" align="center" style={{ marginTop: index ? 8 : 0 }}>
                            <Typography.Text type="secondary" style={{ fontSize: 13 }}>
                              {section.title} ({section.ideas.length})
                            </Typography.Text>
                            {section.key === "next" && section.more && (
                              <Button size="small" type="link" onClick={() => setAllNext(true)}>
                                Xem thêm
                              </Button>
                            )}
                          </Flex>
                        )}
                        <div
                          role="button"
                          tabIndex={0}
                          aria-pressed={chosen}
                          onClick={() => (chosen ? setPicked(null) : pick(idea))}
                          onKeyDown={(event) => {
                            if (event.key === "Enter" || event.key === " ") {
                              event.preventDefault();
                              if (chosen) setPicked(null);
                              else pick(idea);
                            }
                          }}
                          style={{
                            display: "flex",
                            gap: 10,
                            alignItems: "flex-start",
                            padding: "8px 10px",
                            cursor: "pointer",
                            borderRadius: token.borderRadius,
                            border: `1px solid ${chosen ? token.colorPrimary : token.colorBorderSecondary}`,
                            background: chosen ? token.colorPrimaryBg : token.colorBgContainer,
                          }}
                        >
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <Typography.Text>{idea.topic}</Typography.Text>
                            <div>
                              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                                {idea.day === null ? "Backlog" : `Ngày ${idea.day}`}
                                {idea.pain_group ? `, ${idea.pain_group}` : ""}
                              </Typography.Text>
                            </div>
                          </div>
                          {chosen && (
                            <Typography.Text style={{ fontSize: 12, color: token.colorPrimary, whiteSpace: "nowrap" }}>
                              Đã chọn
                            </Typography.Text>
                          )}
                        </div>
                      </Fragment>
                    );
                  })}
                </Flex>
              </Col>
            )}
            <Col xs={24} md={ideas.length > 0 ? 15 : 24}>
              <div
                style={{
                  border: ideas.length > 0 ? `1px solid ${token.colorBorderSecondary}` : undefined,
                  borderRadius: token.borderRadiusLG,
                  padding: ideas.length > 0 ? 16 : 0,
                }}
              >
                {sample && <SampleFields samples={samples} />}
                <Form.Item
                  label={sample ? "Chủ đề hoặc yêu cầu cho video mới" : "Chủ đề"}
                  name="topic"
                  rules={[{ required: true, whitespace: true, message: "Hãy nhập chủ đề" }]}
                  extra={
                    manual
                      ? "Cũng là chữ cảnh tiêu đề, sửa được sau. VD: 6 món *bổ xương* cho người sau 50"
                      : sample
                        ? "VD: cùng kiểu này nhưng nói về hạt chia cho người tiểu đường"
                        : "Gõ chủ đề hoặc chọn một ý tưởng bên trái. VD: thực phẩm tốt cho xương khớp người sau 50 tuổi"
                  }
                >
                  <Input.TextArea autoSize={{ minRows: 2, maxRows: 4 }} maxLength={300} />
                </Form.Item>
                {/* "Từ video mẫu" writes in its own call, without the effects. */}
                {mode === "ai" && (
                  <Flex vertical gap={2} style={{ marginBottom: 16 }}>
                    <Checkbox checked={aiEffects} onChange={(event) => setAiEffects(event.target.checked)}>
                      AI gợi ý hiệu ứng
                    </Checkbox>
                    <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                      AI chọn luôn chuyển cảnh, màu, âm thanh và vài dòng chữ nổi bật cho từng cảnh khi viết kịch bản,
                      trong cùng một lượt gọi. Sửa hoặc bỏ được trong xem trước video.
                    </Typography.Text>
                  </Flex>
                )}
                {manual && (
                  <>
                    <Form.Item
                      label="Kịch bản (không bắt buộc)"
                      name="script"
                      extra="Để trống thì video có cảnh tiêu đề và một cảnh trống để viết trên trang video."
                    >
                      <Input.TextArea
                        autoSize={{ minRows: 6, maxRows: 14 }}
                        maxLength={5000}
                        placeholder={SCRIPT_HINT}
                        aria-label="Kịch bản"
                      />
                    </Form.Item>
                    <Alert
                      type="warning"
                      showIcon
                      style={{ marginBottom: 16 }}
                      data-testid="hand-written-note"
                      title="Không gọi AI: không có tiêu đề gợi ý, caption, hashtag, từ khoá ảnh và tự rà soát an toàn. Hãy tự kiểm tra nội dung theo luật an toàn của kênh."
                    />
                  </>
                )}
                {picked && !sample && (
                  <Alert
                    type="info"
                    style={{ marginBottom: 16 }}
                    data-testid="picked-idea"
                    title={`Theo kế hoạch, ${picked.day === null ? "Backlog" : `ngày ${picked.day}`}${picked.pain_group ? `, ${picked.pain_group}` : ""}`}
                    description={
                      <>
                        {picked.pain && <div>Nỗi đau: {picked.pain}</div>}
                        {picked.hook && <div>Hook: {picked.hook}</div>}
                        {!manual && (
                          <div style={{ marginTop: 4, fontSize: 12 }}>
                            Nỗi đau và hook được gửi kèm prompt viết kịch bản.
                          </div>
                        )}
                      </>
                    }
                    action={
                      <Button size="small" type="text" onClick={() => setPicked(null)}>
                        Bỏ chọn
                      </Button>
                    }
                  />
                )}
                {outsidePlan && !sample && (
                  <Alert
                    type="warning"
                    showIcon
                    style={{ marginBottom: 0 }}
                    data-testid="outside-plan"
                    title="Chủ đề này không có trong kế hoạch 30 ngày của nhóm. Vẫn tạo được bình thường."
                  />
                )}
              </div>
            </Col>
          </Row>
        </Form>
      )}
    </FormDrawer>
  );
}
