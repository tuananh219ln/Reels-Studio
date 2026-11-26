"use client";

import { COLORS } from "@/app/theme";
import ColumnPicker, { useRememberedColumns } from "@/components/ColumnPicker";
import EmptyState from "@/components/EmptyState";
import PageHeader from "@/components/PageHeader";
import { formatDuration, formatNumber, formatSeconds } from "@/components/page/Figures";
import {
  api,
  errorMessage,
  type DashboardFigure,
  type Fanpage,
  type Stats,
  type StatsFacebookRow,
  type StatsInstagramRow,
  type StatsSeries,
} from "@/lib/api";
import { percentFormat } from "@/lib/format";
import { useUrlChoice } from "@/lib/urlState";
import { DownloadOutlined } from "@ant-design/icons";
import { App, Button, Card, Col, Flex, Row, Segmented, Select, Table, Tag, Tooltip, Typography } from "antd";
import Link from "next/link";
import { Suspense, useEffect, useMemo, useState } from "react";

const COLUMNS_KEY = { facebook: "stats-columns-facebook", instagram: "stats-columns-instagram" } as const;
const PERIODS = ["7", "28", "90"] as const;
const PLATFORMS = ["facebook", "instagram", "tiktok"] as const;
type Platform = (typeof PLATFORMS)[number];
const LINES = ["#C2410C", "#3B6A9A", "#2F7D4F", "#8A5BB5", "#B58A1B", "#1F8A8A", "#B5446E", "#5F6670"];

type Row = StatsFacebookRow | StatsInstagramRow;
type Cell = {
  key: string;
  title: string;
  group: string;
  tip?: string;
  numeric?: boolean;
  /** What the CSV file gets. */
  value: (row: never) => string | number | null;
  render: (row: never) => React.ReactNode;
};

const dash = <Typography.Text type="secondary">—</Typography.Text>;

function figure(pick: (row: never) => DashboardFigure | undefined) {
  return {
    numeric: true,
    value: (row: never) => pick(row)?.value ?? null,
    render: (row: never) => formatNumber(pick(row)?.value ?? null),
  };
}

const TIMES_LABEL = { measuring: "Đang đo", pass: "Đạt cửa đo", hold: "Chưa đạt", change: "Đổi hook và trụ" } as const;

function hours(row: StatsFacebookRow | StatsInstagramRow): string | null {
  const best = row.best_times;
  if (!best || !best.enough || best.hours.length === 0) return null;
  return best.hours.map((one) => `${String(one.hour).padStart(2, "0")}:00`).join(", ");
}

const FACEBOOK_CELLS: Cell[] = [
  {
    key: "views",
    title: "Lượt xem",
    group: "Hiệu quả",
    tip: "Facebook, cả Page trong khoảng ngày đã chọn",
    ...figure((row: StatsFacebookRow) => row.totals.views),
  },
  {
    key: "previous",
    title: "So kỳ trước",
    group: "Hiệu quả",
    tip: "Lượt xem của kỳ liền trước, số tuyệt đối (không tính % tăng)",
    ...figure((row: StatsFacebookRow) => ({ value: row.totals.views.previous, previous: null, change: null })),
  },
  {
    key: "reach",
    title: "Tiếp cận",
    group: "Hiệu quả",
    tip: "Số người đã thấy nội dung của Page (Facebook không trả “người xem” hay “hiển thị” riêng)",
    ...figure((row: StatsFacebookRow) => row.totals.reach),
  },
  {
    key: "engagements",
    title: "Tương tác",
    group: "Lượt tương tác",
    ...figure((row: StatsFacebookRow) => row.totals.engagements),
  },
  {
    key: "comments",
    title: "Bình luận",
    group: "Lượt tương tác",
    tip: "Của các bài app đăng trong kỳ",
    ...figure((row: StatsFacebookRow) => row.post_numbers.comments),
  },
  {
    key: "shares",
    title: "Chia sẻ",
    group: "Lượt tương tác",
    tip: "Của các bài app đăng trong kỳ",
    ...figure((row: StatsFacebookRow) => row.post_numbers.shares),
  },
  {
    key: "share_per_view",
    title: "Share/view",
    group: "Lượt tương tác",
    tip: "Chia sẻ chia cho lượt xem của các bài app đăng trong kỳ",
    numeric: true,
    value: (row: StatsFacebookRow) => row.share_per_view,
    render: (row: StatsFacebookRow) => (row.share_per_view === null ? dash : percentFormat.format(row.share_per_view)),
  },
  {
    key: "median_48h",
    title: "Trung vị 48h",
    group: "Cửa đo 48h",
    tip: "Trung vị lượt xem ở mốc 48 giờ của các video 60 ngày qua",
    numeric: true,
    value: (row: StatsFacebookRow) => row.gate.median_views,
    render: (row: StatsFacebookRow) => formatNumber(row.gate.median_views),
  },
  {
    key: "verdict",
    title: "Verdict 48h",
    group: "Cửa đo 48h",
    tip: "Kết luận của cửa đo 48h",
    value: (row: StatsFacebookRow) => row.gate.label,
    render: (row: StatsFacebookRow) => (
      <Tooltip title={`${row.gate.label} (đã đo ${row.gate.measured}/${row.gate.first}/${row.gate.last})`}>
        <Tag color={row.gate.state === "pass" ? "success" : row.gate.state === "change" ? "warning" : "default"}>
          {TIMES_LABEL[row.gate.state]}
        </Tag>
      </Tooltip>
    ),
  },
  {
    key: "view_time",
    title: "Thời gian xem",
    group: "Hiệu quả",
    tip: "Tổng thời gian xem các bài app đăng trong kỳ, số Facebook trả",
    numeric: true,
    value: (row: StatsFacebookRow) => row.view_time_seconds,
    render: (row: StatsFacebookRow) => formatDuration(row.view_time_seconds),
  },
  {
    key: "avg_watch",
    title: "Xem TB",
    group: "Hiệu quả",
    numeric: true,
    value: (row: StatsFacebookRow) => row.post_numbers.avg_watch_seconds.value,
    render: (row: StatsFacebookRow) => formatSeconds(row.post_numbers.avg_watch_seconds.value),
  },
  {
    key: "best_hours",
    title: "Khung giờ hiệu quả nhất",
    group: "Hiệu quả",
    tip: "Giờ đăng được xem nhiều nhất trong 90 ngày; “—” khi chưa đủ bài",
    value: (row: StatsFacebookRow) => hours(row),
    render: (row: StatsFacebookRow) => hours(row) ?? dash,
  },
];

function topAudience(row: StatsInstagramRow): string | null {
  const first = row.audience ? Object.values(row.audience)[0]?.[0] : undefined;
  return first ? `${first.key} (${percentFormat.format(first.share)})` : null;
}

const INSTAGRAM_CELLS: Cell[] = [
  { key: "views", title: "Lượt xem", group: "Hiệu quả", ...figure((row: StatsInstagramRow) => row.totals.views) },
  {
    key: "previous",
    title: "So kỳ trước",
    group: "Hiệu quả",
    tip: "Lượt xem của kỳ liền trước, số tuyệt đối",
    ...figure((row: StatsInstagramRow) => ({ value: row.totals.views.previous, previous: null, change: null })),
  },
  { key: "reach", title: "Tiếp cận", group: "Hiệu quả", ...figure((row: StatsInstagramRow) => row.totals.reach) },
  {
    key: "interactions",
    title: "Tương tác",
    group: "Lượt tương tác",
    ...figure((row: StatsInstagramRow) => row.totals.interactions),
  },
  {
    key: "follows",
    title: "Theo dõi mới",
    group: "Lượt tương tác",
    ...figure((row: StatsInstagramRow) => row.totals.follows),
  },
  ...(["comments", "shares", "saves"] as const).map((key): Cell => ({
    key,
    title: { comments: "Bình luận", shares: "Chia sẻ", saves: "Lượt lưu" }[key],
    group: "Lượt tương tác",
    tip: "Của các Reel app đăng trong kỳ",
    numeric: true,
    value: (row: StatsInstagramRow) => row.post_numbers[key],
    render: (row: StatsInstagramRow) => formatNumber(row.post_numbers[key]),
  })),
  {
    key: "audience",
    title: "Khán giả chính",
    group: "Hiệu quả",
    tip: "Nhóm lớn nhất trong khán giả của tài khoản Instagram",
    value: (row: StatsInstagramRow) => topAudience(row),
    render: (row: StatsInstagramRow) => topAudience(row) ?? dash,
  },
  {
    key: "best_hours",
    title: "Khung giờ hiệu quả nhất",
    group: "Hiệu quả",
    value: (row: StatsInstagramRow) => hours(row),
    render: (row: StatsInstagramRow) => hours(row) ?? dash,
  },
];

function csvCell(value: string | number | null): string {
  if (value === null) return "";
  const text = String(value);
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function downloadCsv(rows: Row[], cells: Cell[], name: string) {
  const header = ["Page", ...cells.map((cell) => cell.title)];
  const lines = rows.map((row) => [row.page.name, ...cells.map((cell) => cell.value(row as never))]);
  const text = [header, ...lines].map((line) => line.map(csvCell).join(",")).join("\r\n");
  // The BOM makes Excel read Vietnamese as UTF-8.
  const url = URL.createObjectURL(new Blob(["﻿", text], { type: "text/csv;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  URL.revokeObjectURL(url);
}

/** One line per Page over the same days; a day without a number is a gap, never 0. Absolute numbers only. */
function CompareChart({
  title,
  rows,
  pick,
}: {
  title: string;
  rows: { name: string; series: StatsSeries }[];
  pick: "views" | "engagements";
}) {
  const days = rows[0]?.series.map((point) => point.day) ?? [];
  const max = Math.max(1, ...rows.flatMap((row) => row.series.map((point) => point[pick] ?? 0)));
  const width = 640;
  const height = 180;
  const x = (index: number) => 8 + (index / Math.max(1, days.length - 1)) * (width - 16);
  const y = (value: number) => height - 8 - (value / max) * (height - 20);
  return (
    <Card size="small" title={title} data-testid={`chart-${pick}`}>
      {rows.length === 0 ? (
        <EmptyState description="Chọn ít nhất một Page" />
      ) : (
        <Flex vertical gap={8}>
          <svg viewBox={`0 0 ${width} ${height}`} width="100%" role="img" aria-label={title}>
            {rows.map((row, index) => {
              const paths: string[] = [];
              let open = false;
              row.series.forEach((point, at) => {
                const value = point[pick];
                if (value === null) {
                  open = false;
                  return;
                }
                paths.push(`${open ? "L" : "M"}${x(at).toFixed(1)},${y(value).toFixed(1)}`);
                open = true;
              });
              return (
                <path
                  key={row.name}
                  d={paths.join(" ")}
                  fill="none"
                  stroke={LINES[index % LINES.length]}
                  strokeWidth={2}
                />
              );
            })}
          </svg>
          <Flex wrap gap={12}>
            {rows.map((row, index) => (
              <Typography.Text key={row.name} style={{ fontSize: 12 }}>
                <span style={{ color: LINES[index % LINES.length] }}>●</span> {row.name}
              </Typography.Text>
            ))}
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              Cao nhất: {formatNumber(max)}
            </Typography.Text>
          </Flex>
        </Flex>
      )}
    </Card>
  );
}

function Strip({ title, children, empty }: { title: string; children: React.ReactNode; empty: string }) {
  return (
    <Card size="small" title={title} style={{ height: "100%" }}>
      {children ?? <Typography.Text type="secondary">{empty}</Typography.Text>}
    </Card>
  );
}

function Strips({ rows }: { rows: StatsFacebookRow[] }) {
  const measuring = rows.flatMap((row) => row.measuring.map((one) => ({ ...one, page: row.page.name })));
  const winners = rows.flatMap((row) => row.winners.map((one) => ({ ...one, page: row.page.name })));
  const bySharing = rows
    .filter((row) => row.share_per_view !== null)
    .sort((a, b) => b.share_per_view! - a.share_per_view!);
  const byEngagement = rows
    .filter((row) => row.totals.engagements.value !== null)
    .sort((a, b) => b.totals.engagements.value! - a.totals.engagements.value!);
  const ranked = (list: StatsFacebookRow[], text: (row: StatsFacebookRow) => string) =>
    list.length === 0 ? null : (
      <Flex vertical gap={2}>
        {list.slice(0, 5).map((row) => (
          <Typography.Text key={row.page.id}>
            {row.page.name}: <strong>{text(row)}</strong>
          </Typography.Text>
        ))}
      </Flex>
    );
  return (
    <Row gutter={[12, 12]}>
      <Col xs={24} md={12} xl={6}>
        <Strip title={`Mới đăng, đang đo 48h (${measuring.length})`} empty="Không có bài nào đang chờ mốc 48h">
          {measuring.length === 0 ? null : (
            <Flex vertical gap={2}>
              {measuring.slice(0, 6).map((one) => (
                <Typography.Text key={one.post_id} ellipsis={{ tooltip: one.video.title }}>
                  {one.page}: <Link href={`/videos/${one.video.id}`}>{one.video.title}</Link>
                </Typography.Text>
              ))}
            </Flex>
          )}
        </Strip>
      </Col>
      <Col xs={24} md={12} xl={6}>
        <Strip title={`Video thắng ≥10× trung vị (${winners.length})`} empty="Chưa có video thắng">
          {winners.length === 0 ? null : (
            <Flex vertical gap={2} data-testid="winners-strip">
              {winners.slice(0, 6).map((one) => (
                <Typography.Text key={one.post_id} ellipsis={{ tooltip: one.video.title }}>
                  {one.page}: <Link href={`/videos/${one.video.id}`}>{one.video.title}</Link>{" "}
                  <Tag color="gold">+{one.times_median}×</Tag>
                </Typography.Text>
              ))}
            </Flex>
          )}
        </Strip>
      </Col>
      <Col xs={24} md={12} xl={6}>
        <Strip title="Chia sẻ nhiều nhất (share/view)" empty="Chưa có bài nào có lượt xem">
          {ranked(bySharing, (row) => percentFormat.format(row.share_per_view!))}
        </Strip>
      </Col>
      <Col xs={24} md={12} xl={6}>
        <Strip title="Tương tác nhiều nhất" empty="Chưa có số tương tác">
          {ranked(byEngagement, (row) => formatNumber(row.totals.engagements.value))}
        </Strip>
      </Col>
    </Row>
  );
}

/** Per Page, the median views at 48 hours of each video length: the evidence for keeping short videos or not. */
function DurationCard({ rows }: { rows: StatsFacebookRow[] }) {
  const buckets = rows[0]?.duration_buckets.map((one) => one.bucket) ?? [];
  return (
    <Card
      size="small"
      title="Thời lượng nào hiệu quả nhất"
      data-testid="duration-card"
      extra={
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          Trung vị lượt xem 48h theo độ dài video, trong kỳ đã chọn
        </Typography.Text>
      }
    >
      <Table<StatsFacebookRow>
        rowKey={(row) => row.page.id}
        size="small"
        pagination={false}
        dataSource={rows}
        scroll={{ x: "max-content" }}
        locale={{ emptyText: <EmptyState description="Chưa chọn Page nào." /> }}
        columns={[
          { key: "page", title: "Page", fixed: "left", width: 200, render: (_: unknown, row) => row.page.name },
          ...buckets.map((bucket) => ({
            key: bucket,
            title: bucket,
            render: (_: unknown, row: StatsFacebookRow) => {
              const one = row.duration_buckets.find((item) => item.bucket === bucket)!;
              return (
                <Flex vertical gap={0}>
                  {one.median_views_48h === null ? (
                    <Typography.Text type="secondary">Chưa đủ mẫu</Typography.Text>
                  ) : (
                    <span style={{ fontVariantNumeric: "tabular-nums" }}>
                      <strong>{formatNumber(one.median_views_48h)}</strong>{" "}
                      {one.best && <Tag color="gold">Tốt nhất</Tag>}
                    </span>
                  )}
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    {one.videos} video
                  </Typography.Text>
                </Flex>
              );
            },
          })),
        ]}
      />
      <Typography.Text type="secondary" style={{ fontSize: 12, color: COLORS.textSecondary }}>
        Chỉ tính video đã đủ 48h, đo bằng độ dài file MP4; một nhóm cần ít nhất 5 video mới có số. Khác “Trung vị 48h” ở
        bảng trên (60 ngày gần nhất).
      </Typography.Text>
    </Card>
  );
}

function StatsView() {
  const { message } = App.useApp();
  const [days, setDays] = useUrlChoice<(typeof PERIODS)[number]>("days", "28", PERIODS);
  const [platform, setPlatform] = useUrlChoice<Platform>("platform", "facebook", PLATFORMS);
  const [pages, setPages] = useState<Fanpage[] | null>(null);
  const [picked, setPicked] = useState<number[] | null>(null);
  const [data, setData] = useState<Stats<Row> | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api<Fanpage[]>("/fanpages")
      .then((rows) => {
        const active = rows.filter((row) => row.active);
        setPages(active);
        // The member's own Pages are the ones compared at first; a teammate's are one click away.
        setPicked(active.filter((row) => row.mine).map((row) => row.id));
      })
      .catch((err) => message.error(errorMessage(err)));
  }, [message]);

  const key = picked?.join(",") ?? null;
  useEffect(() => {
    if (platform === "tiktok" || key === null) return;
    if (key === "") {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- no Page chosen: nothing to ask, an empty table
      setData({ days: Number(days), platform, start: "", end: "", rows: [] });
      return;
    }
    let current = true;
    setLoading(true);
    api<Stats<Row>>(`/stats?days=${days}&platform=${platform}&page_ids=${key}`)
      .then((body) => current && setData(body))
      .catch((err) => message.error(errorMessage(err)))
      .finally(() => current && setLoading(false));
    return () => {
      current = false;
    };
  }, [days, platform, key, message]);

  const cells = platform === "instagram" ? INSTAGRAM_CELLS : FACEBOOK_CELLS;
  const known = useMemo(() => cells.map((cell) => cell.key), [cells]);
  const storage = platform === "instagram" ? COLUMNS_KEY.instagram : COLUMNS_KEY.facebook;
  return (
    <>
      <PageHeader
        title="Thống kê"
        description="So sánh các Page với nhau, mỗi Page một dòng. Chỉ có số của từng Page, không cộng tổng; số nào Facebook không trả thì để trống."
        actions={
          <Segmented<Platform>
            value={platform}
            onChange={setPlatform}
            options={[
              { value: "facebook", label: "Facebook" },
              { value: "instagram", label: "Instagram" },
              { value: "tiktok", label: "TikTok" },
            ]}
          />
        }
      >
        <Select
          mode="multiple"
          allowClear
          maxTagCount="responsive"
          style={{ minWidth: 280, maxWidth: 480 }}
          placeholder="Chọn Page để so sánh"
          aria-label="Chọn Page để so sánh"
          loading={pages === null}
          value={picked ?? []}
          onChange={setPicked}
          optionFilterProp="label"
          options={[
            {
              label: "Của tôi",
              options: (pages ?? []).filter((row) => row.mine).map((row) => ({ value: row.id, label: row.name })),
            },
            {
              label: "Của đồng đội",
              options: (pages ?? []).filter((row) => !row.mine).map((row) => ({ value: row.id, label: row.name })),
            },
          ]}
        />
        <Segmented<(typeof PERIODS)[number]>
          value={days}
          onChange={setDays}
          options={PERIODS.map((one) => ({ value: one, label: `${one} ngày` }))}
        />
      </PageHeader>
      {platform === "tiktok" ? (
        <Card>
          <EmptyState description="TikTok chưa có nguồn số liệu để so sánh." />
        </Card>
      ) : (
        <ComparisonTable
          key={platform}
          cells={cells}
          known={known}
          storage={storage}
          data={data}
          loading={loading}
          platform={platform}
          days={days}
        />
      )}
    </>
  );
}

function ComparisonTable({
  cells,
  known,
  storage,
  data,
  loading,
  platform,
  days,
}: {
  cells: Cell[];
  known: string[];
  storage: string;
  data: Stats<Row> | null;
  loading: boolean;
  platform: Platform;
  days: string;
}) {
  const [shown, setShown] = useRememberedColumns<string>(storage, known, known);
  const columns = shown.map((key) => cells.find((cell) => cell.key === key)!).filter(Boolean);
  const rows = data?.rows ?? [];
  const chartRows = rows.map((row) => ({ name: row.page.name, series: row.series }));
  return (
    <Flex vertical gap={12}>
      <Row gutter={[12, 12]}>
        <Col xs={24} xl={12}>
          <CompareChart title="Lượt xem theo ngày" rows={chartRows} pick="views" />
        </Col>
        <Col xs={24} xl={12}>
          <CompareChart title="Tương tác theo ngày" rows={chartRows} pick="engagements" />
        </Col>
      </Row>
      {platform === "facebook" && <Strips rows={rows as StatsFacebookRow[]} />}
      <Card
        size="small"
        title={data && data.start ? `${rows.length} Page, ${data.start} → ${data.end}` : "Các Page"}
        extra={
          <Flex gap={8}>
            <ColumnPicker<string>
              columns={cells.map(({ key, title, group }) => ({ key, title, group }))}
              shown={shown}
              onApply={setShown}
            />
            <Button
              size="small"
              icon={<DownloadOutlined />}
              disabled={rows.length === 0}
              onClick={() => downloadCsv(rows, columns, `thong-ke-${platform}-${days}-ngay.csv`)}
            >
              Xuất CSV
            </Button>
          </Flex>
        }
      >
        <Table<Row>
          data-testid="stats-table"
          rowKey={(row) => row.page.id}
          size="small"
          loading={loading || data === null}
          dataSource={rows}
          pagination={false}
          scroll={{ x: "max-content" }}
          locale={{ emptyText: <EmptyState description="Chưa chọn Page nào, hoặc Page không có số trong kỳ này." /> }}
          columns={[
            { key: "page", title: "Page", fixed: "left", width: 200, render: (_: unknown, row: Row) => row.page.name },
            ...columns.map((cell) => ({
              key: cell.key,
              title: cell.tip ? (
                <Tooltip title={cell.tip}>
                  <span style={{ whiteSpace: "nowrap" }}>{cell.title}</span>
                </Tooltip>
              ) : (
                <span style={{ whiteSpace: "nowrap" }}>{cell.title}</span>
              ),
              align: cell.numeric ? ("right" as const) : undefined,
              render: (_: unknown, row: Row) => (
                <span style={cell.numeric ? { fontVariantNumeric: "tabular-nums" } : undefined}>
                  {cell.render(row as never)}
                </span>
              ),
            })),
            {
              key: "dashboard",
              title: "Dashboard",
              fixed: "right",
              width: 100,
              render: (_: unknown, row: Row) => (
                <Link href={`/fanpages/${row.page.id}`} prefetch={false}>
                  Mở
                </Link>
              ),
            },
          ]}
        />
        <Typography.Text type="secondary" style={{ fontSize: 12, color: COLORS.textSecondary }}>
          Nguồn: Facebook và Instagram, đọc qua tool. Facebook không trả “người xem”, “hiển thị”, xem từ 1 phút hay tỉ
          lệ chưa theo dõi nên các cột này không có. Số tuyệt đối, không tính % tăng.
        </Typography.Text>
      </Card>
      {platform === "facebook" && <DurationCard rows={rows as StatsFacebookRow[]} />}
    </Flex>
  );
}

export default function Page() {
  return (
    <Suspense fallback={null}>
      <StatsView />
    </Suspense>
  );
}
