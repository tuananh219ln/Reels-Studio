"use client";

import { DragOutlined } from "@ant-design/icons";
import { Alert, App, Button, Flex, Grid, Slider, Switch, Typography } from "antd";
import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { api, errorMessage, type SceneData, type SceneLayer, type VideoDetail } from "@/lib/api";
import { useEditor } from "./AutoSaveField";
import PlaceModal from "./PlaceModal";
import {
  FRAME_HEIGHT,
  FRAME_WIDTH,
  HALF_HEIGHT_MAX,
  HALF_HEIGHT_MIN,
  HALF_X,
  halfHeight,
  halfYResized,
  isHalf,
  layerCorner,
} from "./preview/layers";
import { silentVideo } from "./silentVideo";
import { placeBox } from "./TextPositionModal";

const percent = (value: number, of: number) => `${(value / of) * 100}%`;
/** The left column of a scene card on a screen from 576 px: the 9:16 frame stays a thumbnail. */
const LEFT_WIDTH = 220;

type Size = { width: number; height: number };
type Place = { y: number; height: number };

/** The size of the scene's text box as the api draws it (null until it has loaded, or without text). */
function useBoxSize(url: string | null): Size | null {
  const [size, setSize] = useState<{ url: string; width: number; height: number } | null>(null);
  useEffect(() => {
    if (!url) return;
    let live = true;
    const image = new Image();
    image.onload = () => {
      if (live) setSize({ url, width: image.naturalWidth, height: image.naturalHeight });
    };
    image.src = url;
    return () => {
      live = false;
    };
  }, [url]);
  return url && size?.url === url ? size : null;
}

/** Whether the scene's text box, where the render puts it, covers part of its inset photo. */
function textOverInset(scene: SceneData, box: Size | null, layer: SceneLayer | undefined): boolean {
  if (!box || !layer) return false;
  const [left, top] = placeBox(box, scene.placed_at, false);
  const side = halfHeight(layer.height);
  const [insetLeft, insetTop] = layerCorner(side, side, layer);
  const across = left < insetLeft + side && left + box.width > insetLeft;
  const down = top < insetTop + side && top + box.height > insetTop;
  return across && down;
}

/**
 * "Chữ đang đè lên ảnh chèn": a small yellow warning beside the scene's text when its text box, as saved, covers part of
 * its inset photo. Allowed (a box style keeps the text readable), so it never blocks saving.
 */
export function InsetOverlapWarning({ scene }: { scene: SceneData }) {
  const box = useBoxSize(scene.textbox_url);
  if (!textOverInset(scene, box, scene.layers.find(isHalf))) return null;
  return <Alert type="warning" showIcon title="Chữ đang đè lên ảnh chèn" data-testid="text-over-inset" />;
}

/**
 * A content scene of a "Video xuyên suốt" (a slide video has no inset photo): the preview (the backdrop playing, the
 * inset photo over it and the scene's text box on top, as the render lays them), "Chỉnh vị trí chữ & ảnh chèn" (always
 * there; both are dragged up and down in PlaceModal), `children` (the scene's own picture tools, when they matter) and
 * the "Ảnh chèn" block: a switch and, turned on, "Cỡ ảnh" (30–45%, the preview follows the slider at once). The inset
 * always shows the scene's photo (2026-11-12, scene card layout); one an older edit gave a photo of its own keeps it,
 * with "Dùng ảnh của cảnh" to let it go.
 *
 * Given `fields` (the scene card), from 576 px it lays out as a grid: the preview beside `fields`, then the button and
 * the picture tools on the left beside the "Ảnh chèn" block on the right; narrower, everything in one column, the
 * fields last. Without `fields` (the studio's inspector), one column.
 */
export default function HalfPhotoPanel({
  scene,
  backdrop,
  fields,
  children,
}: {
  scene: SceneData;
  /** The title scene of a "Video xuyên suốt": its photo or clip runs under this scene. */
  backdrop: SceneData | null;
  /** The card's text, narration and other fields: the right column. */
  fields?: ReactNode;
  children?: ReactNode;
}) {
  const { modal } = App.useApp();
  const editor = useEditor();
  const wide = Grid.useBreakpoint().sm === true;
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [placing, setPlacing] = useState(false);
  // "Cỡ ảnh" while its slider is being dragged: the preview follows it before it is saved.
  const [resizing, setResizing] = useState<number | null>(null);
  // The size and place an inset had when it was turned off here, given back when it is turned on again.
  const lastPlace = useRef<Place | null>(null);
  const box = useBoxSize(scene.textbox_url);
  const frozen = editor.locked || editor.readOnly;
  const off = frozen || busy !== null;
  const layer = scene.layers.find(isHalf);
  // One photo layer per scene: an older video's "Ảnh món" takes the place too.
  const otherPhoto = !layer && scene.layers.some((item) => item.kind === "photo");

  async function run(kind: string, action: () => Promise<VideoDetail>) {
    setBusy(kind);
    setError(null);
    try {
      editor.onSaved(await action());
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  /** On: an inset showing the scene's photo, flush with the bottom edge at 32% (an "Ảnh món" turns into one), or where
   * it was when it was turned off here. */
  const turnOn = () =>
    run("on", async () => {
      const saved = await api<VideoDetail>("/layers/half-photo", "POST", { scene_id: scene.id, scene_photo: true });
      const back = lastPlace.current;
      const made = saved.scenes.find((item) => item.id === scene.id)?.layers.find(isHalf);
      if (!back || !made || (made.y === back.y && made.height === back.height)) return saved;
      // The height first (the api applies it before `y`), so the place is kept exactly.
      return api<VideoDetail>(`/layers/${made.id}`, "PATCH", { height: back.height, y: back.y });
    });

  function turnOff(target: SceneLayer) {
    const go = () => {
      lastPlace.current = { y: target.y, height: target.height };
      return run("off", () => api<VideoDetail>(`/layers/${target.id}`, "DELETE"));
    };
    if (!target.own_image) {
      void go();
      return;
    }
    modal.confirm({
      title: "Tắt ảnh chèn?",
      content: "Ảnh riêng của ảnh chèn bị xoá hẳn. Bật lại thì ảnh chèn dùng ảnh của cảnh.",
      okText: "Tắt",
      okButtonProps: { danger: true },
      cancelText: "Huỷ",
      onOk: go,
    });
  }

  /** An older edit's own photo let go: the inset shows the scene's photo, in the same place and size. */
  const toScenePhoto = () =>
    run("scene", () => api<VideoDetail>("/layers/half-photo", "POST", { scene_id: scene.id, scene_photo: true }));

  const ground = backdrop ?? scene;
  const picture = ground.frame_url ?? ground.preview_url;
  const textCorner = box ? placeBox(box, scene.placed_at, false) : null;
  const height = resizing ?? layer?.height ?? 0;
  const side = layer ? halfHeight(height) : 0;
  const insetCorner = layer
    ? layerCorner(side, side, {
        x: HALF_X,
        y: resizing === null ? layer.y : halfYResized(layer.y, layer.height, resizing),
      })
    : null;

  const stage = (
    <div
      data-testid="half-photo-stage"
      style={{
        position: "relative",
        width: "100%",
        aspectRatio: `${FRAME_WIDTH} / ${FRAME_HEIGHT}`,
        overflow: "hidden",
        borderRadius: 6,
        background: "#000",
      }}
    >
      {ground.video ? (
        <video
          ref={silentVideo}
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
        // eslint-disable-next-line @next/next/no-img-element -- frames are drawn by the api; next/image adds nothing
        <img
          src={picture}
          alt=""
          style={{ position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "cover" }}
        />
      ) : null}
      {layer && insetCorner && (
        // The inset as the render core draws it (a rounded square), sized here so the slider shows its size at once.
        // eslint-disable-next-line @next/next/no-img-element -- drawn by the api with the render core's own code
        <img
          src={layer.image_url}
          alt=""
          draggable={false}
          data-testid="preview-layer"
          data-layer={layer.id}
          style={{
            position: "absolute",
            pointerEvents: "none",
            left: percent(insetCorner[0], FRAME_WIDTH),
            top: percent(insetCorner[1], FRAME_HEIGHT),
            width: percent(side, FRAME_WIDTH),
            height: percent(side, FRAME_HEIGHT),
          }}
        />
      )}
      {scene.textbox_url && box && textCorner && (
        // The scene's text over the photo, where the render puts it.
        // eslint-disable-next-line @next/next/no-img-element -- drawn by the api with the renderer's own code
        <img
          src={scene.textbox_url}
          alt=""
          draggable={false}
          style={{
            position: "absolute",
            pointerEvents: "none",
            left: percent(textCorner[0], FRAME_WIDTH),
            top: percent(textCorner[1], FRAME_HEIGHT),
            width: percent(box.width, FRAME_WIDTH),
          }}
        />
      )}
    </div>
  );

  const place = (
    <Button
      type="primary"
      block
      icon={<DragOutlined />}
      disabled={frozen}
      onClick={async () => {
        // The box is drawn from the saved text: the text being typed is saved first.
        await editor.flush();
        setPlacing(true);
      }}
    >
      Chỉnh vị trí chữ & ảnh chèn
    </Button>
  );

  const block = (
    <Flex
      vertical
      gap={8}
      data-testid="inset-block"
      style={{ border: "1px solid #f0f0f0", borderRadius: 8, padding: 10 }}
    >
      <Flex align="center" justify="space-between" gap={8}>
        <Typography.Text strong>Ảnh chèn</Typography.Text>
        <Switch
          size="small"
          aria-label="Ảnh chèn"
          checked={!!layer}
          loading={busy === "on" || busy === "off"}
          disabled={off}
          onChange={(on) => (on ? void turnOn() : layer && turnOff(layer))}
        />
      </Flex>
      {!layer ? (
        <Typography.Text type="secondary" style={{ fontSize: 12 }} data-testid="inset-off">
          {otherPhoto ? "Cảnh đang dùng ảnh món. Bật để đổi sang ảnh chèn." : "Đang tắt. Bật để chèn ảnh của cảnh."}
        </Typography.Text>
      ) : (
        <>
          <div>
            <Slider
              ariaLabelForHandle="Cỡ ảnh"
              min={HALF_HEIGHT_MIN}
              max={HALF_HEIGHT_MAX}
              step={1}
              value={height}
              disabled={off}
              tooltip={{ formatter: (value) => `${value}%` }}
              style={{ margin: "4px 6px" }}
              onChange={(value) => setResizing(value)}
              onChangeComplete={(value) =>
                void run("size", () => api<VideoDetail>(`/layers/${layer.id}`, "PATCH", { height: value })).finally(
                  () => setResizing(null),
                )
              }
            />
            <Typography.Text type="secondary" style={{ fontSize: 12 }} data-testid="inset-size">
              Cỡ ảnh: {height}% (hẹp hơn video)
            </Typography.Text>
          </div>
          {layer.own_image && (
            // An inset given a photo of its own before the block lost its own picture buttons: it keeps rendering it.
            <Flex wrap align="center" gap={6} data-testid="inset-own-image">
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                Đang dùng ảnh riêng chọn từ trước.
              </Typography.Text>
              <Button size="small" loading={busy === "scene"} disabled={off} onClick={() => void toScenePhoto()}>
                Dùng ảnh của cảnh
              </Button>
            </Flex>
          )}
        </>
      )}
      {error && <Alert type="error" showIcon title={error} />}
    </Flex>
  );

  const placeWindow = placing && (
    <PlaceModal
      scene={scene}
      backdrop={backdrop}
      tab="text"
      onClose={() => setPlacing(false)}
      onSaved={editor.onSaved}
    />
  );

  if (fields === undefined) {
    return (
      <Flex vertical gap={8} data-testid="half-photo-panel">
        {stage}
        {place}
        {children}
        {block}
        {placeWindow}
      </Flex>
    );
  }

  // From 576 px: the preview beside the fields, the button and picture tools beside the "Ảnh chèn" block, which keeps
  // its own height. Narrower: one column as before, the left column's parts a thumbnail wide, the fields last.
  const cell = (area: string, left: boolean): CSSProperties => ({
    gridArea: area,
    minWidth: 0,
    ...(left && !wide ? { width: "100%", maxWidth: LEFT_WIDTH, justifySelf: "center" } : {}),
  });
  return (
    <div
      data-testid="half-photo-panel"
      style={{
        display: "grid",
        columnGap: 16,
        rowGap: 8,
        gridTemplateColumns: wide ? `${LEFT_WIDTH}px minmax(0, 1fr)` : "minmax(0, 1fr)",
        gridTemplateRows: wide ? "auto auto 1fr" : undefined,
        gridTemplateAreas: wide
          ? '"stage fields" "place block" "tools block"'
          : '"stage" "place" "tools" "block" "fields"',
      }}
    >
      <div style={cell("stage", true)}>{stage}</div>
      <div style={cell("fields", false)}>{fields}</div>
      <div style={cell("place", true)}>{place}</div>
      {children && <div style={cell("tools", true)}>{children}</div>}
      <div style={{ ...cell("block", true), alignSelf: "start" }}>{block}</div>
      {placeWindow}
    </div>
  );
}
