"use client";

import { PlayCircleOutlined, RobotOutlined, VideoCameraOutlined } from "@ant-design/icons";
import { Button, Flex, Space, Typography } from "antd";
import type { VideoDetail } from "@/lib/api";
import ImageProviderMenu from "./ImageProviderMenu";

/** Scrolls to the first red reason on the page: a whole-video one, else a scene's. */
export function showFirstBlocking() {
  document
    .querySelector('[data-testid="video-blocking"], [data-testid="scene-blocking"]')
    ?.scrollIntoView({ behavior: "smooth", block: "center" });
}

/**
 * The editor's action bar, stuck to the bottom of the screen so "Render" is in reach however far the member has
 * scrolled down the scenes. It says what still blocks the render and jumps to it.
 */
export default function RenderBar({
  video,
  busy,
  onRender,
  onGenerateImages,
  onShowBlocking = showFirstBlocking,
  onPreview,
}: {
  video: VideoDetail;
  busy: boolean;
  onRender: () => void;
  /** Without a provider: the team's default; with one: picked from the button's arrow for this press. */
  onGenerateImages: (provider?: "cloudflare" | "gemini") => void;
  /** Opens what hides the first reason (a collapsed scene) before scrolling to it. */
  onShowBlocking?: () => void;
  /** "Xem trước": the video played in the browser, before any render. */
  onPreview?: () => void;
}) {
  const scenes = [video.title_scene, ...video.scenes].filter((scene) => scene !== null);
  const blocking = video.video_blocking.length + scenes.reduce((sum, scene) => sum + scene.blocking.length, 0);
  const missingPhotos = scenes.some((scene) => !scene.has_image && !scene.video);

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
        border: "1px solid #EDEDED",
        borderRadius: 8,
        boxShadow: "0 -4px 12px rgba(0, 0, 0, 0.06)",
      }}
    >
      <Flex wrap gap={8} align="center" justify="space-between">
        <div style={{ minWidth: 0 }}>
          {blocking > 0 ? (
            <Button type="link" danger style={{ padding: 0 }} onClick={onShowBlocking}>
              Còn {blocking} lỗi cần sửa, xem lỗi đầu tiên
            </Button>
          ) : (
            <Typography.Text type="secondary">
              {video.locked ? "Đang chạy job, chờ xong rồi render." : "Sẵn sàng render."}
            </Typography.Text>
          )}
        </div>
        <Flex wrap gap={8}>
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
          <Button type="primary" icon={<VideoCameraOutlined />} disabled={!video.can_render || busy} onClick={onRender}>
            Render
          </Button>
        </Flex>
      </Flex>
    </div>
  );
}
