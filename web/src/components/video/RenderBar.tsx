"use client";

import { PlayCircleOutlined, RobotOutlined, VideoCameraOutlined } from "@ant-design/icons";
import { Button, Flex, Space, Spin, Typography } from "antd";
import { useEffect, useState } from "react";
import type { VideoDetail } from "@/lib/api";
import GooglePhotosButton from "./GooglePhotosButton";
import ImageProviderMenu from "./ImageProviderMenu";
import { COLORS } from "@/app/theme";

/** Scrolls to the first red reason on the page: a whole-video one, else a scene's. */
export function showFirstBlocking() {
  document
    .querySelector('[data-testid="video-blocking"], [data-testid="scene-blocking"]')
    ?.scrollIntoView({ behavior: "smooth", block: "center" });
}

/** 75 -> "1:15". */
export function clock(seconds: number) {
  const whole = Math.max(0, Math.round(seconds));
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

/** Seconds since `startedAt`, ticking every second while it is set; 0 before the job starts. */
function useElapsed(startedAt: string | null) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!startedAt) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [startedAt]);
  // A clock a little ahead of the server's would read below zero for a moment.
  return startedAt ? Math.max(0, (now - Date.parse(startedAt)) / 1000) : 0;
}

/**
 * The editor's action bar, stuck to the bottom of the screen so "Render" is in reach however far the member has
 * scrolled down the scenes. It says what still blocks the render and jumps to it, which job is running and for how
 * long, and how the MP4 stands against the scenes.
 */
export default function RenderBar({
  video,
  busy,
  jobName,
  onRender,
  onGenerateImages,
  onShowBlocking = showFirstBlocking,
  onPreview,
  onCancelJob,
}: {
  video: VideoDetail;
  busy: boolean;
  /** The running or queued job's name ("Tạo ảnh AI"), for the line that says what the video waits for. */
  jobName?: string;
  onRender: () => void;
  /** Without a provider: the team's default; with one: picked from the button's arrow for this press. */
  onGenerateImages: (provider?: "cloudflare" | "gemini") => void;
  /** Opens what hides the first reason (a collapsed scene) before scrolling to it. */
  onShowBlocking?: () => void;
  /** "Xem trước": the video played in the browser, before any render. */
  onPreview?: () => void;
  /** Cancels the queued job, which has not started yet. */
  onCancelJob?: () => void;
}) {
  const scenes = [video.title_scene, ...video.scenes].filter((scene) => scene !== null);
  const blocking = video.video_blocking.length + scenes.reduce((sum, scene) => sum + scene.blocking.length, 0);
  const missingPhotos = scenes.some((scene) => !scene.has_image && !scene.video);
  const job = video.active_job;
  const rendering = job?.kind === "render";
  const elapsed = useElapsed(job?.status === "running" ? job.started_at : null);
  const seconds = scenes.reduce((sum, scene) => sum + scene.fitted_seconds, 0);

  let status;
  if (job) {
    const running = job.status === "running";
    const label = rendering ? "Đang render video" : `Đang chạy: ${jobName ?? "job"}`;
    status = (
      <Flex gap={8} align="center" wrap data-testid="render-bar-job">
        <Spin size="small" />
        <Typography.Text>
          {running ? (
            <>
              {label}… {clock(elapsed)}
              {/* The last render's time is the best guess at this one's. */}
              {rendering && video.mp4 && ` / khoảng ${clock(video.mp4.render_seconds)}`}
            </>
          ) : (
            `Đang chờ tới lượt: ${rendering ? "Render" : (jobName ?? "job")}`
          )}
        </Typography.Text>
        {!rendering && <Typography.Text type="secondary">Xong mới render được.</Typography.Text>}
        {!running && onCancelJob && (
          <Button size="small" disabled={busy} onClick={onCancelJob}>
            Hủy
          </Button>
        )}
      </Flex>
    );
  } else if (blocking > 0) {
    status = (
      <Button type="link" danger style={{ padding: 0 }} onClick={onShowBlocking}>
        Còn {blocking} lỗi cần sửa, xem lỗi đầu tiên
      </Button>
    );
  } else if (!video.mp4) {
    status = <Typography.Text>Sẵn sàng render.</Typography.Text>;
  } else if (video.mp4_outdated) {
    status = (
      <Typography.Text type="warning" data-testid="render-bar-outdated">
        Bản sửa chưa có trong MP4, bấm “Render lại”.
      </Typography.Text>
    );
  } else {
    status = <Typography.Text type="secondary">MP4 đã theo bản mới nhất.</Typography.Text>;
  }

  return (
    <div
      data-testid="render-bar"
      style={{
        position: "sticky",
        bottom: 0,
        zIndex: 5,
        marginTop: 16,
        padding: "10px 16px",
        background: "#fff",
        border: `1px solid ${COLORS.border}`,
        borderRadius: 8,
        boxShadow: "0 -4px 12px rgba(0, 0, 0, 0.06)",
      }}
    >
      <Flex wrap gap={8} align="center" justify="space-between">
        <Flex vertical gap={2} style={{ minWidth: 0 }}>
          {status}
          <Typography.Text type="secondary" style={{ fontSize: 12 }} data-testid="render-bar-summary">
            {video.scenes.length} cảnh · dài khoảng {Math.round(seconds)} giây ·{" "}
            {video.voice_enabled ? "có giọng đọc" : "không giọng đọc"}
            {video.mp4 ? ` · MP4 hiện tại ${video.mp4.seconds.toFixed(1)} giây` : " · chưa có MP4"}
          </Typography.Text>
        </Flex>
        <Flex wrap gap={8}>
          {missingPhotos && <GooglePhotosButton video={video} disabled={busy || video.locked} />}
          {missingPhotos && (
            <Space.Compact>
              <Button icon={<RobotOutlined />} disabled={busy || video.locked} onClick={() => onGenerateImages()}>
                Tạo ảnh AI cho cảnh thiếu
              </Button>
              <ImageProviderMenu disabled={busy || video.locked} onPick={onGenerateImages} />
            </Space.Compact>
          )}
          {onPreview && (
            <Button icon={<PlayCircleOutlined />} onClick={onPreview}>
              Xem trước
            </Button>
          )}
          <Button
            type="primary"
            icon={<VideoCameraOutlined />}
            loading={rendering}
            disabled={!video.can_render || busy}
            onClick={onRender}
          >
            {video.mp4 ? "Render lại" : "Render"}
          </Button>
        </Flex>
      </Flex>
    </div>
  );
}
