"use client";

import EmptyState from "@/components/EmptyState";
import PageHeader from "@/components/PageHeader";
import { DeleteOutlined, LinkOutlined, ReloadOutlined, SearchOutlined, SwapOutlined } from "@ant-design/icons";
import {
  Alert,
  App,
  Button,
  Card,
  Checkbox,
  Descriptions,
  Flex,
  Input,
  Modal,
  Popconfirm,
  Space,
  Table,
  Tag,
  Typography,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { useCallback, useEffect, useState } from "react";
import { api, errorMessage, formatDateTime, formatDayTime } from "@/lib/api";
import {
  openExtensionOptions,
  useCompetitorScanner,
  type CompetitorScan,
  type ScanAccount,
} from "@/lib/competitorScanner";
import { usePolling } from "@/lib/polling";

type Competitor = {
  id: number;
  fb_url: string;
  kind: "page" | "profile";
  name: string | null;
  followers: number | null;
  reels_url: string;
  latest_scan: (CompetitorScan & { total_views: number }) | null;
};

type Stats = {
  videos: number;
  videos_with_views: number;
  total_views: number;
  median_views: number | null;
  buckets: { label: string; videos: number; views: number }[];
  top10_share: number | null;
  by_type: { reel: number; video: number };
  videos_per_week: number | null;
  frequency: { reel: Frequency | null; video: Frequency | null };
  newest_posted_at: string | null;
  oldest_posted_at: string | null;
  limits: string[];
};

/** How often one grid was posted to (api competitors._frequency): the whole span, and each stretch between dates. */
type Frequency = {
  videos_per_week: number | null;
  from: string;
  to: string;
  videos: number;
  stretches: { from: string; to: string; videos: number; videos_per_week: number | null }[];
};

/** One competitor in "So sánh" (api competitors.compare), by its latest scan that read anything. */
type Compared = {
  competitor: { id: number; fb_url: string; name: string | null };
  scan: {
    videos: number;
    by_type: { reel: number; video: number };
    total_views: number;
    median_views: number | null;
    max_views: number | null;
    top10_share: number | null;
    videos_per_week: number | null;
    newest_posted_at: string | null;
    finished_at: string | null;
  } | null;
};

type TopVideo = {
  rank: number;
  fb_video_id: string;
  url: string;
  views: number | null;
  views_raw: string | null;
  caption: string | null;
  audio_name: string | null;
  reactions: number | null;
  comments: number | null;
  shares: number | null;
  posted_at: string | null;
  posted_raw: string | null;
  type: "reel" | "video";
};
type Report = { id: number; created_at: string | null; written_by: string; markdown: string };
type ScanDetail = CompetitorScan & { stats: Stats; top_videos: TopVideo[]; report: Report | null };

const STATUS: Record<CompetitorScan["status"], { label: string; color: string }> = {
  queued: { label: "Chờ quét", color: "default" },
  running: { label: "Đang quét", color: "processing" },
  partial: { label: "Dừng giữa chừng", color: "warning" },
  done: { label: "Xong", color: "success" },
  failed: { label: "Lỗi", color: "error" },
};

const number = new Intl.NumberFormat("vi-VN");

export default function CompetitorsPage() {
  const { message } = App.useApp();
  const [competitors, setCompetitors] = useState<Competitor[] | null>(null);
  const [url, setUrl] = useState("");
  const [starting, setStarting] = useState(false);
  const [wakeUp, setWakeUp] = useState(0);
  const [open, setOpen] = useState<number | null>(null);
  // M5: the Videos tab is read too; competitors ticked for "So sánh".
  const [includeVideos, setIncludeVideos] = useState(false);
  const [picked, setPicked] = useState<number[]>([]);
  const [comparing, setComparing] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await api<{ competitors: Competitor[] }>("/competitors");
      setCompetitors(data.competitors);
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
  const waiting = competitors?.some((row) => row.latest_scan && ["queued", "running"].includes(row.latest_scan.status));
  // Every few seconds only while a scan waits or runs; once a minute otherwise.
  usePolling(load, waiting ? 5_000 : 60_000);

  async function start() {
    setStarting(true);
    try {
      await api("/competitors/scans", "POST", { url, include_videos: includeVideos });
      setUrl("");
      setWakeUp((value) => value + 1);
      await load();
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setStarting(false);
    }
  }

  async function act(path: string, method: "POST" | "DELETE", done: string) {
    try {
      await api(path, method);
      message.success(done);
      setWakeUp((value) => value + 1);
    } catch (err) {
      message.error(errorMessage(err));
    }
    await load();
  }

  const columns: ColumnsType<Competitor> = [
    {
      title: "Đối thủ",
      key: "name",
      render: (_, row) => (
        <Flex vertical gap={2}>
          <Typography.Text strong>{row.name || row.fb_url.replace("https://www.facebook.com/", "")}</Typography.Text>
          <Typography.Link href={row.reels_url} target="_blank" rel="noreferrer">
            <LinkOutlined /> Mở tab Reels
          </Typography.Link>
        </Flex>
      ),
    },
    {
      title: "Lượt quét gần nhất",
      key: "scan",
      width: 260,
      render: (_, row) => {
        const scan = row.latest_scan;
        if (!scan) return "—";
        const progress = scanner.running?.scan.id === scan.id ? scanner.running : null;
        return (
          <Flex vertical gap={2}>
            <Space size={4}>
              <Tag color={STATUS[scan.status].color}>{STATUS[scan.status].label}</Tag>
              <Typography.Text>{number.format(progress ? progress.found : scan.videos_found)} video</Typography.Text>
            </Space>
            {progress?.details && (
              <Typography.Text type="secondary">
                Đang mở top video: {progress.details.read}/{progress.details.of}
              </Typography.Text>
            )}
            {scan.error && <Typography.Text type="warning">{scan.error}</Typography.Text>}
            <Typography.Text type="secondary">
              {formatDateTime(scan.finished_at ?? scan.started_at ?? scan.created_at ?? "")}
            </Typography.Text>
          </Flex>
        );
      },
    },
    {
      title: "Tổng view",
      key: "views",
      width: 140,
      render: (_, row) => (row.latest_scan ? number.format(row.latest_scan.total_views) : "—"),
    },
    {
      title: "Thao tác",
      key: "actions",
      width: 260,
      render: (_, row) => {
        const scan = row.latest_scan;
        return (
          <Space wrap>
            {scan && ["partial", "failed"].includes(scan.status) && (
              <Button onClick={() => act(`/competitors/scans/${scan.id}/resume`, "POST", "Đã xếp lại lượt quét")}>
                Tiếp tục
              </Button>
            )}
            {(!scan || ["done", "partial", "failed"].includes(scan.status)) && (
              <Button
                icon={<ReloadOutlined />}
                onClick={async () => {
                  try {
                    await api("/competitors/scans", "POST", { url: row.fb_url });
                    setWakeUp((value) => value + 1);
                  } catch (err) {
                    message.error(errorMessage(err));
                  }
                  await load();
                }}
              >
                Quét lại
              </Button>
            )}
            <Popconfirm
              title="Xóa toàn bộ dữ liệu của đối thủ này?"
              description="Mọi lượt quét và video đã đọc bị xóa hẳn."
              okText="Xóa"
              cancelText="Hủy"
              onConfirm={() => act(`/competitors/${row.id}`, "DELETE", "Đã xóa dữ liệu đối thủ")}
            >
              <Button danger icon={<DeleteOutlined />} aria-label="Xóa dữ liệu" />
            </Popconfirm>
          </Space>
        );
      },
    },
  ];

  return (
    <>
      <PageHeader title="Phân tích đối thủ">
        <Flex vertical gap={12}>
          <Space.Compact style={{ maxWidth: 640, width: "100%" }}>
            <Input
              placeholder="Dán link Facebook của đối thủ, ví dụ facebook.com/tenpage"
              aria-label="Link Facebook của đối thủ"
              value={url}
              onChange={(event) => setUrl(event.target.value)}
              onPressEnter={() => url.trim() && start()}
            />
            <Button type="primary" icon={<SearchOutlined />} loading={starting} disabled={!url.trim()} onClick={start}>
              Quét
            </Button>
          </Space.Compact>
          <Flex gap={12} wrap align="center">
            <Checkbox checked={includeVideos} onChange={(event) => setIncludeVideos(event.target.checked)}>
              Quét cả tab Video (video thường), sau Reels
            </Checkbox>
            <Button icon={<SwapOutlined />} disabled={picked.length < 2} onClick={() => setComparing(true)}>
              So sánh {picked.length >= 2 ? `${picked.length} đối thủ` : "(chọn từ 2 đối thủ)"}
            </Button>
          </Flex>
          <ScannerNotice
            version={scanner.version}
            current={scanner.current}
            account={scanner.account}
            ready={scanner.ready}
          />
        </Flex>
      </PageHeader>
      <Card styles={{ body: { padding: 0 } }}>
        <Table<Competitor>
          rowKey="id"
          columns={columns}
          rowSelection={{
            selectedRowKeys: picked,
            onChange: (keys) => setPicked(keys.map(Number).slice(0, 10)),
            getCheckboxProps: (row) => ({ "aria-label": `Chọn ${row.name || row.fb_url} để so sánh` }),
          }}
          dataSource={competitors ?? []}
          loading={competitors === null}
          pagination={false}
          scroll={{ x: 900 }}
          expandable={{
            expandedRowKeys: open ? [open] : [],
            onExpand: (expanded, row) => setOpen(expanded ? row.id : null),
            rowExpandable: (row) => Boolean(row.latest_scan?.videos_found),
            expandedRowRender: (row) => row.latest_scan && <ScanDetailView scanId={row.latest_scan.id} />,
          }}
          locale={{ emptyText: <EmptyState description="Chưa quét đối thủ nào: dán link Facebook ở trên" /> }}
        />
      </Card>
      {comparing && <CompareView ids={picked} onClose={() => setComparing(false)} />}
    </>
  );
}

/** "So sánh": the ticked competitors side by side, each by its latest scan that read anything. */
function CompareView({ ids, onClose }: { ids: number[]; onClose: () => void }) {
  const [rows, setRows] = useState<Compared[] | null>(null);
  const [failed, setFailed] = useState("");
  useEffect(() => {
    api<{ competitors: Compared[] }>(`/competitors/compare?ids=${ids.join(",")}`)
      .then((data) => setRows(data.competitors))
      .catch((err) => setFailed(errorMessage(err)));
  }, [ids]);
  const value = (row: Compared, read: (scan: NonNullable<Compared["scan"]>) => string) =>
    row.scan ? read(row.scan) : "Chưa quét xong";
  return (
    <Modal open title="So sánh đối thủ" footer={null} onCancel={onClose} width={960}>
      {failed && <Typography.Text type="danger">{failed}</Typography.Text>}
      <Table<Compared>
        size="small"
        rowKey={(row) => row.competitor.id}
        loading={rows === null && !failed}
        dataSource={rows ?? []}
        pagination={false}
        scroll={{ x: 820 }}
        columns={[
          {
            title: "Đối thủ",
            key: "name",
            render: (_, row) => row.competitor.name || row.competitor.fb_url.replace("https://www.facebook.com/", ""),
          },
          {
            title: "Video (Reels · Video)",
            key: "videos",
            render: (_, row) =>
              value(row, (scan) => `${number.format(scan.videos)} (${scan.by_type.reel} · ${scan.by_type.video})`),
          },
          {
            title: "Tổng view",
            key: "total",
            render: (_, row) => value(row, (scan) => number.format(scan.total_views)),
          },
          {
            title: "Trung vị",
            key: "median",
            render: (_, row) =>
              value(row, (scan) => (scan.median_views === null ? "—" : number.format(scan.median_views))),
          },
          {
            title: "Cao nhất",
            key: "max",
            render: (_, row) => value(row, (scan) => (scan.max_views === null ? "—" : number.format(scan.max_views))),
          },
          {
            title: "Top 10 chiếm",
            key: "top10",
            render: (_, row) =>
              value(row, (scan) => (scan.top10_share === null ? "—" : `${Math.round(scan.top10_share * 1000) / 10}%`)),
          },
          {
            title: "Video/tuần",
            key: "frequency",
            render: (_, row) =>
              value(row, (scan) => (scan.videos_per_week === null ? "—" : String(scan.videos_per_week))),
          },
          {
            title: "Đăng gần nhất",
            key: "newest",
            render: (_, row) =>
              value(row, (scan) => (scan.newest_posted_at ? formatDayTime(scan.newest_posted_at) : "—")),
          },
        ]}
      />
      <Typography.Text type="secondary">
        Số liệu tính bằng code từ lượt quét gần nhất của từng đối thủ. Nhờ Claude (competitor_compare) để rút ra khác
        biệt về chủ đề và cách làm.
      </Typography.Text>
    </Modal>
  );
}

function ScannerNotice({
  version,
  current,
  account,
  ready,
}: {
  version: string;
  current: boolean;
  account: ScanAccount | null;
  ready: boolean;
}) {
  if (ready && account) {
    return (
      <Typography.Text type="secondary">
        Tiện ích đã sẵn sàng, quét bằng tài khoản phụ {account.userId} trong cửa sổ ẩn danh. Giữ trang này mở: lượt quét
        (kể cả do Claude tạo qua MCP) chạy trong Chrome này, cuộn chậm như người thật.{" "}
        <Typography.Link onClick={openExtensionOptions}>Đổi tài khoản phụ</Typography.Link>
      </Typography.Text>
    );
  }
  if (!current) {
    return (
      <Alert
        type="info"
        showIcon
        message={version ? `Tiện ích bản ${version} chưa quét được đối thủ` : "Chưa thấy tiện ích Reels Studio"}
        description="Cài hoặc cập nhật tiện ích (thư mục extension/ của dự án, bản 1.4.0 trở lên) trong Chrome, rồi tải lại trang."
      />
    );
  }
  const missing = [];
  if (!account?.userId) missing.push("lưu cookie của tài khoản Facebook phụ");
  if (account && !account.incognito)
    missing.push('bật "Cho phép ở chế độ ẩn danh" cho tiện ích trong chrome://extensions');
  return (
    <Alert
      type="warning"
      showIcon
      message="Chưa quét được: cần tài khoản Facebook phụ"
      description={
        <Flex vertical gap={8} align="start">
          <span>
            Lượt quét chỉ chạy bằng tài khoản phụ, trong cửa sổ ẩn danh, để Facebook chính của bạn không bị ảnh hưởng.
            Cookie chỉ lưu trong tiện ích của Chrome này, không gửi lên máy chủ. Còn thiếu: {missing.join("; ") || "…"}.
          </span>
          <Button onClick={openExtensionOptions}>Cài đặt tài khoản phụ</Button>
        </Flex>
      }
    />
  );
}

/** How often each grid was posted to over time: the stretches between dated videos, newest first. */
function FrequencyView({ frequency }: { frequency: Stats["frequency"] }) {
  const grids = (
    [
      ["Reels", frequency.reel],
      ["Video", frequency.video],
    ] as const
  ).filter(([, grid]) => grid && grid.stretches.length);
  if (!grids.length) return null;
  const day = (iso: string) => formatDateTime(iso).slice(0, 10);
  return (
    <Flex vertical gap={4}>
      {grids.map(([label, grid]) => (
        <Typography.Text key={label} type="secondary">
          {label}:{" "}
          {grid!.stretches
            .map((stretch) => `${day(stretch.from)}–${day(stretch.to)}: ${stretch.videos_per_week ?? "—"}/tuần`)
            .join(" · ")}
        </Typography.Text>
      ))}
    </Flex>
  );
}

function ScanDetailView({ scanId }: { scanId: number }) {
  const [detail, setDetail] = useState<ScanDetail | null>(null);
  const [failed, setFailed] = useState("");
  useEffect(() => {
    api<ScanDetail>(`/competitors/scans/${scanId}`)
      .then(setDetail)
      .catch((err) => setFailed(errorMessage(err)));
  }, [scanId]);
  if (failed) return <Typography.Text type="danger">{failed}</Typography.Text>;
  if (!detail) return <Typography.Text type="secondary">Đang tải…</Typography.Text>;
  const { stats } = detail;
  return (
    <Flex vertical gap={12}>
      <Descriptions size="small" column={{ xs: 1, sm: 2, lg: 4 }}>
        <Descriptions.Item label="Số video">{number.format(stats.videos)}</Descriptions.Item>
        <Descriptions.Item label="Tổng view">{number.format(stats.total_views)}</Descriptions.Item>
        <Descriptions.Item label="Trung vị">
          {stats.median_views === null ? "—" : number.format(stats.median_views)}
        </Descriptions.Item>
        <Descriptions.Item label="Top 10 chiếm">
          {stats.top10_share === null ? "—" : `${Math.round(stats.top10_share * 1000) / 10}%`}
        </Descriptions.Item>
        {stats.buckets.map((bucket) => (
          <Descriptions.Item key={bucket.label} label={bucket.label}>
            {number.format(bucket.videos)} video
          </Descriptions.Item>
        ))}
        <Descriptions.Item label="Reels · Video">
          {number.format(stats.by_type.reel)} · {number.format(stats.by_type.video)}
        </Descriptions.Item>
        <Descriptions.Item label="Video/tuần">{stats.videos_per_week ?? "—"}</Descriptions.Item>
        <Descriptions.Item label="Đăng gần nhất">
          {stats.newest_posted_at ? formatDayTime(stats.newest_posted_at) : "—"}
        </Descriptions.Item>
        <Descriptions.Item label="Cũ nhất đọc được">
          {stats.oldest_posted_at ? formatDateTime(stats.oldest_posted_at).slice(0, 10) : "—"}
        </Descriptions.Item>
      </Descriptions>
      <FrequencyView frequency={stats.frequency} />
      <Table<TopVideo>
        data-testid="competitor-top-videos"
        size="small"
        rowKey="fb_video_id"
        pagination={false}
        dataSource={detail.top_videos}
        columns={[
          { title: "Hạng", dataIndex: "rank", width: 70 },
          {
            title: "View",
            key: "views",
            width: 140,
            render: (_, video) => (video.views === null ? "—" : number.format(video.views)),
          },
          {
            title: "Video",
            key: "url",
            render: (_, video) => (
              <Flex vertical gap={2}>
                <Typography.Link href={video.url} target="_blank" rel="noreferrer">
                  {video.url}
                </Typography.Link>
                {(video.posted_at || video.type === "video") && (
                  <Typography.Text type="secondary">
                    {video.type === "video" ? "Video · " : ""}
                    {video.posted_at ? `Đăng ${formatDayTime(video.posted_at)} (${video.posted_raw ?? ""})` : ""}
                  </Typography.Text>
                )}
                {video.caption && (
                  <Typography.Paragraph
                    ellipsis={{ rows: 2, expandable: true, symbol: "Xem thêm" }}
                    style={{ margin: 0 }}
                  >
                    {video.caption}
                  </Typography.Paragraph>
                )}
                {video.audio_name && <Typography.Text type="secondary">Âm thanh: {video.audio_name}</Typography.Text>}
              </Flex>
            ),
          },
          {
            title: "Cảm xúc · Bình luận · Chia sẻ",
            key: "counts",
            width: 220,
            render: (_, video) =>
              [video.reactions, video.comments, video.shares]
                .map((value) => (value === null ? "—" : number.format(value)))
                .join(" · "),
          },
        ]}
      />
      <Typography.Text type="secondary">
        {stats.limits.join(" ")}
        {!detail.report &&
          " Nhờ Claude (kết nối MCP Reels Studio) phân tích chủ đề, nỗi đau và đề xuất nội dung, rồi lưu báo cáo."}
      </Typography.Text>
      {detail.report && <ReportView report={detail.report} />}
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
          {report.written_by ? `${report.written_by} · ` : ""}
          {report.created_at ? formatDateTime(report.created_at) : ""}
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
