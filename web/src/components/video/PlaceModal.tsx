"use client";

import { Button, Flex, Modal, Tabs, Typography } from "antd";
import { useRef, useState } from "react";
import { api, errorMessage, type SceneData, type VideoDetail } from "@/lib/api";
import { COLORS } from "@/app/theme";
import { FRAME_HEIGHT, FRAME_WIDTH, HALF_X, halfHeight, halfHomeY, halfY, isHalf, layerCorner } from "./preview/layers";
import { SAFE, placeBox } from "./TextPositionModal";

export type PlaceTab = "text" | "inset";

type Size = { width: number; height: number };
type Point = [number, number];

const SHOWN_WIDTH = 270; // the frame on screen, a quarter of its size
const SCALE = SHOWN_WIDTH / FRAME_WIDTH;
const STEP = 10; // frame pixels an arrow key moves the chosen one
const LOCKED_OPACITY = 0.55;
const scaled = (value: number) => value * SCALE;

/**
 * Where the scene's text goes when nobody placed it (videos.placed_at): the video's own place if it has one, else the
 * side facing away from an inset photo that is not flush with the top edge (videos.opposite_the_inset), else the
 * template's (None).
 */
function textHome(scene: SceneData, insetTop: number | null): Point | null {
  const savedInset = scene.layers.find(isHalf);
  const savedTop = savedInset ? savedInset.y - Math.floor(halfHeight(savedInset.height) / 2) : null;
  const fromInset = scene.text_position === null && savedTop !== null && savedTop > 0 && scene.placed_at?.[1] === 0;
  if (scene.text_position === null && scene.placed_at !== null && !fromInset) {
    return scene.placed_at;
  }
  return insetTop !== null && insetTop > 0 ? [FRAME_WIDTH / 2, 0] : null;
}

/**
 * "Chỉnh vị trí": one window for a content scene of a "Video xuyên suốt" with two tabs, "Chữ" and "Ảnh chèn" (the
 * second only while the scene has an inset photo). Over the backdrop, the inset photo and the text box as the render
 * lays them, the open tab's one is dragged up and down (mouse, touch or arrow keys) and always stays centred across;
 * the other is dimmed and locked. The text stays inside the platforms' safe zone (as on the title scene); the inset
 * goes from flush with the top edge to flush with the bottom edge. "Vị trí gốc" puts the open tab's one back, "Lưu"
 * saves both and closes, ✕ drops what was not saved.
 */
export default function PlaceModal({
  scene,
  backdrop,
  tab: openTab,
  onClose,
  onSaved,
}: {
  scene: SceneData;
  /** The title scene, whose photo or clip runs under this scene. */
  backdrop: SceneData | null;
  tab: PlaceTab;
  onClose: () => void;
  onSaved: (video: VideoDetail) => void;
}) {
  const inset = scene.layers.find(isHalf) ?? null;
  const [tab, setTab] = useState<PlaceTab>(inset ? openTab : "text");
  const [size, setSize] = useState<Size | null>(null);
  // The text's own place: null is "not placed" (its home); `textMoved` once it was dragged or put back.
  const [textCentre, setTextCentre] = useState<Point | null>(scene.text_position ? scene.placed_at : null);
  const [textMoved, setTextMoved] = useState(false);
  const [insetY, setInsetY] = useState<number | null>(inset?.y ?? null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const drag = useRef<{ pointer: number; y: number } | null>(null);

  const side = inset ? halfHeight(inset.height) : 0;
  const insetCorner = inset && insetY !== null ? layerCorner(side, side, { x: HALF_X, y: insetY }) : null;
  const shownCentre = textCentre ?? textHome(scene, insetCorner ? insetCorner[1] : null);
  const textCorner = size ? placeBox(size, shownCentre, false) : null;
  const textY = size && textCorner ? textCorner[1] + Math.floor(size.height / 2) : null;

  /** Moves the open tab's one to `y` (frame pixels), kept where the render will really put it. */
  function moveTo(y: number, snap: boolean) {
    if (tab === "inset" && inset) {
      setInsetY(halfY(y, inset.height, snap));
    } else if (size) {
      const corner = placeBox(size, [FRAME_WIDTH / 2, y], false);
      setTextCentre([FRAME_WIDTH / 2, corner[1] + Math.floor(size.height / 2)]);
      setTextMoved(true);
    }
  }

  const currentY = () => (tab === "inset" ? insetY : textY);

  function start(event: React.PointerEvent<HTMLElement>) {
    const y = currentY();
    if (y === null) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    drag.current = { pointer: event.clientY, y };
  }

  function move(event: React.PointerEvent<HTMLElement>) {
    const from = drag.current;
    if (from) moveTo(Math.round(from.y + (event.clientY - from.pointer) / SCALE), true);
  }

  function key(event: React.KeyboardEvent) {
    const step = { ArrowUp: -1, ArrowDown: 1 }[event.key];
    const y = currentY();
    if (step && y !== null) {
      event.preventDefault();
      moveTo(y + step * STEP, false);
    }
  }

  function reset() {
    if (tab === "inset" && inset) {
      setInsetY(halfHomeY(inset.height));
    } else {
      setTextCentre(null);
      setTextMoved(true);
    }
  }

  async function save() {
    setSaving(true);
    setError(null);
    try {
      let saved: VideoDetail | null = null;
      if (inset && insetY !== null && insetY !== inset.y) {
        saved = await api<VideoDetail>(`/layers/${inset.id}`, "PATCH", { y: insetY });
      }
      if (textMoved) {
        saved = await api<VideoDetail>(`/scenes/${scene.id}`, "PATCH", { text_position: textCentre });
      }
      if (saved) onSaved(saved);
      onClose();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  const ground = backdrop ?? scene;
  const picture = ground.frame_url ?? ground.preview_url;
  const shade = "rgba(0, 0, 0, 0.45)";
  /** The open tab's one: dashed, dragged up and down, with ⇅ beside it; the other dimmed and locked. Its handlers
   * are set on the element itself. */
  const active = (on: boolean, label: string, y: number | null) =>
    on
      ? {
          role: "slider",
          "aria-label": label,
          "aria-orientation": "vertical" as const,
          "aria-valuenow": y ?? undefined,
          "aria-valuemin": 0,
          "aria-valuemax": FRAME_HEIGHT,
          tabIndex: 0,
          style: {
            cursor: "ns-resize",
            outline: `2px dashed ${COLORS.primary}`,
            outlineOffset: 2,
            touchAction: "none" as const,
          },
        }
      : { "aria-hidden": true, style: { opacity: LOCKED_OPACITY, pointerEvents: "none" as const } };

  const insetProps = active(tab === "inset", "Ảnh chèn", insetY);
  const textProps = active(tab === "text", "Hộp chữ", textY);
  const arrowAt = tab === "inset" ? insetY : textY;

  return (
    <Modal
      open
      title={tab === "inset" ? "Vị trí ảnh chèn" : "Vị trí chữ"}
      onCancel={onClose}
      centered
      width={420}
      footer={null}
      destroyOnHidden
    >
      <Flex vertical gap={12} align="center" data-testid="place-modal">
        {inset && (
          <Tabs
            activeKey={tab}
            onChange={(key) => setTab(key as PlaceTab)}
            centered
            size="small"
            style={{ width: "100%" }}
            tabBarStyle={{ marginBottom: 0 }}
            items={[
              { key: "text", label: "Chữ" },
              { key: "inset", label: "Ảnh chèn" },
            ]}
          />
        )}
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          Kéo lên hoặc xuống (hoặc dùng phím mũi tên); luôn ở giữa theo chiều ngang.
        </Typography.Text>
        <div
          data-testid="place-frame"
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
          {ground.video ? (
            <video
              src={ground.video.url}
              muted
              loop
              autoPlay
              playsInline
              onLoadedMetadata={(event) => {
                event.currentTarget.currentTime = ground.video?.start ?? 0;
              }}
              style={{ position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "cover" }}
            />
          ) : picture ? (
            // eslint-disable-next-line @next/next/no-img-element -- drawn by the api, like the previews
            <img
              src={picture}
              alt=""
              style={{ position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "cover" }}
            />
          ) : null}
          {tab === "text" && (
            // Outside the safe zone, where TikTok and Reels put their buttons, darkened.
            <>
              <div
                style={{ position: "absolute", inset: 0, bottom: "auto", height: scaled(SAFE.top), background: shade }}
              />
              <div style={{ position: "absolute", inset: 0, top: scaled(SAFE.bottom), background: shade }} />
            </>
          )}
          {inset && insetCorner && (
            // eslint-disable-next-line @next/next/no-img-element -- drawn by the api with the render core's own code
            <img
              src={inset.image_url}
              alt="Ảnh chèn"
              draggable={false}
              data-testid="place-inset"
              {...insetProps}
              onPointerDown={tab === "inset" ? start : undefined}
              onPointerMove={tab === "inset" ? move : undefined}
              onPointerUp={() => (drag.current = null)}
              onKeyDown={tab === "inset" ? key : undefined}
              style={{
                position: "absolute",
                left: scaled(insetCorner[0]),
                top: scaled(insetCorner[1]),
                width: scaled(side),
                height: scaled(side),
                ...insetProps.style,
              }}
            />
          )}
          {scene.textbox_url && (
            // eslint-disable-next-line @next/next/no-img-element -- the exact box the renderer overlays
            <img
              src={scene.textbox_url}
              alt="Hộp chữ"
              draggable={false}
              data-testid="place-text"
              onLoad={(event) =>
                setSize({ width: event.currentTarget.naturalWidth, height: event.currentTarget.naturalHeight })
              }
              {...textProps}
              onPointerDown={tab === "text" ? start : undefined}
              onPointerMove={tab === "text" ? move : undefined}
              onPointerUp={() => (drag.current = null)}
              onKeyDown={tab === "text" ? key : undefined}
              style={{
                position: "absolute",
                left: textCorner ? scaled(textCorner[0]) : 0,
                top: textCorner ? scaled(textCorner[1]) : 0,
                width: size ? scaled(size.width) : undefined,
                visibility: textCorner ? "visible" : "hidden",
                ...textProps.style,
              }}
            />
          )}
          {arrowAt !== null && (
            <span
              aria-hidden
              style={{
                position: "absolute",
                right: 4,
                top: scaled(arrowAt),
                transform: "translateY(-50%)",
                color: "#fff",
                background: COLORS.primary,
                borderRadius: 4,
                padding: "0 4px",
                fontSize: 14,
                lineHeight: "20px",
                pointerEvents: "none",
              }}
            >
              ⇅
            </span>
          )}
        </div>
        {error && <Typography.Text type="danger">{error}</Typography.Text>}
        <Flex wrap gap={8} justify="center">
          <Button onClick={reset} disabled={saving}>
            Vị trí gốc
          </Button>
          <Button type="primary" loading={saving} disabled={tab === "text" && !size} onClick={() => void save()}>
            Lưu
          </Button>
        </Flex>
      </Flex>
    </Modal>
  );
}
