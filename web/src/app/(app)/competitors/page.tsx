"use client";

import EmptyState from "@/components/EmptyState";
import PageHeader from "@/components/PageHeader";
import { DeleteOutlined, LinkOutlined, ReloadOutlined, SearchOutlined } from "@ant-design/icons";
import { Alert, App, Button, Card, Descriptions, Flex, Input, Popconfirm, Space, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useCallback, useEffect, useState } from "react";
import { api, errorMessage, formatDateTime } from "@/lib/api";
import { useCompetitorScanner, type CompetitorScan } from "@/lib/competitorScanner";
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
  limits: string[];
};

type TopVideo = { rank: number; fb_video_id: string; url: string; views: number | null; views_raw: string | null };
type ScanDetail = CompetitorScan & { stats: Stats; top_videos: TopVideo[] };

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
      await api("/competitors/scans", "POST", { url });
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
        const live = scanner.running?.scan.id === scan.id ? scanner.running.found : scan.videos_found;
        return (
          <Flex vertical gap={2}>
            <Space size={4}>
              <Tag color={STATUS[scan.status].color}>{STATUS[scan.status].label}</Tag>
              <Typography.Text>{number.format(live)} video</Typography.Text>
            </Space>
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
          <ScannerNotice version={scanner.version} ready={scanner.ready} />
        </Flex>
      </PageHeader>
      <Card styles={{ body: { padding: 0 } }}>
        <Table<Competitor>
          rowKey="id"
          columns={columns}
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
    </>
  );
}

function ScannerNotice({ version, ready }: { version: string; ready: boolean }) {
  if (ready) {
    return (
      <Typography.Text type="secondary">
        Tiện ích đã sẵn sàng. Giữ trang này mở: lượt quét (kể cả do Claude tạo qua MCP) chạy trong cửa sổ Facebook của
        Chrome này, cuộn chậm như người thật.
      </Typography.Text>
    );
  }
  return (
    <Alert
      type="info"
      showIcon
      message={version ? `Tiện ích bản ${version} chưa quét được đối thủ` : "Chưa thấy tiện ích Reels Studio"}
      description="Cài hoặc cập nhật tiện ích (thư mục extension/ của dự án, bản 1.1.0 trở lên) trong Chrome đã đăng nhập Facebook, rồi tải lại trang. Nên dùng tài khoản Facebook phụ: Facebook có thể hạn chế tài khoản bị cho là quét tự động."
    />
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
      </Descriptions>
      <Table<TopVideo>
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
              <Typography.Link href={video.url} target="_blank" rel="noreferrer">
                {video.url}
              </Typography.Link>
            ),
          },
        ]}
      />
      <Typography.Text type="secondary">
        {stats.limits.join(" ")} Nhờ Claude (kết nối MCP Reels Studio) phân tích chủ đề, nỗi đau và đề xuất nội dung.
      </Typography.Text>
    </Flex>
  );
}
