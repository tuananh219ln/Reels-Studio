"use client";

import EmptyState from "@/components/EmptyState";
import PageHeader from "@/components/PageHeader";
import {
  CheckCircleFilled,
  DownOutlined,
  LinkOutlined,
  LoadingOutlined,
  LockOutlined,
  MoreOutlined,
  ReloadOutlined,
  RightOutlined,
  SearchOutlined,
} from "@ant-design/icons";
import {
  App,
  Avatar,
  Badge,
  Button,
  Card,
  Checkbox,
  Dropdown,
  Flex,
  Grid,
  Input,
  Select,
  Skeleton,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { Suspense, useCallback, useEffect, useState } from "react";
import CompareView from "@/components/competitors/CompareView";
import ScanDetailView from "@/components/competitors/ScanDetailView";
import { ScannerChip, ScannerHelp, type ScannerState } from "@/components/competitors/ScannerStatus";
import type { Competitor } from "@/components/competitors/types";
import { api, errorMessage, formatDateTime } from "@/lib/api";
import { avatarColor, formatAgo, formatCompact, formatFull, plain, thresholdLabel } from "@/lib/competitorFormat";
import { useCompetitorScanner, type CompetitorScan } from "@/lib/competitorScanner";
import { usePolling } from "@/lib/polling";
import { useUrlChoice } from "@/lib/urlState";

const STATUS: Record<
  CompetitorScan["status"],
  { label: string; badge: "default" | "processing" | "warning" | "success" | "error" }
> = {
  queued: { label: "Chờ quét", badge: "default" },
  running: { label: "Đang quét", badge: "processing" },
  partial: { label: "Dừng giữa chừng", badge: "warning" },
  done: { label: "Xong", badge: "success" },
  failed: { label: "Lỗi", badge: "error" },
};

const SORTS = ["views", "median", "videos", "scanned", "name"] as const;
const STATUSES = ["all", "done", "running", "failed"] as const;
const MAX_COMPARE = 5;

export default function CompetitorsPage() {
  return (
    <Suspense fallback={null}>
      <Competitors />
    </Suspense>
  );
}

function Competitors() {
  const { message, modal } = App.useApp();
  const screens = Grid.useBreakpoint();
  const phone = screens.md === false;
  const [competitors, setCompetitors] = useState<Competitor[] | null>(null);
  const [url, setUrl] = useState("");
  const [starting, setStarting] = useState(false);
  const [wakeUp, setWakeUp] = useState(0);
  const [open, setOpen] = useState<number | null>(null);
  const [includeVideos, setIncludeVideos] = useState(false);
  const [picked, setPicked] = useState<number[]>([]);
  const [comparing, setComparing] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  const [search, setSearch] = useUrlChoice<string>("q", "");
  const [typed, setTyped] = useState(search);
  const [sort, setSort] = useUrlChoice<(typeof SORTS)[number]>("sort", "views", SORTS);
  const [status, setStatus] = useUrlChoice<(typeof STATUSES)[number]>("status", "all", STATUSES);

  // The search box follows typing at once; the list and the address wait for a pause of 200 ms.
  useEffect(() => {
    const wait = window.setTimeout(() => setSearch(typed), 200);
    return () => window.clearTimeout(wait);
  }, [typed, setSearch]);

  const load = useCallback(async () => {
    try {
      const data = await api<{ competitors: Competitor[] }>("/competitors");
      setCompetitors(data.competitors);
      setNow(Date.now());
    } catch (err) {
      message.error(errorMessage(err));
    }
  }, [message]);

  useEffect(() => {
    api<{ competitors: Competitor[] }>("/competitors").then(
      (data) => setCompetitors(data.competitors),
      (err) => message.error(errorMessage(err)),
    );
  }, [message]);
  const scanner = useCompetitorScanner(load, wakeUp);
  const waiting = competitors?.some(
    (row) => row.meta_busy || (row.latest_scan && ["queued", "running"].includes(row.latest_scan.status)),
  );
  // Every few seconds only while a scan waits or runs; once a minute otherwise.
  usePolling(load, waiting ? 5_000 : 60_000);

  const state: ScannerState = !scanner.ready ? "offline" : scanner.running ? "busy" : "ready";

  async function start() {
    setStarting(true);
    try {
      const known = new Set((competitors ?? []).map((row) => row.fb_url));
      const scan = await api<CompetitorScan>("/competitors/scans", "POST", { url, include_videos: includeVideos });
      if (known.has(scan.competitor.fb_url)) message.info("Kênh đã có trong danh sách: đã xếp quét lại.");
      setUrl("");
      setWakeUp((value) => value + 1);
      await load();
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setStarting(false);
    }
  }

  async function act(path: string, method: "POST" | "DELETE" | "PATCH", done: string, body?: object) {
    try {
      await api(path, method, body);
      message.success(done);
      setWakeUp((value) => value + 1);
    } catch (err) {
      message.error(errorMessage(err));
    }
    await load();
  }

  const rescan = (row: Competitor) =>
    act("/competitors/scans", "POST", `Đã xếp quét lại ${row.display_name}`, { url: row.fb_url });

  function confirmDelete(rows: Competitor[]) {
    const one = rows.length === 1 ? rows[0].display_name : `${rows.length} kênh`;
    modal.confirm({
      title: `Xóa toàn bộ dữ liệu của ${one}?`,
      content: "Mọi lượt quét và video đã đọc bị xóa hẳn.",
      okText: "Xóa dữ liệu",
      okButtonProps: { danger: true },
      cancelText: "Hủy",
      onOk: async () => {
        for (const row of rows)
          await api(`/competitors/${row.id}`, "DELETE").catch((err) => message.error(errorMessage(err)));
        setPicked((before) => before.filter((id) => !rows.some((row) => row.id === id)));
        await load();
      },
    });
  }

  const shown = (competitors ?? [])
    .filter((row) => {
      const scan = row.latest_scan?.status;
      if (status === "done" && scan !== "done") return false;
      if (status === "running" && scan !== "running" && scan !== "queued") return false;
      if (status === "failed" && scan !== "failed" && scan !== "partial") return false;
      const words = plain(search.trim());
      return !words || plain(`${row.display_name} ${row.handle ?? ""} ${row.fb_id ?? ""}`).includes(words);
    })
    .sort((a, b) => {
      const number = (row: Competitor) =>
        sort === "views"
          ? (row.latest_scan?.total_views ?? -1)
          : sort === "median"
            ? (row.latest_scan?.median_views ?? -1)
            : sort === "videos"
              ? (row.latest_scan?.video_count ?? -1)
              : new Date(row.latest_scan?.finished_at ?? row.latest_scan?.created_at ?? 0).getTime();
      return sort === "name" ? a.display_name.localeCompare(b.display_name, "vi") : number(b) - number(a);
    });

  const scanned = shown.filter((row) => row.latest_scan);
  const lastScan = Math.max(0, ...scanned.map((row) => new Date(row.latest_scan?.finished_at ?? 0).getTime()));
  const kpis = [
    { label: "Kênh", value: formatFull(shown.length) },
    { label: "Video", value: formatFull(scanned.reduce((sum, row) => sum + (row.latest_scan?.video_count ?? 0), 0)) },
    {
      label: "Tổng view",
      value: formatCompact(scanned.reduce((sum, row) => sum + (row.latest_scan?.total_views ?? 0), 0)),
    },
    { label: "Quét gần nhất", value: lastScan ? formatAgo(new Date(lastScan).toISOString(), now) : "—" },
  ];

  // A header click sorts like the "Sắp xếp" box (one direction each: numbers biggest first, names A to Z).
  const sortable = (key: (typeof SORTS)[number]) => ({
    sorter: true,
    sortOrder: sort === key ? (key === "name" ? ("ascend" as const) : ("descend" as const)) : null,
    sortDirections: [key === "name" ? ("ascend" as const) : ("descend" as const)],
    showSorterTooltip: false,
  });

  const columns: ColumnsType<Competitor> = [
    {
      title: "Kênh",
      key: "name",
      ...sortable("name"),
      render: (_, row) => (
        <ChannelCell
          row={row}
          onRename={(name) => act(`/competitors/${row.id}`, "PATCH", "Đã đổi tên kênh", { custom_name: name })}
        />
      ),
    },
    {
      title: "Video",
      key: "videos",
      align: "right",
      width: 130,
      ...sortable("videos"),
      render: (_, row) => {
        const scan = row.latest_scan;
        if (!scan) return "—";
        // A big channel keeps only its videos above the threshold: "23 / 300", with a mark saying from how many views.
        const kept = scan.threshold_applied;
        const text = (
          <span style={{ fontVariantNumeric: "tabular-nums" }}>
            {kept != null
              ? `${formatFull(scan.stored_count)} / ${formatFull(scan.video_count)}`
              : formatFull(scan.video_count)}
          </span>
        );
        if (kept != null) {
          // Two lines like the channel beside it: the counts, then from how many views they were kept.
          return (
            <Tooltip
              title={`${formatFull(scan.stored_count)} video từ ${thresholdLabel(kept)} view được lưu, đã đọc ${formatFull(scan.video_count)} video`}
            >
              <Flex vertical align="end">
                {text}
                <Typography.Text type="secondary" style={{ fontSize: 12, whiteSpace: "nowrap" }}>
                  ≥{thresholdLabel(kept)} view
                </Typography.Text>
              </Flex>
            </Tooltip>
          );
        }
        return scan.videos_count > 0 ? (
          <Tooltip title={`Reels ${scan.reels_count}, Video ${scan.videos_count}`}>{text}</Tooltip>
        ) : (
          text
        );
      },
    },
    {
      title: "Tổng view",
      key: "views",
      align: "right",
      width: 120,
      ...sortable("views"),
      render: (_, row) =>
        row.latest_scan ? (
          <Tooltip title={formatFull(row.latest_scan.total_views)}>
            <span style={{ fontVariantNumeric: "tabular-nums" }}>{formatCompact(row.latest_scan.total_views)}</span>
          </Tooltip>
        ) : (
          "—"
        ),
    },
    {
      title: "Trung vị",
      key: "median",
      align: "right",
      width: 110,
      ...sortable("median"),
      responsive: ["xl"],
      render: (_, row) =>
        row.latest_scan?.median_views != null ? (
          <Tooltip title={formatFull(row.latest_scan.median_views)}>
            <span style={{ fontVariantNumeric: "tabular-nums" }}>{formatCompact(row.latest_scan.median_views)}</span>
          </Tooltip>
        ) : (
          "—"
        ),
    },
    {
      title: "Quét gần nhất",
      key: "scanned",
      width: 190,
      ...sortable("scanned"),
      render: (_, row) => (
        <ScanCell
          row={row}
          now={now}
          progress={scanner.running?.scan.id === row.latest_scan?.id ? scanner.running : null}
        />
      ),
    },
    {
      title: "Thao tác",
      key: "actions",
      width: 96,
      align: "center",
      render: (_, row) => <Actions row={row} onRescan={rescan} onAct={act} onDelete={() => confirmDelete([row])} />,
    },
  ];

  const mine = (competitors ?? []).filter((row) => picked.includes(row.id) && row.is_mine);
  const pickedRows = (competitors ?? []).filter((row) => picked.includes(row.id));
  const canCompare = picked.length >= 2 && picked.length <= MAX_COMPARE;

  return (
    <>
      <PageHeader
        title="Phân tích đối thủ"
        actions={<ScannerChip state={state} account={scanner.account} scanning={scanner.running ? 1 : 0} />}
      >
        <Flex vertical gap={12}>
          <Flex wrap gap={12} align="center">
            <Space.Compact style={{ maxWidth: 640, width: "100%", flex: "1 1 360px" }}>
              <Input
                type="url"
                placeholder="Dán link Facebook của đối thủ, ví dụ facebook.com/tenpage"
                aria-label="Link Facebook của đối thủ"
                value={url}
                onChange={(event) => setUrl(event.target.value)}
                onPressEnter={() => url.trim() && state !== "offline" && start()}
              />
              <Button
                type="primary"
                icon={<SearchOutlined />}
                loading={starting}
                disabled={!url.trim() || state === "offline"}
                onClick={start}
              >
                Quét
              </Button>
            </Space.Compact>
            <Checkbox checked={includeVideos} onChange={(event) => setIncludeVideos(event.target.checked)}>
              Kèm tab Video
            </Checkbox>
          </Flex>
          {state === "offline" && (
            <ScannerHelp version={scanner.version} current={scanner.current} account={scanner.account} />
          )}
        </Flex>
      </PageHeader>

      <div
        data-testid="competitor-kpis"
        style={{
          display: "grid",
          gap: 12,
          gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))",
          marginBottom: 12,
        }}
      >
        {kpis.map((kpi) => (
          <Card key={kpi.label} size="small">
            <Typography.Text type="secondary">{kpi.label}</Typography.Text>
            <div style={{ fontSize: 20, fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>
              {competitors === null ? <Skeleton.Input active size="small" /> : kpi.value}
            </div>
          </Card>
        ))}
      </div>

      <Flex wrap gap={8} style={{ marginBottom: 12 }}>
        <Input
          allowClear
          prefix={<SearchOutlined />}
          placeholder="Tìm kênh theo tên, handle hoặc ID…"
          aria-label="Tìm kênh"
          style={{ width: 280, maxWidth: "100%" }}
          value={typed}
          onChange={(event) => setTyped(event.target.value)}
        />
        <Select
          aria-label="Sắp xếp"
          value={sort}
          onChange={setSort}
          style={{ width: 190 }}
          options={[
            { value: "views", label: "Sắp xếp: Tổng view" },
            { value: "median", label: "Sắp xếp: Trung vị" },
            { value: "videos", label: "Sắp xếp: Số video" },
            { value: "scanned", label: "Sắp xếp: Quét gần nhất" },
            { value: "name", label: "Sắp xếp: Tên" },
          ]}
        />
        <Select
          aria-label="Lọc trạng thái"
          value={status}
          onChange={setStatus}
          style={{ width: 220 }}
          options={[
            { value: "all", label: "Tất cả trạng thái" },
            { value: "done", label: "Xong" },
            { value: "running", label: "Đang quét" },
            { value: "failed", label: "Lỗi hoặc dừng giữa chừng" },
          ]}
        />
      </Flex>

      {phone ? (
        <PhoneList
          rows={shown}
          loading={competitors === null}
          now={now}
          picked={picked}
          onPick={setPicked}
          open={open}
          onOpen={setOpen}
          empty={competitors?.length ? "filtered" : "none"}
          onClear={() => {
            setTyped("");
            setStatus("all");
          }}
          onRescan={rescan}
          onAct={act}
          onDelete={(row) => confirmDelete([row])}
        />
      ) : (
        <Card styles={{ body: { padding: 0 } }}>
          <Table<Competitor>
            rowKey="id"
            columns={columns}
            rowSelection={{
              selectedRowKeys: picked,
              onChange: (keys) => setPicked(keys.map(Number)),
              getCheckboxProps: (row) => ({ "aria-label": `Chọn ${row.display_name}` }),
            }}
            dataSource={shown}
            loading={competitors === null}
            pagination={false}
            scroll={{ x: 820 }}
            onChange={(_pagination, _filters, sorter) => {
              const one = Array.isArray(sorter) ? sorter[0] : sorter;
              const key = SORTS.find((value) => value === one?.columnKey);
              // A second click on the sorted column would clear it: the list keeps its order instead.
              if (key && one?.order) setSort(key);
            }}
            rowClassName={(row) => (row.id === open ? "competitor-row competitor-row--open" : "competitor-row")}
            onRow={(row) => ({
              onClick: (event) => {
                // A button, link, box or the name being edited keeps its own click.
                if (
                  (event.target as HTMLElement).closest(
                    "a, button, input, textarea, label, .ant-checkbox, .ant-typography-edit-content",
                  )
                )
                  return;
                if (row.latest_scan?.video_count) setOpen(open === row.id ? null : row.id);
              },
            })}
            expandable={{
              expandedRowKeys: open ? [open] : [],
              expandIconColumnIndex: 7,
              expandIcon: ({ expanded, onExpand, record }) =>
                record.latest_scan?.video_count ? (
                  <Button
                    type="text"
                    size="small"
                    aria-label={`${expanded ? "Thu gọn" : "Mở rộng"} ${record.display_name}`}
                    aria-expanded={expanded}
                    icon={expanded ? <DownOutlined /> : <RightOutlined />}
                    onClick={(event) => onExpand(record, event)}
                  />
                ) : null,
              onExpand: (expanded, row) => setOpen(expanded ? row.id : null),
              expandedRowRender: (row) =>
                row.latest_scan && <ScanDetailView competitorId={row.id} scanId={row.latest_scan.id} />,
            }}
            locale={{
              emptyText: competitors?.length ? (
                <EmptyState
                  description={`Không có kênh khớp${search ? ` “${search}”` : " bộ lọc"}`}
                  action={
                    <Button
                      onClick={() => {
                        setTyped("");
                        setStatus("all");
                      }}
                    >
                      Xóa bộ lọc
                    </Button>
                  }
                />
              ) : (
                <EmptyState description="Dán link trang Facebook của đối thủ để bắt đầu" />
              ),
            }}
          />
        </Card>
      )}

      {picked.length > 0 && (
        <Card
          size="small"
          role="region"
          aria-label="Thao tác với kênh đã chọn"
          style={{
            position: "fixed",
            bottom: 24,
            left: "50%",
            transform: "translateX(-50%)",
            zIndex: 20,
            maxWidth: "calc(100vw - 32px)",
            boxShadow: "0 6px 24px rgba(0,0,0,0.18)",
          }}
        >
          <Flex wrap gap={8} align="center" justify="center">
            <Typography.Text>Đã chọn {picked.length} kênh</Typography.Text>
            <Tooltip
              title={
                canCompare
                  ? ""
                  : picked.length > MAX_COMPARE
                    ? `So sánh tối đa ${MAX_COMPARE} kênh`
                    : "Chọn từ 2 kênh để so sánh"
              }
            >
              <span>
                <Button disabled={!canCompare} onClick={() => setComparing(true)}>
                  So sánh
                </Button>
              </span>
            </Tooltip>
            <Tooltip title={mine.length ? "" : "Chỉ quét lại được kênh do bạn quét"}>
              <span>
                <Button
                  disabled={!mine.length}
                  onClick={async () => {
                    for (const row of mine)
                      await api("/competitors/scans", "POST", { url: row.fb_url }).catch((err) =>
                        message.error(errorMessage(err)),
                      );
                    setWakeUp((value) => value + 1);
                    await load();
                  }}
                >
                  Quét lại
                </Button>
              </span>
            </Tooltip>
            <Tooltip title={mine.length ? "" : "Chỉ xóa được kênh do bạn quét"}>
              <span>
                <Button danger disabled={!mine.length} onClick={() => confirmDelete(mine)}>
                  Xóa dữ liệu
                </Button>
              </span>
            </Tooltip>
            <Button type="text" onClick={() => setPicked([])}>
              Bỏ chọn
            </Button>
          </Flex>
        </Card>
      )}
      {comparing && pickedRows.length >= 2 && (
        <CompareView ids={pickedRows.map((row) => row.id).slice(0, MAX_COMPARE)} onClose={() => setComparing(false)} />
      )}
    </>
  );
}

/** Avatar (the copy kept by the api, else the initial on a colour from the id), the name, and what else is known. */
function ChannelCell({ row, onRename }: { row: Competitor; onRename: (name: string) => void }) {
  const seed = row.fb_id ?? row.handle ?? String(row.id);
  const second = row.handle ? `@${row.handle}` : `ID …${(row.fb_id ?? "").slice(-6)}`;
  return (
    <Flex gap={12} align="center" style={{ minWidth: 0 }}>
      <Avatar size={36} src={row.avatar_url ?? undefined} style={{ background: avatarColor(seed), flex: "none" }}>
        {row.display_name.slice(0, 1).toUpperCase()}
      </Avatar>
      <Flex vertical style={{ minWidth: 0 }}>
        <Flex gap={6} align="center" style={{ minWidth: 0 }}>
          <Typography.Text
            strong
            ellipsis={{ tooltip: row.display_name }}
            editable={
              row.is_mine
                ? { onChange: onRename, tooltip: "Đổi tên kênh", triggerType: ["icon"], maxLength: 200 }
                : false
            }
            style={{ maxWidth: 280 }}
          >
            {row.display_name}
          </Typography.Text>
          {row.is_verified && (
            <Tooltip title="Đã xác minh">
              <CheckCircleFilled aria-label="Đã xác minh" style={{ color: "var(--ant-color-primary)" }} />
            </Tooltip>
          )}
          <Tooltip title="Mở tab Reels">
            <Typography.Link
              href={row.reels_url}
              target="_blank"
              rel="noreferrer"
              aria-label={`Mở tab Reels của ${row.display_name}`}
            >
              <LinkOutlined />
            </Typography.Link>
          </Tooltip>
          {!row.has_meta && !row.custom_name && (
            <Tooltip title="Quét lại hoặc chọn Cập nhật thông tin kênh để lấy tên và ảnh">
              <Tag style={{ marginInlineEnd: 0 }}>Chưa có tên</Tag>
            </Tooltip>
          )}
        </Flex>
        <Flex gap={8}>
          <Typography.Text type="secondary" ellipsis style={{ maxWidth: 200 }}>
            {second}
          </Typography.Text>
          {row.followers != null && (
            <Typography.Text type="secondary" style={{ whiteSpace: "nowrap" }}>
              {formatCompact(row.followers)} theo dõi
            </Typography.Text>
          )}
        </Flex>
      </Flex>
    </Flex>
  );
}

function ScanCell({
  row,
  now,
  progress,
}: {
  row: Competitor;
  now: number;
  progress: { found: number; details?: { read: number; of: number } } | null;
}) {
  const scan = row.latest_scan;
  if (!scan) return row.meta_busy ? <Badge status="processing" text="Đang lấy thông tin" /> : "—";
  const at = scan.finished_at ?? scan.started_at ?? scan.created_at;
  const who = row.is_mine ? "Bạn" : row.owner.name;
  const info = STATUS[scan.status];
  const live = scan.status === "running" || scan.status === "queued";
  return (
    <Tooltip
      title={
        <>
          {at ? formatDateTime(at) : ""}
          <br />
          Người quét: {who}
          {scan.error && (
            <>
              <br />
              {scan.error}
            </>
          )}
        </>
      }
    >
      <Flex vertical gap={2}>
        <Badge status={info.badge} text={info.label} />
        {live ? (
          <Typography.Text type="secondary" style={{ fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" }}>
            <LoadingOutlined aria-hidden />{" "}
            {progress?.details
              ? `Top video ${progress.details.read}/${progress.details.of}`
              : `${formatFull(progress ? progress.found : scan.videos_found)}/${formatFull(scan.max_videos)} video`}
          </Typography.Text>
        ) : (
          at && <Typography.Text type="secondary">{formatAgo(at, now)}</Typography.Text>
        )}
      </Flex>
    </Tooltip>
  );
}

type Act = (path: string, method: "POST" | "DELETE" | "PATCH", done: string, body?: object) => Promise<void>;

/** Re-scan, and a menu of the rest; a channel another member scans can only be read. */
function Actions({
  row,
  onRescan,
  onAct,
  onDelete,
}: {
  row: Competitor;
  onRescan: (row: Competitor) => void;
  onAct: Act;
  onDelete: () => void;
}) {
  const { message } = App.useApp();
  const scan = row.latest_scan;
  const busy = scan && ["queued", "running"].includes(scan.status);
  if (!row.is_mine) {
    return (
      <Tooltip title={`Chỉ ${row.owner.name} quét lại, đổi tên hoặc xóa được`}>
        <LockOutlined aria-label={`Chỉ ${row.owner.name} thao tác được`} style={{ opacity: 0.5 }} />
      </Tooltip>
    );
  }
  return (
    <Space size={4}>
      <Tooltip title="Quét lại">
        <Button
          type="text"
          icon={<ReloadOutlined />}
          disabled={Boolean(busy)}
          aria-label={`Quét lại ${row.display_name}`}
          onClick={() => onRescan(row)}
        />
      </Tooltip>
      <Dropdown
        trigger={["click"]}
        menu={{
          items: [
            { key: "meta", label: "Cập nhật thông tin kênh", disabled: row.meta_busy },
            ...(scan && ["partial", "failed"].includes(scan.status) ? [{ key: "resume", label: "Tiếp tục quét" }] : []),
            ...(row.custom_name ? [{ key: "restore", label: "Khôi phục tên gốc" }] : []),
            {
              key: "threshold",
              label: "Ngưỡng video",
              children: (
                [
                  ["auto", "Tự động (theo Cài đặt)"],
                  ["all", "Lấy tất cả"],
                  ["100k", "≥100K"],
                  ["1m", "≥1M"],
                ] as const
              ).map(([mode, label]) => ({
                key: `threshold:${mode}`,
                label: row.video_threshold_mode === mode ? `${label} (đang chọn)` : label,
              })),
            },
            { key: "open", label: "Mở trên Facebook" },
            { key: "copy", label: "Sao chép link" },
            { type: "divider" },
            { key: "delete", label: "Xóa dữ liệu", danger: true },
          ],
          onClick: ({ key }) => {
            if (key.startsWith("threshold:"))
              void onAct(`/competitors/${row.id}`, "PATCH", "Ngưỡng video áp dụng từ lượt quét sau", {
                video_threshold_mode: key.slice("threshold:".length),
              });
            else if (key === "meta")
              void onAct(`/competitors/${row.id}/refresh-meta`, "POST", "Đã xếp lượt lấy thông tin kênh");
            else if (key === "resume" && scan)
              void onAct(`/competitors/scans/${scan.id}/resume`, "POST", "Đã xếp lại lượt quét");
            else if (key === "restore")
              void onAct(`/competitors/${row.id}`, "PATCH", "Đã khôi phục tên gốc", { custom_name: null });
            else if (key === "open") window.open(row.fb_url, "_blank", "noopener,noreferrer");
            else if (key === "copy")
              void navigator.clipboard?.writeText(row.fb_url).then(() => message.success("Đã sao chép link"));
            else if (key === "delete") onDelete();
          },
        }}
      >
        <Button type="text" icon={<MoreOutlined />} aria-label={`Thêm thao tác với ${row.display_name}`} />
      </Dropdown>
    </Space>
  );
}

/** Under 768 px the table gives way to cards: avatar, name and menu, then the numbers in one line. */
function PhoneList({
  rows,
  loading,
  now,
  picked,
  onPick,
  open,
  onOpen,
  empty,
  onClear,
  onRescan,
  onAct,
  onDelete,
}: {
  rows: Competitor[];
  loading: boolean;
  now: number;
  picked: number[];
  onPick: (ids: number[]) => void;
  open: number | null;
  onOpen: (id: number | null) => void;
  empty: "none" | "filtered";
  onClear: () => void;
  onRescan: (row: Competitor) => void;
  onAct: Act;
  onDelete: (row: Competitor) => void;
}) {
  if (loading) return <Skeleton active />;
  if (!rows.length) {
    return empty === "filtered" ? (
      <EmptyState description="Không có kênh khớp bộ lọc" action={<Button onClick={onClear}>Xóa bộ lọc</Button>} />
    ) : (
      <EmptyState description="Dán link trang Facebook của đối thủ để bắt đầu" />
    );
  }
  return (
    <Flex vertical gap={8}>
      {rows.map((row) => {
        const scan = row.latest_scan;
        const at = scan?.finished_at ?? scan?.created_at;
        const line = scan
          ? `${formatFull(scan.video_count)} video, ${formatCompact(scan.total_views)} view${at ? `, ${formatAgo(at, now)}` : ""}`
          : "Chưa quét";
        return (
          <Card key={row.id} size="small">
            <Flex gap={8} align="start">
              <Checkbox
                aria-label={`Chọn ${row.display_name}`}
                checked={picked.includes(row.id)}
                onChange={(event) =>
                  onPick(event.target.checked ? [...picked, row.id] : picked.filter((id) => id !== row.id))
                }
              />
              <Flex vertical gap={4} style={{ flex: 1, minWidth: 0 }}>
                <Flex justify="space-between" align="center" gap={8}>
                  <ChannelCell
                    row={row}
                    onRename={(name) =>
                      void onAct(`/competitors/${row.id}`, "PATCH", "Đã đổi tên kênh", { custom_name: name })
                    }
                  />
                  <Actions row={row} onRescan={onRescan} onAct={onAct} onDelete={() => onDelete(row)} />
                </Flex>
                <Typography.Text type="secondary">{line}</Typography.Text>
                {scan?.video_count ? (
                  <Button
                    size="small"
                    onClick={() => onOpen(open === row.id ? null : row.id)}
                    aria-expanded={open === row.id}
                  >
                    {open === row.id ? "Thu gọn" : "Xem chi tiết"}
                  </Button>
                ) : null}
                {open === row.id && scan && <ScanDetailView competitorId={row.id} scanId={scan.id} />}
              </Flex>
            </Flex>
          </Card>
        );
      })}
    </Flex>
  );
}
