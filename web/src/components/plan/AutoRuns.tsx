"use client";

import { WarningOutlined } from "@ant-design/icons";
import { Alert, App, Button, Checkbox, Flex, Popconfirm, Tag, Typography } from "antd";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, errorMessage, formatDateTime, type AutoRun, type AutoRunStatus } from "@/lib/api";
import { usePolling } from "@/lib/polling";

const STATUS: Record<AutoRunStatus, { label: string; color?: string }> = {
  preparing: { label: "Đang dựng", color: "processing" },
  ready: { label: "Chờ duyệt", color: "orange" },
  approved: { label: "Đã duyệt", color: "green" },
  rejected: { label: "Không duyệt" },
  failed: { label: "Lỗi", color: "red" },
  skipped: { label: "Bỏ qua" },
};

const TIKTOK: Record<NonNullable<AutoRun["tiktok_state"]>, string> = {
  waiting: "TikTok: sẽ gửi nháp sau khi xếp lịch Facebook",
  sent: "TikTok: đã gửi nháp vào hộp thư TikTok",
  skipped: "TikTok: bỏ qua",
  failed: "TikTok: lỗi",
};

/** Today in Vietnam, "YYYY-MM-DD", whatever the browser's time zone. */
function vietnamToday(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Ho_Chi_Minh" }).format(new Date());
}

/** "Bán tự động" in the "Hôm nay" strip: what the worker prepared this morning for the group's Pages, and, for each
 * Page's owner, "Duyệt" (schedule the post at the idea's time, and send the TikTok draft unless skipped) or
 * "Không duyệt" (nothing is posted; the video is fixed by hand). */
export default function AutoRuns({ topicId }: { topicId: number }) {
  const { message } = App.useApp();
  const [runs, setRuns] = useState<AutoRun[] | null>(null);

  const load = useCallback(
    () =>
      api<AutoRun[]>(`/auto-runs?knowledge_topic_id=${topicId}&day=${vietnamToday()}`).then(setRuns, (err) => {
        setRuns([]);
        message.error(errorMessage(err));
      }),
    [topicId, message],
  );
  useEffect(() => {
    void load();
  }, [load]);
  // The worker starts runs at the Page's time and moves them on between jobs: the strip follows while it is open.
  usePolling(load, 10_000);

  if (!runs || runs.length === 0) {
    return null;
  }
  return (
    <Flex vertical gap={8} data-testid="auto-runs" style={{ marginTop: 6 }}>
      <Typography.Text strong style={{ fontSize: 13 }}>
        Bán tự động hôm nay
      </Typography.Text>
      {runs.map((run) => (
        <RunRow
          key={run.id}
          run={run}
          onRun={(saved) => setRuns(runs.map((row) => (row.id === saved.id ? saved : row)))}
        />
      ))}
    </Flex>
  );
}

function RunRow({ run, onRun }: { run: AutoRun; onRun: (run: AutoRun) => void }) {
  const { message } = App.useApp();
  const [skipTikTok, setSkipTikTok] = useState(false);
  const [busy, setBusy] = useState(false);
  const status = STATUS[run.status];

  async function decide(path: "approve" | "reject") {
    setBusy(true);
    try {
      const saved = await api<AutoRun>(
        `/auto-runs/${run.id}/${path}`,
        "POST",
        path === "approve" ? { skip_tiktok: skipTikTok } : undefined,
      );
      onRun(saved);
      message.success(path === "approve" ? "Đã duyệt, bài Facebook đã được xếp lịch" : "Đã đánh dấu không duyệt");
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Flex vertical gap={6} data-testid="auto-run" style={{ border: "1px solid #f0f0f0", borderRadius: 8, padding: 10 }}>
      <Flex wrap align="center" gap={8}>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          {run.fanpage.name}
        </Typography.Text>
        <Typography.Text strong style={{ flex: "1 1 200px", minWidth: 0 }}>
          {run.idea_topic || "Không có ý tưởng"}
        </Typography.Text>
        <Tag color={status.color} style={{ marginInlineEnd: 0 }} data-testid="auto-run-status">
          {status.label}
        </Tag>
        {run.video && (
          <Link prefetch={false} href={`/videos/${run.video.id}`}>
            Mở video
          </Link>
        )}
      </Flex>
      {run.reason && (
        <Typography.Text
          type={run.status === "failed" ? "danger" : "secondary"}
          style={{ fontSize: 12 }}
          data-testid="auto-run-reason"
        >
          {run.reason}
        </Typography.Text>
      )}
      {run.banned.length > 0 && (
        <Alert
          type="warning"
          showIcon
          icon={<WarningOutlined />}
          title={`Kịch bản dính từ cấm: ${run.banned.join("; ")}`}
          data-testid="auto-run-banned"
        />
      )}
      {run.status === "ready" && run.video?.mp4_url && (
        <video
          src={run.video.mp4_url}
          controls
          preload="metadata"
          style={{ width: 180, aspectRatio: "9 / 16", borderRadius: 8, background: "#000" }}
          aria-label={`Bản render của ${run.idea_topic}`}
        />
      )}
      {run.status === "ready" && run.video && (
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          Giọng: {run.video.voice_id || "mặc định"} · Nhạc: {run.video.music ?? "không có"}
          {run.tiktok_video_id && (
            <>
              {" "}
              ·{" "}
              <Link prefetch={false} href={`/videos/${run.tiktok_video_id}`}>
                Bản TikTok riêng
              </Link>
            </>
          )}{" "}
          · Ảnh từng cảnh và kịch bản xem ở trang video
        </Typography.Text>
      )}
      {run.status === "ready" && run.can_decide && (
        <Flex wrap align="center" gap={8}>
          {run.tiktok_ready ? (
            <Checkbox checked={skipTikTok} onChange={(event) => setSkipTikTok(event.target.checked)}>
              Bỏ qua TikTok cho video này
            </Checkbox>
          ) : (
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              Không gửi TikTok: {run.tiktok_problem}
            </Typography.Text>
          )}
          <Button type="primary" size="small" loading={busy} onClick={() => decide("approve")}>
            Duyệt
          </Button>
          <Popconfirm
            title="Không duyệt video này?"
            description="Không đăng gì cả; video để lại cho bạn sửa tay."
            okText="Không duyệt"
            cancelText="Huỷ"
            onConfirm={() => decide("reject")}
          >
            <Button size="small" disabled={busy}>
              Không duyệt
            </Button>
          </Popconfirm>
        </Flex>
      )}
      {run.status === "ready" && !run.can_decide && (
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          Chờ chủ Page duyệt
        </Typography.Text>
      )}
      {run.status === "approved" && (
        <Typography.Text type="secondary" style={{ fontSize: 12 }} data-testid="auto-run-approved">
          Facebook: hẹn đăng {run.post_at ? formatDateTime(run.post_at) : ""}
          {run.tiktok_state && ` · ${TIKTOK[run.tiktok_state]}`}
          {run.tiktok_reason && ` (${run.tiktok_reason})`}
        </Typography.Text>
      )}
    </Flex>
  );
}
