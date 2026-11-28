"use client";

import { Button, Flex, Modal, Slider, Typography } from "antd";
import { useRef, useState } from "react";
import { COLORS } from "@/app/theme";
import type { VideoDetail, VideoLayout } from "@/lib/api";
import { badgeStyle } from "./logoBadge";
import { FRAME_HEIGHT, FRAME_WIDTH, placeBox, shownAt } from "./TextPositionModal";

/** What the window saves into the video's options: the logo ring's top-left corner and diameter; null: the usual. */
export type LogoPlace = { logo_position: [number, number] | null; logo_size: number | null };

const SHOWN_WIDTH = 270; // the frame on screen, a quarter of its size
const SCALE = SHOWN_WIDTH / FRAME_WIDTH;
const STEP = 10; // frame pixels an arrow key moves the logo
const MIN_SIZE = 80; // reels_render.layout.LOGO_MIN_SIZE and LOGO_MAX_SIZE
const MAX_SIZE = 240;

type Logo = Pick<VideoLayout["logo"], "x" | "y" | "size">;

/** The logo kept inside the video's safe zone (reels_render.layout.logo_box). */
function keep({ x, y, size }: Logo, layout: VideoLayout): Logo {
  return {
    x: Math.round(Math.max(layout.text_left, Math.min(x, layout.text_right - size))),
    y: Math.round(Math.max(layout.text_top_min, Math.min(y, layout.subtitle_bottom - size))),
    size,
  };
}

/**
 * "Vị trí & cỡ" of the logo: dragged (mouse, touch or arrow keys) over the first content scene with its text, inside
 * the video's safe zone, and resized. One place for the whole video, so it stays still through every scene.
 */
export default function LogoPositionModal({
  video,
  badge,
  onClose,
  onSave,
}: {
  video: VideoDetail;
  badge: string;
  onClose: () => void;
  onSave: (place: LogoPlace) => void;
}) {
  const layout = video.layout;
  const [logo, setLogo] = useState<Logo>(layout.logo);
  const [box, setBox] = useState<{ width: number; height: number } | null>(null);
  const drag = useRef<{ pointer: [number, number]; from: Logo } | null>(null);
  const scene = video.scenes.find((one) => one.frame_url) ?? null;
  const corner = scene && box ? placeBox(box, shownAt(scene), false, scene.text_area) : null;
  const scaled = (value: number) => value * SCALE;

  function move(event: React.PointerEvent<HTMLImageElement>) {
    const start = drag.current;
    if (start) {
      const x = start.from.x + (event.clientX - start.pointer[0]) / SCALE;
      const y = start.from.y + (event.clientY - start.pointer[1]) / SCALE;
      setLogo(keep({ x, y, size: start.from.size }, layout));
    }
  }

  function key(event: React.KeyboardEvent) {
    const steps: Record<string, [number, number]> = {
      ArrowUp: [0, -1],
      ArrowDown: [0, 1],
      ArrowLeft: [-1, 0],
      ArrowRight: [1, 0],
    };
    const step = steps[event.key];
    if (step) {
      event.preventDefault();
      setLogo(keep({ ...logo, x: logo.x + step[0] * STEP, y: logo.y + step[1] * STEP }, layout));
    }
  }

  return (
    <Modal open title="Vị trí và cỡ logo" onCancel={onClose} centered width={420} footer={null} destroyOnHidden>
      <Flex vertical gap={12} align="center">
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          Kéo logo (hoặc dùng phím mũi tên) trong khung nét đứt. Logo đứng một chỗ cho cả video, trừ cảnh tiêu đề.
        </Typography.Text>
        <div
          data-testid="logo-frame"
          style={{
            position: "relative",
            width: SHOWN_WIDTH,
            height: scaled(FRAME_HEIGHT),
            overflow: "hidden",
            borderRadius: 6,
            background: "#222",
            touchAction: "none",
          }}
        >
          {scene?.frame_url && (
            // eslint-disable-next-line @next/next/no-img-element -- drawn by the api, like the previews
            <img src={scene.frame_url} alt="" style={{ position: "absolute", inset: 0, width: "100%" }} />
          )}
          {scene?.textbox_url && (
            // eslint-disable-next-line @next/next/no-img-element -- the exact box the renderer overlays
            <img
              src={scene.textbox_url}
              alt=""
              draggable={false}
              onLoad={(event) =>
                setBox({ width: event.currentTarget.naturalWidth, height: event.currentTarget.naturalHeight })
              }
              style={{
                position: "absolute",
                left: corner ? scaled(corner[0]) : 0,
                top: corner ? scaled(corner[1]) : 0,
                width: box ? scaled(box.width) : undefined,
                visibility: corner ? "visible" : "hidden",
              }}
            />
          )}
          <div
            style={{
              position: "absolute",
              left: scaled(layout.text_left),
              top: scaled(layout.text_top_min),
              width: scaled(layout.text_right - layout.text_left),
              height: scaled(layout.subtitle_bottom - layout.text_top_min),
              border: "1px dashed rgba(255,255,255,0.7)",
              boxSizing: "border-box",
              pointerEvents: "none",
            }}
          />
          {/* eslint-disable-next-line @next/next/no-img-element -- the api's badge picture, laid by css */}
          <img
            src={badge}
            alt="Logo"
            role="slider"
            aria-label="Vị trí logo"
            aria-valuenow={logo.y}
            aria-valuemin={0}
            aria-valuemax={FRAME_HEIGHT}
            aria-valuetext={`x ${logo.x}, y ${logo.y}`}
            data-testid="logo-drag"
            tabIndex={0}
            draggable={false}
            onPointerDown={(event) => {
              event.currentTarget.setPointerCapture(event.pointerId);
              drag.current = { pointer: [event.clientX, event.clientY], from: logo };
            }}
            onPointerMove={move}
            onPointerUp={() => (drag.current = null)}
            onKeyDown={key}
            style={{ ...badgeStyle(logo), cursor: "move", outline: `2px solid ${COLORS.primary}` }}
          />
        </div>
        <Flex gap={8} align="center" style={{ width: SHOWN_WIDTH }}>
          <Typography.Text style={{ fontSize: 13 }}>Cỡ</Typography.Text>
          <Slider
            ariaLabelForHandle="Cỡ logo"
            style={{ flex: 1 }}
            min={MIN_SIZE}
            max={MAX_SIZE}
            step={5}
            value={logo.size}
            onChange={(size) => setLogo(keep({ ...logo, size }, layout))}
          />
        </Flex>
        <Flex wrap gap={8} justify="center">
          <Button onClick={() => onSave({ logo_position: null, logo_size: null })}>Đặt lại vị trí</Button>
          <Button type="primary" onClick={() => onSave({ logo_position: [logo.x, logo.y], logo_size: logo.size })}>
            Lưu
          </Button>
        </Flex>
      </Flex>
    </Modal>
  );
}
