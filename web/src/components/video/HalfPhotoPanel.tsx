"use client";

import { DragOutlined, FolderOpenOutlined, RobotOutlined, SearchOutlined, UploadOutlined } from "@ant-design/icons";
import { Alert, App, Button, Flex, Slider, Switch, Typography } from "antd";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { api, errorMessage, upload, type SceneData, type SceneLayer, type VideoDetail } from "@/lib/api";
import { useEditor } from "./AutoSaveField";
import MediaLibraryPicker from "./MediaLibraryPicker";
import PlaceModal, { type PlaceTab } from "./PlaceModal";
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
import StockPicker from "./StockPicker";
import { placeBox } from "./TextPositionModal";

const percent = (value: number, of: number) => `${(value / of) * 100}%`;
const MAX_IMAGE_BYTES = 15 * 1024 * 1024;
const IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"];

type Size = { width: number; height: number };

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
 * The left column of a content scene's card on a "Video xuyên suốt" (a slide video has no inset photo): from the top,
 * the preview (the backdrop playing, the inset photo over it and the scene's text box on top, as the render lays them),
 * "Chỉnh vị trí chữ" (always there), `children` (the scene's own picture tools, when they matter), then the "Ảnh chèn"
 * block. Turned off, the block is one line. Turned on: "Chỉnh vị trí ảnh chèn" (both places are dragged up and down in
 * PlaceModal), "Cỡ ảnh" (30–45%, the preview follows the slider at once) and the inset's own photo from four places:
 * upload, the library, a stock search, or an AI photo (the scene's, made from its "Prompt ảnh AI"). These are kept apart
 * from the scene's picture tools so the two kinds of photo are not confused.
 */
export default function HalfPhotoPanel({
  scene,
  backdrop,
  generating = false,
  children,
}: {
  scene: SceneData;
  /** The title scene of a "Video xuyên suốt": its photo or clip runs under this scene. */
  backdrop: SceneData | null;
  /** An AI photo is being made for this scene. */
  generating?: boolean;
  children?: ReactNode;
}) {
  const { modal } = App.useApp();
  const editor = useEditor();
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [placing, setPlacing] = useState<PlaceTab | null>(null);
  const [picking, setPicking] = useState<"stock" | "library" | null>(null);
  // "Cỡ ảnh" while its slider is being dragged: the preview follows it before it is saved.
  const [resizing, setResizing] = useState<number | null>(null);
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

  /** On: an inset showing the scene's photo, flush with the bottom edge at 32% (an "Ảnh món" turns into one). */
  const turnOn = () =>
    run("on", () => api<VideoDetail>("/layers/half-photo", "POST", { scene_id: scene.id, scene_photo: true }));

  const turnOff = (target: SceneLayer) =>
    modal.confirm({
      title: "Tắt ảnh chèn?",
      content: "Ảnh chèn bị xoá hẳn, không hoàn tác được. Muốn dùng lại thì bật và chọn ảnh lần nữa.",
      okText: "Tắt",
      okButtonProps: { danger: true },
      cancelText: "Huỷ",
      onOk: () => run("off", () => api<VideoDetail>(`/layers/${target.id}`, "DELETE")),
    });

  function chosen(file: File | undefined) {
    if (input.current) input.current.value = "";
    if (!file) return;
    if (!IMAGE_TYPES.includes(file.type)) {
      setError("Ảnh chèn chỉ nhận ảnh JPG, PNG hoặc WebP");
      return;
    }
    if (file.size > MAX_IMAGE_BYTES) {
      setError("Ảnh quá 15 MB, hãy chọn ảnh nhỏ hơn");
      return;
    }
    void run("upload", () => upload<VideoDetail>("/layers/half-photo/upload", file, { scene_id: String(scene.id) }));
  }

  /** "AI": the inset shows the scene's photo, made by an AI from the scene's "Prompt ảnh AI". */
  function generate(target: SceneLayer) {
    const go = () =>
      run("ai", async () => {
        // The job reads the saved prompt: the one being typed is saved first.
        await editor.flush();
        if (target.own_image) {
          await api<VideoDetail>("/layers/half-photo", "POST", { scene_id: scene.id, scene_photo: true });
        }
        return api<VideoDetail>(`/scenes/${scene.id}/image-ai`, "POST");
      });
    modal.confirm({
      title: "Tạo ảnh AI cho ảnh chèn?",
      content:
        "Ảnh AI được tạo theo “Prompt ảnh AI” của cảnh và thay ảnh chèn đang có. Mỗi lần tạo tốn phí dịch vụ ảnh AI.",
      okText: "Tạo",
      cancelText: "Huỷ",
      onOk: () => void go(),
    });
  }

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
          {otherPhoto ? "Cảnh đang dùng ảnh món. Bật để đổi sang ảnh chèn." : "Đang tắt. Bật để chọn vị trí và ảnh."}
        </Typography.Text>
      ) : (
        <>
          <Button
            block
            icon={<DragOutlined />}
            disabled={off}
            onClick={async () => {
              await editor.flush();
              setPlacing("inset");
            }}
            style={{ whiteSpace: "normal", height: "auto", minHeight: 32 }}
          >
            Chỉnh vị trí ảnh chèn (kéo lên xuống)
          </Button>
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
          <Flex gap={6} wrap data-testid="inset-sources">
            <Button
              size="small"
              icon={<UploadOutlined />}
              loading={busy === "upload"}
              disabled={off}
              onClick={() => input.current?.click()}
            >
              Tải lên
            </Button>
            <Button size="small" icon={<FolderOpenOutlined />} disabled={off} onClick={() => setPicking("library")}>
              Kho
            </Button>
            <Button
              size="small"
              icon={<SearchOutlined />}
              disabled={off}
              onClick={async () => {
                // The search starts from the scene's keywords: the one being typed is saved first.
                await editor.flush();
                setPicking("stock");
              }}
            >
              Tìm
            </Button>
            <Button
              size="small"
              icon={<RobotOutlined />}
              loading={generating || busy === "ai"}
              disabled={off || generating}
              onClick={() => generate(layer)}
            >
              AI
            </Button>
          </Flex>
          {!layer.own_image && (
            <Typography.Text type="secondary" style={{ fontSize: 12 }} data-testid="half-photo-scene-tools">
              Đang dùng ảnh của cảnh. Chọn ảnh riêng cho ảnh chèn bằng các nút trên.
            </Typography.Text>
          )}
          <input
            ref={input}
            type="file"
            accept={IMAGE_TYPES.join(",")}
            hidden
            aria-label="Tải ảnh lên cho ảnh chèn"
            onChange={(event) => chosen(event.target.files?.[0])}
          />
        </>
      )}
      {error && <Alert type="error" showIcon title={error} />}
    </Flex>
  );

  return (
    <Flex vertical gap={8} data-testid="half-photo-panel">
      {stage}
      <Button
        type="primary"
        block
        icon={<DragOutlined />}
        disabled={frozen}
        onClick={async () => {
          // The box is drawn from the saved text: the text being typed is saved first.
          await editor.flush();
          setPlacing("text");
        }}
      >
        Chỉnh vị trí chữ
      </Button>
      {children}
      {block}
      {placing && (
        <PlaceModal
          scene={scene}
          backdrop={backdrop}
          tab={placing}
          onClose={() => setPlacing(null)}
          onSaved={editor.onSaved}
        />
      )}
      {picking === "stock" && layer && (
        <StockPicker
          sceneId={scene.id}
          videoId={scene.video_id}
          keywords={scene.keywords}
          keywordsEn={scene.keywords_en}
          title="Tìm ảnh cho ảnh chèn"
          onChoose={(hit) => api<VideoDetail>("/layers/half-photo", "POST", { scene_id: scene.id, url: hit.url })}
          onClose={() => setPicking(null)}
        />
      )}
      {picking === "library" && layer && (
        <MediaLibraryPicker
          sceneId={scene.id}
          videoId={scene.video_id}
          hasPicture={!!layer.own_image}
          onUse={(mediaId) => api<VideoDetail>("/layers/half-photo", "POST", { scene_id: scene.id, media_id: mediaId })}
          onClose={() => setPicking(null)}
        />
      )}
    </Flex>
  );
}
