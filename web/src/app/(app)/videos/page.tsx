"use client";
import VideoActions from "@/components/actions/VideoActions";
import VideoCard from "@/components/videoList/VideoCard";
import VideoTable from "@/components/videoList/VideoTable";
import { useVideoColumns } from "@/components/videoList/columns";
import { useVideoView, VideoSearch, ViewToggle } from "@/components/videoList/toolbar";
import {
  BulkActionBar,
  BulkDeleteDialog,
  deleteAction,
  reportBulkDelete,
  useVideoSelection,
} from "@/components/videoList/bulkDelete";

import EmptyState from "@/components/EmptyState";
import type { SelectProps } from "antd";

import FilterSelect from "@/components/FilterSelect";
import FormDrawer from "@/components/FormDrawer";
import { useMe } from "@/components/MeContext";
import GuideButton from "@/components/GuideButton";
import PageHeader from "@/components/PageHeader";
import SampleFields, { type SampleValues } from "@/components/video/SampleFields";
import ImportMp4Modal from "@/components/video/ImportMp4Modal";
import { groupVideoModeLabel, VIDEO_MODES, videoModeLabel } from "@/components/video/videoModes";
import VideoNameEditor from "@/components/VideoNameEditor";
import { videoDetails } from "@/components/videoList/format";
import type { ColumnsType } from "antd/es/table";
import VideoTitleCell from "@/components/VideoTitleCell";
import {
  api,
  errorMessage,
  postForm,
  type ActiveLlm,
  type Knowledge,
  type KnowledgeTopic,
  type Plan,
  type PlanItem,
  type PlanToday,
  type SampleSummary,
  type VideoDetail,
  type VideoMode,
  type VideoRow,
} from "@/lib/api";
import { loadLastChoices, saveLastChoice } from "@/lib/lastChoices";
import { usePolling } from "@/lib/polling";
import { useGuardedClose } from "@/lib/unsaved";
import { useUrlChoice, useUrlPage, useUrlParam } from "@/lib/urlState";
import { VIDEO_STATUS_FILTERS, type VideoStatusFilter } from "@/lib/videoStatus";
import { EditOutlined, FilterOutlined, PlusOutlined, UploadOutlined } from "@ant-design/icons";
import {
  Alert,
  App,
  Button,
  Card,
  Checkbox,
  Col,
  Drawer,
  Flex,
  Form,
  Grid,
  Input,
  Row,
  Segmented,
  Select,
  Spin,
  theme,
  Typography,
} from "antd";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Fragment, Suspense, useCallback, useEffect, useMemo, useState } from "react";

/** While a video is being made the list follows its stages closely; otherwise only teammates' new videos and the
 * numbers change, which a minute's wait shows soon enough. */
const REFRESH_MS = 5000;
const IDLE_REFRESH_MS = 60_000;

type Sort = "new" | "views";
// Where the choice was kept before every list of videos shared one: "grid" was the cards, "list" the table.
const LEGACY_VIEW = { key: "reels-studio.videos-view", values: { grid: "cards", list: "table" } } as const;
const GROUP_KEY = "reels-studio.videos-group";

/** A draft older than this many days waits on someone ("Cần làm"). */
const STALE_DRAFT_DAYS = 2;

type StatusFilter = "all" | "todo" | VideoStatusFilter;

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

/** The status filter: "Cần làm" first, then the choices every video list shares (lib/videoStatus.ts). */
const STATUS_FILTERS: { value: StatusFilter; label: string; match: (row: VideoRow) => boolean }[] = [
  { value: "all", label: "Mọi trạng thái", match: () => true },
  { value: "todo", label: "Cần làm", match: needsWork },
  ...VIDEO_STATUS_FILTERS,
];

export default function VideosPage() {
  // The list's search and filters are in the address, which a static page only knows in the browser.
  return (
    <Suspense fallback={null}>
      <Videos />
    </Suspense>
  );
}

function Videos() {
  const { message } = App.useApp();
  const [rows, setRows] = useState<VideoRow[] | null>(null);
  const [query, setQuery] = useUrlChoice<string>("q", "");
  const [creating, setCreating] = useState(false);
  // The 30-day plan idea "Tạo video" starts from: "Làm tiếp" here, or "Tạo video" on an idea in Kho kiến thức.
  const [startItem, setStartItem] = useState<PlanItem | null>(null);
  // The sample video "Tạo thêm video từ mẫu này" on a video page starts from ("Từ video mẫu", way "reuse").
  const [startSample, setStartSample] = useState<number | null>(null);
  // The topic group "Tạo video" on a group's "Video" tab in Kho kiến thức starts with.
  const [startGroup, setStartGroup] = useState<number | null>(null);
  // A new dialog each time it opens, so it starts from `startItem` and nothing picked before.
  const [opened, setOpened] = useState(0);
  const [today, setToday] = useState<PlanToday[]>([]);
  const router = useRouter();
  const { me } = useMe();
  const [status, setStatus] = useUrlChoice<StatusFilter>(
    "status",
    "all",
    STATUS_FILTERS.map(({ value }) => value),
  );
  // Null is everyone; a name is that member's videos ("Của tôi" is the signed-in member). Undefined until chosen:
  // "Của tôi" once the member has made a video, "Cả đội" before.
  // In the address as `by`, empty for everyone.
  const [by, setBy] = useUrlParam("by");
  const creatorPick = by === null ? undefined : by || null;
  const setCreator = (next: string | null) => setBy(next ?? "");
  const [platform, setPlatform] = useUrlChoice<"all" | "facebook" | "tiktok">("platform", "all", [
    "facebook",
    "tiktok",
  ]);
  // "Kiểu video": every video, or only the finished MP4s sent in whole ("MP4 tải lên").
  const [kind, setKind] = useUrlChoice<"all" | "upload" | "built">("kind", "all", ["upload", "built"]);
  const [importing, setImporting] = useState(false);
  const [fanpage, setFanpage] = useUrlChoice<string | null>("fanpage", null);
  // The topic group shown: the address's, else the one remembered in this browser, as a member usually works on one
  // group at a time. (`group` in the address is the group "Tạo video" opens with, below.)
  const [urlGroup, setUrlGroup] = useUrlParam("topic");
  const [storedGroup, setStoredGroup] = useState<string | null>(() => {
    try {
      return window.localStorage.getItem(GROUP_KEY);
    } catch {
      return null;
    }
  });
  const group = urlGroup ?? storedGroup;
  const [view, chooseView] = useVideoView("cards", LEGACY_VIEW);
  // A phone gets "Bộ lọc" instead of five filters stacked above the list.
  const phone = !(Grid.useBreakpoint().md ?? true);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [sort, setSort] = useUrlChoice<Sort>("sort", "new", ["new", "views"]);

  function startFrom(item: PlanItem | null, sample: number | null = null, group: number | null = null) {
    setStartItem(item);
    setStartSample(sample);
    setStartGroup(group);
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
  // Statuses change in the worker: keep the list current without a reload, often only while a job runs.
  const making = (rows ?? []).some((row) => !["draft", "done", "failed"].includes(row.status));
  usePolling(() => reload(query, true), making ? REFRESH_MS : IDLE_REFRESH_MS);

  useEffect(() => {
    api<PlanToday[]>("/plans/today")
      .then(setToday)
      // Only a suggestion: without it the page works as before.
      .catch(() => setToday([]));
  }, []);

  // /videos?plan_item=<id>: opened from an idea's "Tạo video" in Kho kiến thức.
  // /videos?reference=<id>: "Tạo thêm video từ mẫu này" on a video made from a sample video.
  // /videos?group=<id>: "Tạo video" on a topic group's "Video" tab in Kho kiến thức.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const group = Number(params.get("group"));
    if (group > 0) {
      router.replace("/videos");
      // Opens once the group is known to be there, so a deleted one says so instead of another group.
      api<Knowledge>("/knowledge")
        .then((knowledge) => {
          if (knowledge.topics.some((topic) => topic.id === group)) {
            startFrom(null, null, group);
          } else {
            message.error("Không tìm thấy nhóm chủ đề (có thể đã bị xoá)");
          }
        })
        .catch((err) => message.error(errorMessage(err)));
      return;
    }
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
    setUrlGroup(next);
    setStoredGroup(next);
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

  const creator =
    creatorPick !== undefined ? creatorPick : (rows ?? []).some((row) => row.created_by_id === me.id) ? me.name : null;
  const match = STATUS_FILTERS.find((item) => item.value === status)!.match;
  const kept = (rows ?? []).filter(
    (row) =>
      match(row) &&
      (!creator || (creator === me.name ? row.created_by_id === me.id : row.created_by === creator)) &&
      (platform === "all" || row.platform === platform) &&
      (kind === "all" || (kind === "upload") === (row.mode === "upload")) &&
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
  // Bulk delete: the ticked videos, across pages. Any filter, search or the "Cột"-less views reset it, so nothing
  // out of sight is ever deleted.
  const selection = useVideoSelection();
  const { clear: clearSelection } = selection;
  const [deleting, setDeleting] = useState(false);
  const selectedIds = useMemo(() => [...selection.ids], [selection.ids]);
  useEffect(() => {
    clearSelection();
  }, [query, status, creator, platform, kind, fanpage, group, clearSelection]);
  useEffect(() => {
    if (selection.ids.size === 0 || deleting) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") clearSelection();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selection.ids.size, deleting, clearSelection]);
  const shownIds = shown.map((row) => row.id);
  const videoColumns = useVideoColumns({
    storageKey: "videos-columns",
    versionsOf: (row) => versions.get(row.id) ?? [],
    onChanged: () => void reload(query, true),
    showGroup: true,
  });
  const filtered =
    Boolean(query.trim()) ||
    status !== "all" ||
    Boolean(creator) ||
    platform !== "all" ||
    kind !== "all" ||
    Boolean(fanpage) ||
    Boolean(group);

  // The five filters: in the toolbar on a wide screen, in a drawer behind "Bộ lọc" on a phone.
  const filterControls = (full: boolean) => (
    <>
      <FilterSelect<StatusFilter>
        aria-label="Lọc theo trạng thái"
        placeholder="Mọi trạng thái"
        value={status === "all" ? null : status}
        onChange={(value) => setStatus(value ?? "all")}
        options={STATUS_FILTERS.filter(({ value }) => value !== "all").map(({ value, label }) => ({ value, label }))}
        style={{ width: full ? "100%" : 160 }}
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
        style={{ width: full ? "100%" : 140 }}
      />
      <FilterSelect<"upload" | "built">
        aria-label="Lọc theo kiểu video"
        placeholder="Mọi kiểu video"
        value={kind === "all" ? null : kind}
        onChange={(value) => setKind(value ?? "all")}
        options={[
          { value: "upload", label: "MP4 tải lên" },
          { value: "built", label: "Video dựng trong Studio" },
        ]}
        style={{ width: full ? "100%" : 160 }}
      />
      <FilterSelect<string>
        aria-label="Lọc theo Fanpage"
        placeholder="Mọi Fanpage"
        value={fanpage}
        onChange={(value) => setFanpage(value ?? null)}
        options={pages.map((name) => ({ value: name, label: name }))}
        style={{ width: full ? "100%" : 160 }}
      />
      <FilterSelect<string>
        aria-label="Lọc theo nhóm chủ đề"
        placeholder="Mọi nhóm chủ đề"
        value={group}
        onChange={(value) => chooseGroup(value ?? null)}
        options={groups.map((name) => ({ value: name, label: `${name} (${groupCounts.get(name)})` }))}
        style={{ width: full ? "100%" : 170 }}
      />
      <FilterSelect<string>
        aria-label="Người tạo"
        placeholder="Cả đội"
        value={creator}
        onChange={(value) => setCreator(value ?? null)}
        options={[{ value: me.name, label: "Của tôi" }, ...creators.map((name) => ({ value: name, label: name }))]}
        style={{ width: full ? "100%" : 140 }}
      />
    </>
  );
  // "Cả đội" (an empty `by`) is everyone's videos, no filter.
  const activeFilters = [
    status !== "all",
    platform !== "all",
    kind !== "all",
    fanpage !== null,
    group !== null,
    Boolean(by),
  ].filter(Boolean).length;

  return (
    <>
      <PageHeader
        title="Video"
        actions={
          <>
            <GuideButton screen="videos" />
            <Button icon={<UploadOutlined />} onClick={() => setImporting(true)} data-testid="import-mp4">
              Import MP4
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => startFrom(null)}>
              Tạo video
            </Button>
          </>
        }
      >
        <VideoSearch value={query} onChange={setQuery} width={230} />
        {phone ? (
          <Button icon={<FilterOutlined />} onClick={() => setFiltersOpen(true)}>
            {activeFilters ? `Bộ lọc (${activeFilters})` : "Bộ lọc"}
          </Button>
        ) : (
          filterControls(false)
        )}
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
        <Flex gap={8} style={{ marginLeft: "auto" }}>
          {view === "table" && videoColumns.picker}
          <ViewToggle value={view} onChange={chooseView} />
        </Flex>
      </PageHeader>
      <Drawer
        title="Bộ lọc"
        placement="bottom"
        open={phone && filtersOpen}
        onClose={() => setFiltersOpen(false)}
        size="auto"
        footer={
          <Button type="primary" block onClick={() => setFiltersOpen(false)}>
            Xem {shown.length} video
          </Button>
        }
      >
        <Flex vertical gap={12}>
          {filterControls(true)}
        </Flex>
      </Drawer>
      {week && (
        <Typography.Paragraph type="secondary" data-testid="group-week" style={{ marginTop: -4 }}>
          {group}, tuần này (từ thứ Hai): {week.made} video mới, {week.out} đã đăng, {week.drafts} còn nháp
        </Typography.Paragraph>
      )}
      <PlanBanners today={today} onContinue={startFrom} />
      {selection.ids.size > 0 && shown.length > selection.ids.size && (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          data-testid="bulk-all-strip"
          message={
            <>
              Đã chọn <strong>{selection.ids.size}</strong> video.{" "}
              <Button type="link" size="small" onClick={() => selection.selectAll(shownIds)}>
                Chọn tất cả {shown.length} video khớp bộ lọc
              </Button>
            </>
          }
        />
      )}
      {selection.matchAll && selection.ids.size > 0 && shown.length === selection.ids.size && (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          message={
            <>
              Đã chọn <strong>tất cả {shown.length}</strong> video khớp bộ lọc.{" "}
              <Button type="link" size="small" onClick={clearSelection}>
                Bỏ chọn
              </Button>
            </>
          }
        />
      )}
      {rows === null ? (
        <Flex justify="center" style={{ padding: 48 }}>
          <Spin />
        </Flex>
      ) : shown.length === 0 ? (
        <Card>
          <EmptyState
            description={filtered ? "Không có video nào khớp" : "Chưa có video nào"}
            action={
              !filtered && (
                <Button type="primary" icon={<PlusOutlined />} onClick={() => startFrom(null)}>
                  Làm video đầu tiên
                </Button>
              )
            }
          />
        </Card>
      ) : view === "cards" ? (
        <>
          <Checkbox
            style={{ marginBottom: 12 }}
            data-testid="cards-select-all"
            checked={shown.length > 0 && selection.ids.size >= shown.length}
            indeterminate={selection.ids.size > 0 && selection.ids.size < shown.length}
            onChange={(event) => selection.setMany(shownIds, event.target.checked)}
          >
            Chọn tất cả
          </Checkbox>
          <Row gutter={[16, 16]}>
            {shown.map((row) => (
              <Col key={row.id} xs={24} md={12} xl={8} xxl={6} style={{ display: "flex" }}>
                <VideoCard
                  row={row}
                  versions={versions.get(row.id) ?? []}
                  onChanged={() => reload(query, true)}
                  selection={{
                    checked: selection.ids.has(row.id),
                    anyChecked: selection.ids.size > 0,
                    onChange: (checked, shift) => selection.toggle(row.id, checked, shift, shownIds),
                  }}
                />
              </Col>
            ))}
          </Row>
        </>
      ) : (
        <VideoRows
          rows={shown}
          columns={videoColumns.columns}
          onChanged={() => reload(query, true)}
          selection={selection}
        />
      )}
      {selection.ids.size > 0 && (
        <BulkActionBar
          count={selection.ids.size}
          onClear={clearSelection}
          actions={[deleteAction(() => setDeleting(true))]}
        />
      )}
      {deleting && (
        <BulkDeleteDialog
          ids={selectedIds}
          matchAll={selection.matchAll}
          onClose={() => setDeleting(false)}
          onDone={(result) => {
            setDeleting(false);
            reportBulkDelete(message, result);
            // What was refused stays ticked, so it can be seen and tried again; what went is gone from the set.
            const left = new Set(result.skipped.map((item) => item.id));
            selection.setMany(
              selectedIds.filter((id) => !left.has(id)),
              false,
            );
            void reload(query, true);
          }}
        />
      )}
      <ImportMp4Modal
        open={importing}
        onClose={() => setImporting(false)}
        onDone={(video) => router.push(`/videos/${video.id}`)}
      />
      <NewVideoModal
        key={opened}
        open={creating}
        startItem={startItem}
        startSample={startSample}
        startGroup={startGroup}
        today={today}
        onClose={() => {
          setCreating(false);
          setStartItem(null);
          setStartSample(null);
          setStartGroup(null);
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

/** "Bảng": one row per video, to scan many at once. */
function VideoRows({
  rows,
  columns,
  onChanged,
  selection,
}: {
  rows: VideoRow[];
  columns: ColumnsType<VideoRow>;
  onChanged: () => Promise<void>;
  selection: ReturnType<typeof useVideoSelection>;
}) {
  // The table's page is in the address too, back to 1 when a filter changes.
  const tablePage = useUrlPage();
  // One row's name is open for editing at a time; opening another closes (cancels) it.
  const [renaming, setRenaming] = useState<number | null>(null);
  return (
    <Card styles={{ body: { padding: 0 } }}>
      <VideoTable<VideoRow>
        rows={rows}
        rowKey="id"
        page={tablePage}
        rowHref={(row) => `/videos/${row.id}`}
        rowTestId="video-row"
        tableProps={{
          rowSelection: {
            columnWidth: 40,
            selectedRowKeys: [...selection.ids],
            // The header's tick ticks or unticks the rows of the page shown; a click on a row's tick never opens it.
            onSelectAll: (checked, _selected, changed) =>
              selection.setMany(
                changed.map((row) => row.id),
                checked,
              ),
            onSelect: (row, checked) => selection.toggle(row.id, checked, false, []),
            // The table does Shift-click itself, within the page shown, and gives the rows whose tick it turned.
            onSelectMultiple: (_checked, _selected, changed) => selection.flip(changed.map((row) => row.id)),
          },
        }}
        actions={(row) => <VideoActions video={row} onChanged={onChanged} onRename={() => setRenaming(row.id)} />}
        columns={[
          {
            title: "Video",
            key: "video",
            width: 420,
            render: (_, row) => (
              <VideoTitleCell
                id={row.id}
                title={row.name || row.title || row.topic}
                thumbnailUrl={row.thumbnail_url}
                maxWidth={340}
                editor={
                  <VideoNameEditor
                    videoId={row.id}
                    name={row.name}
                    title={row.title || row.topic}
                    href={`/videos/${row.id}`}
                    maxWidth={340}
                    editing={renaming === row.id}
                    onEditingChange={(on) => setRenaming(on ? row.id : null)}
                    onSaved={onChanged}
                  />
                }
                sub={<Typography.Text type="secondary">{videoDetails(row)}</Typography.Text>}
              />
            ),
          },
          ...columns,
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

/** The create dialog's topic groups: the member's own (their Pages' groups) first, under "Nhóm của tôi". Only the AI's
 * way needs a group's script prompt; a sample video has a default prompt. */
function groupOptions(topics: KnowledgeTopic[], mode: Mode): NonNullable<SelectProps["options"]> {
  const option = (topic: KnowledgeTopic) => ({
    value: topic.id,
    label: topic.script_prompt || mode !== "ai" ? topic.name : `${topic.name} (chưa có prompt)`,
    disabled: !topic.script_prompt && mode === "ai",
  });
  const mine = topics.filter((topic) => topic.mine).map(option);
  const others = topics.filter((topic) => !topic.mine).map(option);
  if (mine.length === 0 || others.length === 0) {
    return [...mine, ...others];
  }
  return [
    { label: "Nhóm của tôi", title: "Nhóm của tôi", options: mine },
    { label: "Nhóm khác", title: "Nhóm khác", options: others },
  ];
}

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
  startGroup,
  today,
  onClose,
}: {
  open: boolean;
  startItem: PlanItem | null;
  startSample: number | null;
  startGroup: number | null;
  today: PlanToday[];
  onClose: () => void;
}) {
  const { message } = App.useApp();
  const { token } = theme.useToken();
  // Under 576 px each label goes above its choice.
  const narrow = !(Grid.useBreakpoint().sm ?? true);
  const router = useRouter();
  const [form] = Form.useForm<NewVideo>();
  // A typed topic or pasted script is not thrown away without asking.
  const close = useGuardedClose(form, open, onClose);
  const [busy, setBusy] = useState(false);
  const [topics, setTopics] = useState<KnowledgeTopic[] | null>(null);
  const [lastGroup, setLastGroup] = useState<number | null>(null);
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
  // "Kiểu video": a slide per scene, or one backdrop under every scene ("Video xuyên suốt"). Starts on the group's
  // own (its "Kiểu video", "Xen kẽ theo ngày" resolved for today); picking one makes it this video's only.
  const [pickedMode, setPickedMode] = useState<VideoMode | null>(null);
  const groupId = Form.useWatch("knowledge_topic_id", form);
  const group = topics?.find((topic) => topic.id === groupId);
  const groupMode = group?.video_mode_today ?? "slides";
  const videoMode = pickedMode ?? groupMode;
  const typed = Form.useWatch("topic", form) ?? "";
  const plan = today.find((group) => group.topic_id === groupId);
  const outsidePlan = !picked && plan && typed.trim() && !plan.topics.some((topic) => sameTopic(topic, typed));
  // The group's whole plan: ideas of the coming days and of the Backlog can be made ahead, to schedule their posts.
  // Only for the member's own groups (of the Pages they own and use); any group can still be picked and typed for.
  const [groupPlan, setGroupPlan] = useState<Plan | null>(null);
  const [allNext, setAllNext] = useState(false);
  const myGroup = topics?.some((topic) => topic.id === groupId && topic.mine) ?? false;
  useEffect(() => {
    if (!open || !groupId || !myGroup) {
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
  }, [open, groupId, myGroup]);
  const sections = myGroup && groupPlan && groupPlan.topic_id === groupId ? ideaSections(groupPlan, allNext) : [];

  function pick(item: PlanItem) {
    setPicked(item);
    form.setFieldsValue({ topic: item.topic });
  }

  useEffect(() => {
    if (open) {
      // The form starts on the member's last group, so wait for it as well (it never fails).
      Promise.all([api<Knowledge>("/knowledge"), loadLastChoices()])
        .then(([data, last]) => {
          setLastGroup(last.knowledge_topic_id);
          setTopics(data.topics);
        })
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
            // Not picked: the api applies the group's switch itself, for the day the video is made.
            video_mode: pickedMode,
          });
      await saveLastChoice({ knowledge_topic_id: values.knowledge_topic_id });
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
    // The writer's line sits above the buttons, on one line of its own, so it never wraps around them.
    <Flex vertical gap={8}>
      <div style={{ textAlign: "start", fontSize: 13 }}>
        {llm && !manual && (
          <Typography.Text type={llm.problem ? "danger" : "secondary"} data-testid="llm-line" style={{ fontSize: 13 }}>
            {llm.problem ? (
              <>
                {llm.problem}.{" "}
                <Link prefetch={false} href="/settings/ai">
                  Mở Cài đặt › AI và nguồn tư liệu
                </Link>
              </>
            ) : (
              <>
                Viết bằng: {llm.name}, {llm.model}.{" "}
                <Link prefetch={false} href="/settings/ai">
                  Đổi trong Cài đặt
                </Link>
              </>
            )}
          </Typography.Text>
        )}
      </div>
      <Flex gap={8} justify="flex-end">
        <Button onClick={close}>Huỷ</Button>
        <Button
          type="primary"
          icon={manual ? <PlusOutlined /> : <EditOutlined />}
          loading={busy}
          disabled={topics === null}
          onClick={() => form.submit()}
        >
          {manual
            ? "Tạo video"
            : sample && sampleMode === "review"
              ? "Phân tích video mẫu"
              : sample && sampleMode === "footage"
                ? "Dựng từ footage"
                : "Viết kịch bản"}
        </Button>
      </Flex>
    </Flex>
  );

  return (
    <FormDrawer
      title="Tạo video"
      open={open}
      onClose={close}
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
            // The idea's or the asked group, else the member's last group, else one of their own groups (their
            // Pages'), else the first with a script prompt.
            knowledge_topic_id:
              startItem?.knowledge_topic_id ??
              startGroup ??
              (
                topics.find((topic) => topic.id === lastGroup && topic.script_prompt) ??
                topics.find((topic) => topic.mine && topic.script_prompt) ??
                topics.find((topic) => topic.script_prompt)
              )?.id,
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
            {/* One row per choice, labels in a column: "Kiểu video", "Cách viết", then the topic group. */}
            <div
              style={{
                display: "grid",
                gridTemplateColumns: narrow ? "1fr" : "90px 1fr",
                gap: "12px 8px",
                alignItems: "center",
              }}
            >
              {!sample && (
                <>
                  <Typography.Text strong style={{ whiteSpace: "nowrap" }}>
                    Kiểu video
                  </Typography.Text>
                  <Segmented
                    aria-label="Kiểu video"
                    value={videoMode}
                    onChange={(value) => setPickedMode(value === groupMode ? null : (value as VideoMode))}
                    options={VIDEO_MODES.map((item) => ({ value: item.value, label: item.label }))}
                    style={{ justifySelf: "start" }}
                  />
                </>
              )}
              <Typography.Text strong style={{ whiteSpace: "nowrap" }}>
                Cách viết
              </Typography.Text>
              <Segmented
                aria-label="Cách viết kịch bản"
                value={mode}
                onChange={(value) => setMode(value as Mode)}
                options={[
                  { value: "ai", label: "AI viết kịch bản" },
                  { value: "sample", label: "Từ video mẫu" },
                  { value: "manual", label: "Tự viết" },
                ]}
                style={{ justifySelf: "start" }}
              />
              <Form.Item
                // Bold and without a colon, like "Kiểu video" and "Cách viết" above it.
                label={<Typography.Text strong>Nhóm chủ đề</Typography.Text>}
                colon={false}
                name="knowledge_topic_id"
                layout="horizontal"
                rules={[{ required: true, message: "Hãy chọn nhóm chủ đề" }]}
                style={{ marginBottom: 0, gridColumn: "1 / -1" }}
              >
                <Select options={groupOptions(topics, mode)} />
              </Form.Item>
            </div>
            {!sample && (
              <Typography.Text type="secondary" style={{ display: "block", marginTop: 8, fontSize: 12 }}>
                {group &&
                  (pickedMode === null
                    ? `Theo kiểu video của nhóm: ${groupVideoModeLabel(group.video_mode)}` +
                      (group.video_mode === "alternate" ? `, hôm nay ${videoModeLabel(groupMode)}` : "") +
                      ". "
                    : `Chỉ video này; nhóm đang theo ${groupVideoModeLabel(group.video_mode)}. `)}
                {VIDEO_MODES.find((item) => item.value === videoMode)?.hint}
              </Typography.Text>
            )}
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
                  label={
                    sample && sampleMode === "footage"
                      ? "Tiêu đề video"
                      : sample
                        ? "Chủ đề hoặc yêu cầu cho video mới"
                        : "Chủ đề"
                  }
                  name="topic"
                  rules={[{ required: true, whitespace: true, message: "Hãy nhập chủ đề" }]}
                  extra={
                    manual
                      ? "Cũng là chữ cảnh tiêu đề, sửa được sau. VD: 6 món *bổ xương* cho người sau 50"
                      : sample && sampleMode === "footage"
                        ? "Là chữ cảnh tiêu đề (cảnh đầu), sửa được sau. VD: Review *yến mạch* Úc sau 1 tháng"
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
