"use client";

import { Flex, Modal, Switch, Typography } from "antd";
import { useState } from "react";
import type { SceneData } from "@/lib/api";
import { silentVideo } from "./silentVideo";
import { FRAME_HEIGHT, FRAME_WIDTH, placeBox } from "./TextPositionModal";

const STAGE_HEIGHT = "min(72vh, 720px)";
const percent = (value: number, of: number) => `${(value / of) * 100}%`;

/**
 * "Xem": the scene large, in the 9:16 frame: the frame without text (or the clip, playing the part the scene uses
 * at its speed, muted like the render) and, switched on by default, the exact text box over it where the render
 * puts it.
 */
export default function SceneViewer({ scene, onClose }: { scene: SceneData; onClose: () => void }) {
  const [showText, setShowText] = useState(true);
  const [box, setBox] = useState<{ width: number; height: number } | null>(null);
  const clip = scene.video;
  const corner = box ? placeBox(box, scene.placed_at, scene.is_title) : null;
  // The part of the clip the scene plays: its seconds at its speed, from its start.
  const clipEnd = clip ? clip.start + scene.seconds * clip.speed : 0;

  return (
    <Modal
      open
      centered
      title={scene.is_title ? "Xem cảnh tiêu đề" : "Xem cảnh"}
      footer={null}
      width="auto"
      styles={{ body: { display: "flex", justifyContent: "center" } }}
      onCancel={onClose}
      destroyOnHidden
    >
      <Flex vertical gap={12} align="center">
        <div
          data-testid="scene-viewer"
          style={{
            position: "relative",
            height: STAGE_HEIGHT,
            aspectRatio: "9 / 16",
            maxWidth: "calc(100vw - 64px)",
            overflow: "hidden",
            borderRadius: 8,
            background: "#141414",
          }}
        >
          {clip ? (
            <video
              ref={silentVideo}
              src={clip.url}
              autoPlay
              muted
              playsInline
              aria-label="Video của cảnh"
              onLoadedMetadata={(event) => {
                event.currentTarget.currentTime = clip.start;
                event.currentTarget.playbackRate = clip.speed;
              }}
              onTimeUpdate={(event) => {
                if (event.currentTarget.currentTime >= Math.min(clipEnd, clip.seconds)) {
                  event.currentTarget.currentTime = clip.start;
                  void event.currentTarget.play();
                }
              }}
              style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }}
            />
          ) : (
            // eslint-disable-next-line @next/next/no-img-element -- drawn by the api with the renderer's own code
            <img
              src={scene.frame_url ?? scene.image_url ?? ""}
              alt="Ảnh của cảnh"
              style={{
                width: "100%",
                height: "100%",
                // The frame is the render's own 9:16 crop; the stored photo alone is shown whole.
                objectFit: scene.frame_url ? "cover" : "contain",
                display: "block",
              }}
            />
          )}
          {scene.textbox_url && (
            // eslint-disable-next-line @next/next/no-img-element -- the exact box image the render overlays
            <img
              src={scene.textbox_url}
              alt=""
              data-testid="scene-viewer-text"
              onLoad={(event) =>
                setBox({ width: event.currentTarget.naturalWidth, height: event.currentTarget.naturalHeight })
              }
              style={{
                position: "absolute",
                left: corner ? percent(corner[0], FRAME_WIDTH) : 0,
                top: corner ? percent(corner[1], FRAME_HEIGHT) : 0,
                width: box ? percent(box.width, FRAME_WIDTH) : "auto",
                visibility: showText && corner ? "visible" : "hidden",
                pointerEvents: "none",
              }}
            />
          )}
        </div>
        <Flex align="center" gap={8}>
          <Switch
            checked={showText && !!scene.textbox_url}
            disabled={!scene.textbox_url}
            onChange={setShowText}
            aria-label="Chữ trên màn hình"
          />
          <Typography.Text>{scene.textbox_url ? "Chữ trên màn hình" : "Cảnh này không có chữ"}</Typography.Text>
        </Flex>
      </Flex>
    </Modal>
  );
}
