"use client";

import { CopyOutlined, DownloadOutlined, ForkOutlined, LinkOutlined } from "@ant-design/icons";
import { App, Button, Card, Flex, Grid, Input, Segmented, Skeleton, Table, Tooltip, Typography, theme } from "antd";
import { useCallback, useEffect, useState } from "react";
import { api, errorMessage, formatDateTime, formatDayTime } from "@/lib/api";
import { formatCompact, formatFull, thresholdLabel } from "@/lib/competitorFormat";
import CloneVideoModal from "./CloneVideoModal";
import type { Frequency, Report, ScanDetail, Stats, VideoPage, VideoRow } from "./types";

const PAGE = 20;
// What was read for a scan does not change, so closing and opening a row never asks again.
const details = new Map<string, ScanDetail>();

/** The expanded row: the scan's numbers, how views spread, and the videos a page at a time. */
export default function ScanDetailView({ competitorId, scanId }: { competitorId: number; scanId: number }) {
  const key = `${competitorId}:${scanId}`;
  const [detail, setDetail] = useState<ScanDetail | null>(details.get(key) ?? null);
  const [failed, setFailed] = useState("");
  useEffect(() => {
    if (details.has(key)) return;
    api<ScanDetail>(`/competitors/scans/${scanId}`).then(
      (data) => {
        details.set(key, data);
        setDetail(data);
      },
      (err) => setFailed(errorMessage(err)),
    );
  }, [key, scanId]);
  if (failed) return <Typography.Text type="danger">{failed}</Typography.Text>;
  if (!detail) return <Skeleton active paragraph={{ rows: 4 }} title={false} />;
  const { stats } = detail;
  return (
    <Flex vertical gap={16}>
      <MetricCards stats={stats} />
      <Distribution stats={stats} />
      <FrequencyView frequency={stats.frequency} />
      <VideoList competitorId={competitorId} scanId={scanId} />
      <Typography.Text type="secondary">
        {stats.limits.join(" ")}
        {!detail.report &&
          " Nhờ Claude (kết nối MCP Reels Studio) phân tích chủ đề, nỗi đau và đề xuất nội dung, rồi lưu báo cáo."}
      </Typography.Text>
      {detail.report && <ReportView report={detail.report} />}
    </Flex>
  );
}

function Metric({ label, value, hint }: { label: string; value: string | null; hint?: string }) {
  return (
    <Flex vertical gap={2} style={{ minWidth: 0 }}>
      <Typography.Text type="secondary">{label}</Typography.Text>
      {value === null ? (
        <Tooltip title={hint ?? "Chưa đọc được"}>
          <Typography.Text type="secondary">—</Typography.Text>
        </Tooltip>
      ) : (
        <Typography.Text strong style={{ fontVariantNumeric: "tabular-nums" }}>
          {value}
        </Typography.Text>
      )}
    </Flex>
  );
}

function MetricCards({ stats }: { stats: Stats }) {
  const noDate = "Chưa đọc được ngày đăng";
  return (
    <div
      style={{ display: "grid", gap: 16, gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))" }}
      data-testid="competitor-metrics"
    >
      <Metric label="Số video" value={formatFull(stats.videos)} />
      <Metric label="Tổng view" value={formatCompact(stats.total_views)} />
      <Metric
        label="Trung vị"
        value={stats.median_views === null ? null : formatCompact(stats.median_views)}
        hint="Chưa đọc được lượt xem"
      />
      <Metric
        label="Top 10 chiếm"
        value={stats.top10_share === null ? null : `${Math.round(stats.top10_share * 1000) / 10}%`.replace(".", ",")}
      />
      <Metric
        label="Video/tuần"
        value={stats.videos_per_week === null ? null : String(stats.videos_per_week).replace(".", ",")}
        hint={noDate}
      />
      <Metric
        label="Đăng gần nhất"
        value={stats.newest_posted_at ? formatDayTime(stats.newest_posted_at) : null}
        hint={noDate}
      />
      <Metric
        label="Cũ nhất đọc được"
        value={stats.oldest_posted_at ? formatDateTime(stats.oldest_posted_at).slice(0, 10) : null}
        hint={noDate}
      />
    </div>
  );
}

/** One stacked bar over the four view groups, dark to light; each group is named with its videos and share. */
function Distribution({ stats }: { stats: Stats }) {
  const { token } = theme.useToken();
  const total = stats.buckets.reduce((sum, bucket) => sum + bucket.videos, 0);
  if (!total) return null;
  const shades = ["ff", "b3", "73", "40"];
  return (
    <Flex vertical gap={8}>
      <Typography.Text type="secondary">Phân bổ view</Typography.Text>
      <Flex
        role="img"
        aria-label={stats.buckets.map((bucket) => `${bucket.label}: ${bucket.videos} video`).join(", ")}
        style={{ height: 12, borderRadius: 6, overflow: "hidden", background: token.colorFillSecondary }}
      >
        {stats.buckets.map((bucket, index) => (
          <div
            key={bucket.label}
            style={{
              width: `${(bucket.videos / total) * 100}%`,
              background: `${token.colorPrimary}${shades[index]}`,
            }}
          />
        ))}
      </Flex>
      <Flex wrap gap="4px 16px">
        {stats.buckets.map((bucket, index) => (
          <Flex key={bucket.label} gap={6} align="center">
            <span
              aria-hidden
              style={{
                width: 10,
                height: 10,
                borderRadius: 2,
                background: `${token.colorPrimary}${shades[index]}`,
                boxShadow: `inset 0 0 0 1px ${token.colorBorderSecondary}`,
              }}
            />
            <Typography.Text style={{ fontVariantNumeric: "tabular-nums" }}>
              {bucket.label}: {formatFull(bucket.videos)} video ({Math.round((bucket.videos / total) * 100)}%)
            </Typography.Text>
          </Flex>
        ))}
      </Flex>
    </Flex>
  );
}

/** How often each grid was posted to over time: the stretches between dated videos, newest first. */
function FrequencyView({ frequency }: { frequency: Stats["frequency"] }) {
  const grids = (
    [
      ["Reels", frequency.reel],
      ["Video", frequency.video],
    ] as [string, Frequency | null][]
  ).filter(([, grid]) => grid && grid.stretches.length);
  if (!grids.length) return null;
  const day = (iso: string) => formatDateTime(iso).slice(0, 10);
  return (
    <Flex vertical gap={4}>
      {grids.map(([label, grid]) => (
        <Typography.Text key={label} type="secondary">
          {label}:{" "}
          {grid!.stretches
            .map(
              (stretch) =>
                `${day(stretch.from)} đến ${day(stretch.to)}: ${String(stretch.videos_per_week ?? "—").replace(".", ",")}/tuần`,
            )
            .join("; ")}
        </Typography.Text>
      ))}
    </Flex>
  );
}

function VideoList({ competitorId, scanId }: { competitorId: number; scanId: number }) {
  const { message } = App.useApp();
  const [sort, setSort] = useState<"views" | "posted">("views");
  const [query, setQuery] = useState("");
  // A small channel keeps every video, so its list can be narrowed by views; a big one already holds only the top.
  const [minViews, setMinViews] = useState(0);
  const [threshold, setThreshold] = useState<number | null>(null);
  const [rows, setRows] = useState<VideoRow[]>([]);
  const [total, setTotal] = useState(0);
  const [flags, setFlags] = useState({ engagement: false, published: false });
  const [loading, setLoading] = useState(true);
  const [anyCaption, setAnyCaption] = useState(false);
  // "Clone": the video whose dialog is open.
  const [cloning, setCloning] = useState<VideoRow | null>(null);
  // Below 768 px the buttons of a row are at least 44 px, for a finger.
  const narrow = !Grid.useBreakpoint().md;
  const touch = narrow ? { minWidth: 44, minHeight: 44 } : undefined;

  const load = useCallback(
    async (page: number, replace: boolean) => {
      setLoading(true);
      try {
        const params = new URLSearchParams({ page: String(page), limit: String(PAGE), sort });
        if (query.trim()) params.set("q", query.trim());
        if (minViews) params.set("min_views", String(minViews));
        const data = await api<VideoPage>(`/competitors/${competitorId}/videos?${params}`);
        setRows((before) => (replace ? data.videos : [...before, ...data.videos]));
        setTotal(data.total);
        setThreshold(data.threshold_applied);
        setFlags({ engagement: data.has_engagement, published: data.has_published_at });
        if (data.videos.some((video) => video.caption)) setAnyCaption(true);
      } catch (err) {
        message.error(errorMessage(err));
      } finally {
        setLoading(false);
      }
    },
    [competitorId, message, minViews, query, sort],
  );
  // The first page again whenever the scan, the sort or the search changes (the search waits for a pause in typing).
  useEffect(() => {
    const wait = window.setTimeout(() => void load(1, true), query ? 300 : 0);
    return () => window.clearTimeout(wait);
  }, [load, query, scanId]);

  const columns = [
    { title: "#", dataIndex: "rank", width: 56 },
    {
      title: "Video",
      key: "video",
      render: (_: unknown, video: VideoRow) => {
        const label = video.caption || `${video.type === "video" ? "Video" : "Reel"} …${video.fb_video_id.slice(-6)}`;
        return (
          <Flex gap={8} align="center" style={{ minWidth: 0 }}>
            {video.thumb_url && (
              // eslint-disable-next-line @next/next/no-img-element -- a small private picture from the api, already shrunk
              <img
                src={video.thumb_url}
                alt=""
                width={48}
                height={64}
                loading="lazy"
                style={{ objectFit: "cover", borderRadius: 4, flex: "none" }}
              />
            )}
            <Typography.Text ellipsis={{ tooltip: label }} style={{ maxWidth: 360 }}>
              {label}
            </Typography.Text>
            <Tooltip title="Mở trên Facebook">
              <Typography.Link
                href={video.url}
                target="_blank"
                rel="noreferrer"
                aria-label={`Mở ${video.type === "video" ? "video" : "reel"} …${video.fb_video_id.slice(-6)} trên Facebook`}
              >
                <LinkOutlined />
              </Typography.Link>
            </Tooltip>
            <Tooltip title="Sao chép link">
              <Button
                type="text"
                size="small"
                icon={<CopyOutlined />}
                aria-label={`Sao chép link …${video.fb_video_id.slice(-6)}`}
                onClick={() => {
                  void navigator.clipboard?.writeText(video.url).then(() => message.success("Đã sao chép link"));
                }}
              />
            </Tooltip>
            <Tooltip title={video.caption ? "Clone video này" : "Video chưa có caption"}>
              <Button
                type="text"
                size="small"
                icon={<ForkOutlined />}
                style={touch}
                disabled={!video.caption}
                aria-label={`Clone video …${video.fb_video_id.slice(-6)}`}
                onClick={() => setCloning(video)}
              />
            </Tooltip>
          </Flex>
        );
      },
    },
    {
      title: "View",
      key: "views",
      width: 100,
      align: "right" as const,
      render: (_: unknown, video: VideoRow) =>
        video.views === null ? (
          "—"
        ) : (
          <Tooltip title={formatFull(video.views)}>
            <span style={{ fontVariantNumeric: "tabular-nums" }}>{formatCompact(video.views)}</span>
          </Tooltip>
        ),
    },
    ...(flags.engagement
      ? [
          {
            title: "Tương tác",
            key: "engagement",
            width: 190,
            render: (_: unknown, video: VideoRow) => (
              <Typography.Text type="secondary" style={{ fontVariantNumeric: "tabular-nums" }}>
                {`${formatCompact(video.reactions)} cảm xúc, ${formatCompact(video.comments)} bình luận, ${formatCompact(video.shares)} chia sẻ`}
              </Typography.Text>
            ),
          },
        ]
      : []),
    ...(flags.published
      ? [
          {
            title: "Ngày đăng",
            key: "posted",
            width: 130,
            render: (_: unknown, video: VideoRow) => (video.posted_at ? formatDayTime(video.posted_at) : "—"),
          },
        ]
      : []),
  ];

  return (
    <Flex vertical gap={8} data-testid="competitor-videos">
      {cloning && <CloneVideoModal competitorId={competitorId} video={cloning} onClose={() => setCloning(null)} />}
      <Flex wrap gap={8} justify="space-between" align="center">
        <Typography.Text strong>
          {threshold != null ? `Video ≥${thresholdLabel(threshold)} view` : "Video"} ({formatFull(total)})
        </Typography.Text>
        <Flex wrap gap={8} align="center">
          {anyCaption && (
            <Input.Search
              allowClear
              size="small"
              placeholder="Tìm trong caption…"
              aria-label="Tìm trong caption"
              style={{ width: 200 }}
              onSearch={setQuery}
              onChange={(event) => !event.target.value && setQuery("")}
            />
          )}
          {threshold == null && (
            <Segmented
              size="small"
              aria-label="Lọc video theo view"
              value={minViews}
              onChange={(value) => setMinViews(Number(value))}
              options={[
                { label: "Tất cả", value: 0 },
                { label: "≥10K", value: 10_000 },
                { label: "≥100K", value: 100_000 },
                { label: "≥1M", value: 1_000_000 },
              ]}
            />
          )}
          {flags.published && (
            <Segmented
              size="small"
              aria-label="Sắp xếp video"
              value={sort}
              onChange={(value) => setSort(value as "views" | "posted")}
              options={[
                { label: "Nhiều view", value: "views" },
                { label: "Mới đăng", value: "posted" },
              ]}
            />
          )}
          <Button
            size="small"
            icon={<DownloadOutlined />}
            href={`/api/competitors/${competitorId}/videos.csv`}
            download
          >
            Xuất CSV
          </Button>
        </Flex>
      </Flex>
      {loading && !rows.length ? (
        <Skeleton active title={false} paragraph={{ rows: 5 }} />
      ) : (
        <Table<VideoRow>
          size="small"
          rowKey="fb_video_id"
          pagination={false}
          dataSource={rows}
          columns={columns}
          scroll={{ x: 560 }}
          locale={{ emptyText: query ? "Không có video khớp lời tìm" : "Chưa đọc được video nào" }}
        />
      )}
      {rows.length > 0 && (
        <Flex gap={12} align="center" justify="center">
          <Typography.Text type="secondary">
            {formatFull(rows.length)}/{formatFull(total)}
          </Typography.Text>
          {rows.length < total && (
            <Button loading={loading} onClick={() => void load(Math.floor(rows.length / PAGE) + 1, false)}>
              Xem thêm {PAGE} video
            </Button>
          )}
        </Flex>
      )}
    </Flex>
  );
}

/** The latest report the member's Claude saved (competitor_report_save), shown as the text it wrote. */
function ReportView({ report }: { report: Report }) {
  return (
    <Card
      size="small"
      title="Báo cáo phân tích"
      extra={
        <Typography.Text type="secondary">
          {[report.created_by, report.written_by, report.created_at ? formatDateTime(report.created_at) : ""]
            .filter(Boolean)
            .join(", ")}
        </Typography.Text>
      }
    >
      <Typography.Paragraph
        copyable={{ text: report.markdown, tooltips: ["Sao chép báo cáo", "Đã sao chép"] }}
        style={{ whiteSpace: "pre-wrap", margin: 0, maxHeight: 520, overflow: "auto" }}
      >
        {report.markdown}
      </Typography.Paragraph>
    </Card>
  );
}
