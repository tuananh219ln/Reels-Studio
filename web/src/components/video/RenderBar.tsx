"use client";

import { PlayCircleOutlined, RobotOutlined, VideoCameraOutlined } from "@ant-design/icons";
import { Button, Flex, Space, Spin, Typography } from "antd";
import { useEffect, useState } from "react";
import type { VideoDetail } from "@/lib/api";
import GooglePhotosButton from "./GooglePhotosButton";
import ImageProviderMenu from "./ImageProviderMenu";
import { formatDecimal } from "@/lib/api";

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

const scenesOf = (video: VideoDetail) => [video.title_scene, ...video.scenes].filter((scene) => scene !== null);

/**
 * How the video stands against a render, in the page's fixed header: what still blocks it (and a jump to it), which
 * job is running and for how long, or how the MP4 stands against the scenes; then a short summary of the video.
 */
export function RenderStatus({
  video,
  busy,
  jobName,
  onShowBlocking = showFirstBlocking,
  onCancelJob,
  compact = false,
}: {
  video: VideoDetail;
  busy: boolean;
  /** The running or queued job's name ("Tạo ảnh AI"), for the line that says what the video waits for. */
  jobName?: string;
  /** Opens what hides the first reason (a collapsed scene) before scrolling to it. */
  onShowBlocking?: () => void;
  /** Cancels the queued job, which has not started yet. */
  onCancelJob?: () => void;
  /** A phone: the summary is left out. */
  compact?: boolean;
}) {
  const scenes = scenesOf(video);
  const blocking = video.video_blocking.length + scenes.reduce((sum, scene) => sum + scene.blocking.length, 0);
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
        <Typography.Text style={{ fontSize: 13 }}>
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
        {!rendering && (
          <Typography.Text type="secondary" style={{ fontSize: 13 }}>
            Xong mới render được.
          </Typography.Text>
        )}
        {!running && onCancelJob && (
          <Button size="small" disabled={busy} onClick={onCancelJob}>
            Hủy
          </Button>
        )}
      </Flex>
    );
  } else if (blocking > 0) {
    status = (
      <Button type="link" danger size="small" style={{ padding: 0 }} onClick={onShowBlocking}>
        Còn {blocking} lỗi cần sửa, xem lỗi đầu tiên
      </Button>
    );
  } else if (!video.mp4) {
    status = <Typography.Text style={{ fontSize: 13 }}>Sẵn sàng render.</Typography.Text>;
  } else if (video.mp4_outdated) {
    status = (
      <Typography.Text type="warning" style={{ fontSize: 13 }} data-testid="render-bar-outdated">
        Bản sửa chưa có trong MP4, bấm “Render lại”.
      </Typography.Text>
    );
  } else {
    status = (
      <Typography.Text type="secondary" style={{ fontSize: 13 }}>
        MP4 đã theo bản mới nhất.
      </Typography.Text>
    );
  }

  return (
    <Flex wrap gap={8} align="center" style={{ minWidth: 0 }}>
      {status}
      <Typography.Text
        type="secondary"
        style={{ fontSize: 12, display: compact ? "none" : undefined }}
        data-testid="render-bar-summary"
      >
        {video.scenes.length} cảnh, dài khoảng {Math.round(seconds)} giây,{" "}
        {video.voice_enabled ? "có giọng đọc" : "không giọng đọc"}
        {video.mp4 ? `, MP4 hiện tại ${formatDecimal(video.mp4.seconds)} giây` : ", chưa có MP4"}
      </Typography.Text>
    </Flex>
  );
}

/** The header's actions on the render: the photo helpers while a scene has none, "Xem trước", then "Render". */
export function RenderButtons({
  video,
  busy,
  onRender,
  onGenerateImages,
  onPreview,
}: {
  video: VideoDetail;
  busy: boolean;
  onRender: () => void;
  /** Without a provider: the team's default; with one: picked from the button's arrow for this press. */
  onGenerateImages: (provider?: "cloudflare" | "gemini") => void;
  /** "Xem trước": the video played in the browser, before any render. */
  onPreview?: () => void;
}) {
  const missingPhotos = scenesOf(video).some((scene) => !scene.has_image && !scene.video);
  const rendering = video.active_job?.kind === "render";
  return (
    <>
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
    </>
  );
}
