"use client";

import { Button, Flex, Modal, Typography } from "antd";
import { useRef, useState } from "react";
import { api, errorMessage, type SceneData, type VideoDetail } from "@/lib/api";

// The renderer's frame and safe zone (reels_render.textbox): keep these in step with it.
const FRAME_WIDTH = 1080;
const FRAME_HEIGHT = 1920;
const SCENE_BOX_BOTTOM = 1440;
const SAFE = { left: 60, top: 220, right: 940, bottom: SCENE_BOX_BOTTOM };
const SHOWN_WIDTH = 270; // the frame on screen, a quarter of its size
const SCALE = SHOWN_WIDTH / FRAME_WIDTH;
const STEP = 10; // frame pixels an arrow key moves the box

type Size = { width: number; height: number };
type Point = [number, number];

function clamp(start: number, size: number, low: number, high: number, frame: number) {
  if (size > high - low) {
    return Math.floor((frame - size) / 2);
  }
  return Math.max(low, Math.min(start, high - size));
}

/** Top-left corner of the box (textbox.place_box): the template's place, or centred on the point in the zone. */
export function placeBox(size: Size, centre: Point | null, isTitle: boolean): Point {
  const middleX = Math.floor((FRAME_WIDTH - size.width) / 2);
  if (centre === null) {
    return [middleX, isTitle ? Math.floor((FRAME_HEIGHT - size.height) / 2) : SCENE_BOX_BOTTOM - size.height];
  }
  const x = isTitle
    ? middleX
    : clamp(centre[0] - Math.floor(size.width / 2), size.width, SAFE.left, SAFE.right, FRAME_WIDTH);
  const y = clamp(centre[1] - Math.floor(size.height / 2), size.height, SAFE.top, SAFE.bottom, FRAME_HEIGHT);
  return [x, y];
}

/** The centre of a box placed at a corner, as the api stores it. */
const centreOf = (corner: Point, size: Size): Point => [
  Math.round(corner[0] + size.width / 2),
  Math.round(corner[1] + size.height / 2),
];

/** Drag the scene's text box over its frame, inside the platforms' safe zone, and save it for the scene or video. */
export default function TextPositionModal({
  scene,
  onClose,
  onSaved,
}: {
  scene: SceneData;
  onClose: () => void;
  onSaved: (video: VideoDetail) => void;
}) {
  const [size, setSize] = useState<Size | null>(null);
  const [centre, setCentre] = useState<Point | null>(scene.placed_at);
  const [saving, setSaving] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const drag = useRef<{ pointer: Point; centre: Point } | null>(null);
  const corner = size ? placeBox(size, centre, scene.is_title) : null;
  const videoWide = !scene.is_title && scene.text_position === null && scene.placed_at !== null;

  function moveTo(point: Point) {
    if (size) {
      // Kept where the renderer will really put it, so the box stops at the zone's edges while dragged.
      setCentre(centreOf(placeBox(size, point, scene.is_title), size));
    }
  }

  function start(event: React.PointerEvent<HTMLImageElement>) {
    if (!size || !corner) {
      return;
    }
    event.currentTarget.setPointerCapture(event.pointerId);
    drag.current = { pointer: [event.clientX, event.clientY], centre: centreOf(corner, size) };
  }

  function move(event: React.PointerEvent<HTMLImageElement>) {
    const from = drag.current;
    if (from) {
      moveTo([
        Math.round(from.centre[0] + (event.clientX - from.pointer[0]) / SCALE),
        Math.round(from.centre[1] + (event.clientY - from.pointer[1]) / SCALE),
      ]);
    }
  }

  function key(event: React.KeyboardEvent) {
    const steps: Record<string, Point> = {
      ArrowUp: [0, -1],
      ArrowDown: [0, 1],
      ArrowLeft: [-1, 0],
      ArrowRight: [1, 0],
    };
    const step = steps[event.key];
    if (step && size && corner) {
      event.preventDefault();
      const [x, y] = centreOf(corner, size);
      moveTo([x + step[0] * STEP, y + step[1] * STEP]);
    }
  }

  async function save(kind: string, requests: () => Promise<VideoDetail>) {
    setSaving(kind);
    setError(null);
    try {
      onSaved(await requests());
      onClose();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(null);
    }
  }

  const point = size && corner ? centreOf(corner, size) : null;
  const forScene = () => api<VideoDetail>(`/scenes/${scene.id}`, "PATCH", { text_position: point });
  const forVideo = async () => {
    const video = await api<VideoDetail>(`/videos/${scene.video_id}`, "PATCH", { options: { text_position: point } });
    // The scene follows the video's place from now on.
    return scene.text_position ? api<VideoDetail>(`/scenes/${scene.id}`, "PATCH", { text_position: null }) : video;
  };
  const shade = "rgba(0, 0, 0, 0.45)";
  const scaled = (value: number) => value * SCALE;

  return (
    <Modal
      open
      title={scene.is_title ? "Vị trí chữ cảnh tiêu đề" : "Vị trí chữ của cảnh"}
      onCancel={onClose}
      width={420}
      footer={null}
      destroyOnHidden
    >
      <Flex vertical gap={12} align="center">
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          {scene.is_title
            ? "Kéo lên hoặc xuống (hoặc dùng phím mũi tên); tiêu đề luôn ở giữa theo chiều ngang."
            : "Kéo hộp chữ (hoặc dùng phím mũi tên). Vùng tối là chỗ nút và chữ của TikTok, Reels che mất."}
        </Typography.Text>
        <div
          data-testid="position-frame"
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
          {scene.frame_url && (
            // eslint-disable-next-line @next/next/no-img-element -- drawn by the api, like the previews
            <img
              src={scene.frame_url}
              alt=""
              style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }}
            />
          )}
          {/* Outside the safe zone, darkened. */}
          <div
            style={{ position: "absolute", left: 0, right: 0, top: 0, height: scaled(SAFE.top), background: shade }}
          />
          <div
            style={{
              position: "absolute",
              left: 0,
              right: 0,
              top: scaled(SAFE.bottom),
              bottom: 0,
              background: shade,
            }}
          />
          <div
            style={{
              position: "absolute",
              left: 0,
              width: scaled(SAFE.left),
              top: scaled(SAFE.top),
              height: scaled(SAFE.bottom - SAFE.top),
              background: shade,
            }}
          />
          <div
            style={{
              position: "absolute",
              left: scaled(SAFE.right),
              right: 0,
              top: scaled(SAFE.top),
              height: scaled(SAFE.bottom - SAFE.top),
              background: shade,
            }}
          />
          <div
            style={{
              position: "absolute",
              left: scaled(SAFE.left),
              top: scaled(SAFE.top),
              width: scaled(SAFE.right - SAFE.left),
              height: scaled(SAFE.bottom - SAFE.top),
              border: "1px dashed rgba(255,255,255,0.7)",
              boxSizing: "border-box",
              pointerEvents: "none",
            }}
          />
          {scene.textbox_url && (
            // eslint-disable-next-line @next/next/no-img-element -- the exact box the renderer overlays
            <img
              src={scene.textbox_url}
              alt="Hộp chữ"
              role="slider"
              aria-label="Hộp chữ"
              aria-valuenow={point?.[1]}
              aria-valuemin={0}
              aria-valuemax={FRAME_HEIGHT}
              aria-valuetext={point ? `x ${point[0]}, y ${point[1]}` : undefined}
              data-testid="position-box"
              tabIndex={0}
              draggable={false}
              onLoad={(event) =>
                setSize({ width: event.currentTarget.naturalWidth, height: event.currentTarget.naturalHeight })
              }
              onPointerDown={start}
              onPointerMove={move}
              onPointerUp={() => (drag.current = null)}
              onKeyDown={key}
              style={{
                position: "absolute",
                left: corner ? scaled(corner[0]) : 0,
                top: corner ? scaled(corner[1]) : 0,
                width: size ? scaled(size.width) : undefined,
                visibility: corner ? "visible" : "hidden",
                cursor: scene.is_title ? "ns-resize" : "move",
                outline: "2px solid #1677ff",
                outlineOffset: 2,
              }}
            />
          )}
        </div>
        {error && <Typography.Text type="danger">{error}</Typography.Text>}
        <Flex wrap gap={8} justify="center">
          <Button onClick={() => setCentre(null)} disabled={saving !== null}>
            Vị trí gốc
          </Button>
          {scene.is_title ? (
            <Button
              type="primary"
              loading={saving === "scene"}
              disabled={!point}
              onClick={() =>
                save("scene", () =>
                  api<VideoDetail>(`/scenes/${scene.id}`, "PATCH", { text_position: centre === null ? null : point }),
                )
              }
            >
              Lưu
            </Button>
          ) : (
            <>
              <Button loading={saving === "video"} disabled={!point} onClick={() => save("video", forVideo)}>
                Lưu cho mọi cảnh
              </Button>
              <Button
                type="primary"
                loading={saving === "scene"}
                disabled={!point}
                onClick={() => save("scene", forScene)}
              >
                Lưu cho cảnh này
              </Button>
            </>
          )}
        </Flex>
        {!scene.is_title && (scene.text_position || videoWide) && (
          <Flex wrap gap={8} justify="center">
            {scene.text_position && (
              <Button
                size="small"
                type="link"
                loading={saving === "own"}
                onClick={() =>
                  save("own", () => api<VideoDetail>(`/scenes/${scene.id}`, "PATCH", { text_position: null }))
                }
              >
                Bỏ vị trí riêng của cảnh này
              </Button>
            )}
            <Button
              size="small"
              type="link"
              loading={saving === "all"}
              onClick={() =>
                save("all", () =>
                  api<VideoDetail>(`/videos/${scene.video_id}`, "PATCH", { options: { text_position: null } }),
                )
              }
            >
              Đưa vị trí chung về gốc
            </Button>
          </Flex>
        )}
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          {scene.is_title
            ? "Tiêu đề cũng là ảnh thumbnail của video."
            : "“Lưu cho mọi cảnh” đặt vị trí chung; cảnh nào đã có vị trí riêng vẫn giữ vị trí đó."}
        </Typography.Text>
      </Flex>
    </Modal>
  );
}
