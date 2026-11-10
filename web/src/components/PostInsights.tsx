"use client";

import { LineChartOutlined } from "@ant-design/icons";
import { Button, Col, Empty, Modal, Row, Statistic, Table, Tooltip, Typography } from "antd";
import { useState } from "react";
import { COLORS } from "@/app/theme";
import { formatCount, formatRate } from "@/components/PostMetrics";
import { formatDateTime, type Post, type PostNumbers, type SceneMark } from "@/lib/api";

const decimal = new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 1 });

/** "8,4 giây", or "—". */
function formatSeconds(value: number | null): string {
  return value === null ? "—" : `${decimal.format(value)} giây`;
}

/** "3 giờ 12 phút", "12 phút" or "40 giây", or "—". */
function formatDuration(seconds: number | null): string {
  if (seconds === null) return "—";
  if (seconds < 60) return `${seconds} giây`;
  const minutes = Math.round(seconds / 60);
  const hours = Math.floor(minutes / 60);
  return hours > 0 ? `${hours} giờ ${minutes % 60} phút` : `${minutes} phút`;
}

/** The share still watching at `at` (0–1 of the reel), the curve's points spread evenly from start to end. */
export function retentionAt(curve: number[], at: number): number {
  if (curve.length === 1) return curve[0];
  const position = Math.min(Math.max(at, 0), 1) * (curve.length - 1);
  const before = Math.floor(position);
  const after = Math.min(before + 1, curve.length - 1);
  return curve[before] + (curve[after] - curve[before]) * (position - before);
}

type SceneRow = SceneMark & { kept: number; lost: number; worst: boolean };

/** Each scene with the share still watching when it starts and the share lost while it plays. */
export function sceneDropOff(curve: number[], scenes: SceneMark[], length: number): SceneRow[] {
  const rows = scenes.map((scene) => {
    const kept = retentionAt(curve, scene.start / length);
    return { ...scene, kept, lost: Math.max(0, kept - retentionAt(curve, scene.end / length)), worst: false };
  });
  const worst = rows.reduce<SceneRow | null>((top, row) => (top === null || row.lost > top.lost ? row : top), null);
  if (worst && worst.lost > 0) worst.worst = true;
  return rows;
}

const WIDTH = 640;
const HEIGHT = 220;
const PAD = { left: 40, right: 12, top: 26, bottom: 24 };

/** The retention curve over the reel, with each scene of the posted MP4 as a band behind it. */
function RetentionChart({ curve, scenes, length }: { curve: number[]; scenes: SceneMark[]; length: number | null }) {
  const plotWidth = WIDTH - PAD.left - PAD.right;
  const plotHeight = HEIGHT - PAD.top - PAD.bottom;
  const x = (fraction: number) => PAD.left + fraction * plotWidth;
  const y = (share: number) => PAD.top + (1 - share) * plotHeight;
  const step = curve.length > 1 ? 1 / (curve.length - 1) : 1;
  const line = curve.map((share, index) => `${x(index * step).toFixed(1)},${y(share).toFixed(1)}`).join(" ");
  const area = `${x(0)},${y(0)} ${line} ${x(curve.length > 1 ? 1 : 0)},${y(0)}`;
  return (
    <svg
      viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
      width="100%"
      role="img"
      aria-label="Biểu đồ giữ chân người xem"
      data-testid="retention-chart"
      style={{ display: "block" }}
    >
      {length !== null &&
        scenes.map((scene, index) => (
          <g key={scene.label}>
            <rect
              x={x(scene.start / length)}
              y={PAD.top}
              width={Math.max(0, x(scene.end / length) - x(scene.start / length))}
              height={plotHeight}
              fill={index % 2 === 0 ? COLORS.muted : COLORS.surface}
            />
            <text
              x={x((scene.start + scene.end) / 2 / length)}
              y={PAD.top - 8}
              textAnchor="middle"
              fontSize={11}
              fill={COLORS.textSecondary}
            >
              {scene.label === "Tiêu đề" ? "TĐ" : scene.label.replace("Cảnh ", "C")}
            </text>
          </g>
        ))}
      {[0, 0.25, 0.5, 0.75, 1].map((share) => (
        <g key={share}>
          <line x1={PAD.left} x2={WIDTH - PAD.right} y1={y(share)} y2={y(share)} stroke={COLORS.border} />
          <text x={PAD.left - 6} y={y(share) + 4} textAnchor="end" fontSize={11} fill={COLORS.textSecondary}>
            {Math.round(share * 100)}%
          </text>
        </g>
      ))}
      <polygon points={area} fill={COLORS.primaryBg} opacity={0.8} />
      <polyline points={line} fill="none" stroke={COLORS.brand} strokeWidth={2.5} strokeLinejoin="round" />
      <text x={PAD.left} y={HEIGHT - 6} fontSize={11} fill={COLORS.textSecondary}>
        0 giây
      </text>
      <text x={WIDTH - PAD.right} y={HEIGHT - 6} textAnchor="end" fontSize={11} fill={COLORS.textSecondary}>
        {length !== null ? `${decimal.format(length)} giây` : "hết video"}
      </text>
    </svg>
  );
}

function Numbers({ numbers }: { numbers: PostNumbers }) {
  const items: { title: string; value: string; tip?: string; testId?: string }[] = [
    { title: "Lượt xem", value: formatCount(numbers.views), tip: "Mọi lượt phát, tính cả xem lại" },
    {
      title: "Xem trung bình",
      value: formatSeconds(numbers.avg_watch_seconds),
      tip: "Mỗi lượt phát, tính cả xem lại nên có thể dài hơn video",
      testId: "insight-avg-watch",
    },
    {
      title: "% thời lượng",
      value: formatRate(numbers.watch_ratio),
      tip: "Xem trung bình chia cho độ dài MP4 đã đăng",
      testId: "insight-watch-ratio",
    },
    { title: "Tiếp cận", value: formatCount(numbers.reach), tip: "Số người đã thấy reel, Facebook ước tính" },
    { title: "Lượt phát đầu", value: formatCount(numbers.plays), tip: "Không tính xem lại" },
    { title: "Xem lại", value: formatCount(numbers.replays) },
    { title: "Tổng thời gian xem", value: formatDuration(numbers.view_time_seconds) },
    { title: "Theo dõi mới", value: formatCount(numbers.followers), tip: "Người theo dõi Page nhờ reel này" },
    { title: "Share", value: formatCount(numbers.shares) },
    { title: "Bình luận", value: formatCount(numbers.comments) },
    { title: "Cảm xúc", value: formatCount(numbers.reactions) },
  ];
  return (
    <Row gutter={[16, 16]}>
      {items.map((item) => (
        <Col key={item.title} xs={12} sm={8} md={6}>
          <Tooltip title={item.tip}>
            <div data-testid={item.testId}>
              <Statistic title={item.title} value={item.value} styles={{ content: { fontSize: 20 } }} />
            </div>
          </Tooltip>
        </Col>
      ))}
    </Row>
  );
}

/** "Phân tích": a post's full numbers from Facebook, and how long viewers stayed, scene by scene. */
export default function PostInsights({ post, compact = false }: { post: Post; compact?: boolean }) {
  const [open, setOpen] = useState(false);
  const { latest, length_seconds: length, scenes } = post.metrics;
  if (!latest) return null;
  const curve = latest.retention;
  const rows = curve && length !== null && scenes.length > 0 ? sceneDropOff(curve, scenes, length) : [];
  return (
    <>
      <Tooltip title={compact ? "Phân tích bài đăng" : undefined}>
        <Button
          size="small"
          type={compact ? "text" : "default"}
          icon={<LineChartOutlined />}
          aria-label="Phân tích bài đăng"
          onClick={(event) => {
            event.stopPropagation();
            setOpen(true);
          }}
        >
          {compact ? null : "Phân tích"}
        </Button>
      </Tooltip>
      <Modal
        open={open}
        title="Phân tích bài đăng"
        footer={null}
        width={760}
        onCancel={() => setOpen(false)}
        destroyOnHidden
      >
        <div data-testid="post-insights" onClick={(event) => event.stopPropagation()}>
          <Typography.Paragraph type="secondary">
            {[post.fanpage, `Đo lúc ${formatDateTime(latest.measured_at)}`].filter(Boolean).join(", ")}. Số do Facebook
            tính, cộng dồn từ lúc đăng.
          </Typography.Paragraph>
          <Numbers numbers={latest} />
          <Typography.Title level={5} style={{ marginTop: 24 }}>
            Giữ chân người xem
          </Typography.Title>
          {curve ? (
            <>
              <RetentionChart curve={curve} scenes={scenes} length={length} />
              <Typography.Paragraph type="secondary" style={{ fontSize: 12, marginTop: 4 }}>
                Phần trăm lượt phát còn xem tới từng thời điểm. Các mốc của Facebook được chia đều theo thời lượng
                video.
              </Typography.Paragraph>
              {rows.length > 0 ? (
                <Table
                  size="small"
                  pagination={false}
                  rowKey="label"
                  dataSource={rows}
                  data-testid="scene-drop-off"
                  scroll={{ x: "max-content" }}
                  columns={[
                    {
                      title: "Cảnh",
                      dataIndex: "label",
                      render: (label: string, row) =>
                        row.worst ? (
                          <Typography.Text type="danger" strong>
                            {label}, mất nhiều nhất
                          </Typography.Text>
                        ) : (
                          label
                        ),
                    },
                    {
                      title: "Thời gian",
                      render: (_, row) => `${decimal.format(row.start)}–${decimal.format(row.end)} giây`,
                    },
                    { title: "Còn xem lúc vào cảnh", render: (_, row) => formatRate(row.kept) },
                    { title: "Rời đi trong cảnh", render: (_, row) => formatRate(row.lost) },
                  ]}
                />
              ) : (
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  Bài này đăng trước khi app lưu mốc từng cảnh, nên chưa chia được theo cảnh.
                </Typography.Text>
              )}
            </>
          ) : (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description="Facebook chưa có đường giữ chân cho reel này. Thường có sau vài giờ, khi đủ lượt xem."
            />
          )}
        </div>
      </Modal>
    </>
  );
}
