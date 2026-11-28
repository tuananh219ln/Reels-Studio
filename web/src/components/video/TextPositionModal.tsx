"use client";

import { Button, Flex, Modal, Typography } from "antd";
import { useRef, useState } from "react";
import { api, errorMessage, type SceneData, type TextArea, type VideoDetail } from "@/lib/api";
import { COLORS } from "@/app/theme";

// The renderer's frame (reels_render.layout). Where text and the logo may go comes with each video from the api.
export const FRAME_WIDTH = 1080;
export const FRAME_HEIGHT = 1920;
/** What the platforms draw over a video (frame 1080×1920): the search bar on top, the caption and music below, the
 * like/comment/share column on the right. */
export const COVERED = {
  top: 190,
  bottom: 1480,
  rightColumn: { x: 900, y1: 850, y2: 1600 },
};
const SHOWN_WIDTH = 270; // the frame on screen, a quarter of its size
const SCALE = SHOWN_WIDTH / FRAME_WIDTH;
const STEP = 10; // frame pixels an arrow key moves the box

type Size = { width: number; height: number };
type Point = [number, number];

/** Top-left corner of a text picture (reels_render.layout.place_box): centred across at the top when nobody placed it,
 * else centred on the point, kept between the area's edges; the title moves only up and down. */
export function placeBox(size: Size, centre: Point | null, isTitle: boolean, area: TextArea): Point {
  const middle = isTitle || centre === null ? FRAME_WIDTH / 2 : centre[0];
  const left = area.left - area.inset;
  const right = area.right + area.inset;
  const x =
    size.width > right - left
      ? left + Math.floor((right - left - size.width) / 2)
      : Math.max(left, Math.min(middle - Math.floor(size.width / 2), right - size.width));
  const top = area.top - area.inset;
  const y = centre === null ? top : centre[1] - Math.floor(size.height / 2);
  return [x, Math.max(top, Math.min(y, area.bottom + area.inset - size.height))];
}

/** The centre of a box placed at a corner, as the api stores it: the inverse of placeBox (which takes half the
 * size rounded down, like textbox.place_box), so placing a box at its own centre never moves it. */
const centreOf = (corner: Point, size: Size): Point => [
  corner[0] + Math.floor(size.width / 2),
  corner[1] + Math.floor(size.height / 2),
];

/** Where the scene's text box is drawn: where it was placed, else where a framed photo ("Khung ảnh") or its zone puts
 * it, else null (the top). */
export function shownAt(scene: SceneData): Point | null {
  return scene.placed_at ?? scene.image_frame?.text_at ?? scene.text_area.home;
}

/** The scene's frame without text for a box centred at `centre`: a framed photo sits below a box in the upper half
 * and above one in the lower half, so its frame follows the box. */
export function frameFor(scene: SceneData, centre: Point | null): string | null {
  if (!scene.frame_url || !scene.image_frame || scene.image_frame.kind === "cover") {
    return scene.frame_url;
  }
  return `${scene.frame_url}&anchor=${centre !== null && centre[1] >= FRAME_HEIGHT / 2 ? "bottom" : "top"}`;
}

/** Drag the scene's text box over its frame, inside the video's text area, and save it for the scene or video. */
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
  // A framed photo's "Vị trí gốc" is where the framing puts the text.
  const area = scene.text_area;
  const home = scene.image_frame?.text_at ?? area.home;
  const [centre, setCentre] = useState<Point | null>(shownAt(scene));
  const [saving, setSaving] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const drag = useRef<{ pointer: Point; centre: Point } | null>(null);
  const corner = size ? placeBox(size, centre, scene.is_title, area) : null;
  const videoWide = !scene.is_title && scene.text_position === null && scene.placed_at !== null;

  function moveTo(point: Point) {
    if (size) {
      // Kept where the renderer will really put it, so the box stops at the zone's edges while dragged.
      setCentre(centreOf(placeBox(size, point, scene.is_title, area), size));
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
      centered
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
              src={frameFor(scene, point) ?? ""}
              alt=""
              style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }}
            />
          )}
          {/* Outside the safe zone, darkened. */}
          <div
            style={{ position: "absolute", left: 0, right: 0, top: 0, height: scaled(area.top), background: shade }}
          />
          <div
            style={{
              position: "absolute",
              left: 0,
              right: 0,
              top: scaled(area.bottom),
              bottom: 0,
              background: shade,
            }}
          />
          <div
            style={{
              position: "absolute",
              left: 0,
              width: scaled(area.left),
              top: scaled(area.top),
              height: scaled(area.bottom - area.top),
              background: shade,
            }}
          />
          <div
            style={{
              position: "absolute",
              left: scaled(area.right),
              right: 0,
              top: scaled(area.top),
              height: scaled(area.bottom - area.top),
              background: shade,
            }}
          />
          <div
            style={{
              position: "absolute",
              left: scaled(area.left),
              top: scaled(area.top),
              width: scaled(area.right - area.left),
              height: scaled(area.bottom - area.top),
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
                outline: `2px solid ${COLORS.primary}`,
                outlineOffset: 2,
              }}
            />
          )}
        </div>
        {error && <Typography.Text type="danger">{error}</Typography.Text>}
        <Flex wrap gap={8} justify="center">
          <Button onClick={() => setCentre(home)} disabled={saving !== null}>
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
