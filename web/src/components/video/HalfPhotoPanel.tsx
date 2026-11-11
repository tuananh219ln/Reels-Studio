"use client";

import { DeleteOutlined, PictureOutlined } from "@ant-design/icons";
import { Alert, App, Button, Flex, Slider, Switch, Typography } from "antd";
import { useRef, useState, type ReactNode } from "react";
import { api, errorMessage, type SceneData, type SceneLayer, type VideoDetail } from "@/lib/api";
import { useEditor } from "./AutoSaveField";
import PlaceSegmented from "./PlaceSegmented";
import LayerStage from "./preview/LayerStage";
import {
  FRAME_HEIGHT,
  FRAME_WIDTH,
  HALF_HEIGHT_MAX,
  HALF_HEIGHT_MIN,
  halfHeight,
  halfPlaces,
  isHalf,
} from "./preview/layers";
import { placeBox } from "./TextPositionModal";

const percent = (value: number, of: number) => `${(value / of) * 100}%`;

/**
 * "Ảnh chèn" on a content scene's card of a "Video xuyên suốt" (a slide video has none): the video's backdrop playing,
 * with the inset photo over it (edge to edge, 38% of the frame tall, fading into the backdrop) and the scene's text box
 * on top, so the photo is placed against what is really under it. The photo is the scene's own, found and edited with
 * the scene's picture tools; it is dragged up and down (snapping flush with the top edge, the middle and the bottom
 * edge) or placed with "Trên / Giữa / Dưới", and its height is 30–45%.
 *
 * `split` is the scene card's top tier: the one preview on the left, the choice of the photo on the right (`children`
 * goes under the inset's own controls). Not split, everything is stacked, as in the studio's narrow panel.
 */
export default function HalfPhotoPanel({
  scene,
  backdrop,
  split = false,
  children,
}: {
  scene: SceneData;
  /** The title scene of a "Video xuyên suốt": its photo or clip runs under this scene. */
  backdrop: SceneData | null;
  split?: boolean;
  children?: ReactNode;
}) {
  const { modal } = App.useApp();
  const editor = useEditor();
  const frozen = editor.locked || editor.readOnly;
  const stage = useRef<HTMLDivElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [box, setBox] = useState<{ width: number; height: number } | null>(null);
  const layer = scene.layers.find(isHalf);
  // One photo layer per scene: "Ảnh món" takes the place too.
  const otherPhoto = !layer && scene.layers.some((item) => item.kind === "photo");

  async function run(action: () => Promise<VideoDetail>) {
    setBusy(true);
    setError(null);
    try {
      editor.onSaved(await action());
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  /** The inset shows the scene's own photo (a new one, an "Ảnh món" turned into one, or its own let go). */
  const linkScenePhoto = () =>
    run(() => api<VideoDetail>("/layers/half-photo", "POST", { scene_id: scene.id, scene_photo: true }));

  const move = (target: SceneLayer, y: number) => run(() => api<VideoDetail>(`/layers/${target.id}`, "PATCH", { y }));

  const remove = (target: SceneLayer) =>
    modal.confirm({
      title: "Xoá ảnh chèn?",
      content: "Ảnh chèn bị xoá hẳn, không hoàn tác được. Muốn dùng lại thì thêm ảnh lần nữa.",
      okText: "Xoá",
      okButtonProps: { danger: true },
      cancelText: "Huỷ",
      onOk: () => run(() => api<VideoDetail>(`/layers/${target.id}`, "DELETE")),
    });

  const ground = backdrop ?? scene;
  const picture = ground.frame_url ?? ground.preview_url;
  const corner = box && scene.textbox_url ? placeBox(box, scene.placed_at, false) : null;
  // The text may sit over the inset: allowed, and said so under the preview.
  const tall = layer ? halfHeight(layer.height) : 0;
  const insetTop = layer ? layer.y - Math.floor(tall / 2) : 0;
  const overlapping = !!layer && !!corner && !!box && corner[1] < insetTop + tall && corner[1] + box.height > insetTop;

  const stageNode = (
    <div
      ref={stage}
      data-testid="half-photo-stage"
      style={{
        position: "relative",
        width: "100%",
        aspectRatio: `${FRAME_WIDTH} / ${FRAME_HEIGHT}`,
        overflow: "hidden",
        borderRadius: 6,
        background: "#000",
        containerType: "inline-size",
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
      {layer && (
        <LayerStage
          under
          layers={[layer]}
          elapsed={() => layer.start}
          stage={stage}
          selected={null}
          editable={!frozen && !busy}
          onSelect={() => undefined}
          onMove={(target, _x, y) => void move(target, y)}
        />
      )}
      {scene.textbox_url && (
        // The scene's text over the photo, where the render puts it.
        // eslint-disable-next-line @next/next/no-img-element -- drawn by the api with the renderer's own code
        <img
          src={scene.textbox_url}
          alt=""
          draggable={false}
          onLoad={(event) =>
            setBox({ width: event.currentTarget.naturalWidth, height: event.currentTarget.naturalHeight })
          }
          style={{
            position: "absolute",
            pointerEvents: "none",
            visibility: corner ? "visible" : "hidden",
            left: corner ? percent(corner[0], FRAME_WIDTH) : 0,
            top: corner ? percent(corner[1], FRAME_HEIGHT) : 0,
            width: box ? percent(box.width, FRAME_WIDTH) : undefined,
          }}
        />
      )}
    </div>
  );

  const places = layer ? halfPlaces(layer.height) : [];

  const controlsNode = layer ? (
    <Flex vertical gap={8}>
      {layer.own_image === false ? (
        // It shows the scene's photo, so the scene's own picture tools find and edit it.
        <Typography.Text type="secondary" style={{ fontSize: 12 }} data-testid="half-photo-scene-tools">
          Ảnh chèn là ảnh của cảnh: tìm ảnh, tải lên, lấy từ kho, dán link, tạo ảnh AI, chỉnh khung hay sửa ảnh ở khung
          chọn ảnh của cảnh.
        </Typography.Text>
      ) : (
        // One with a photo of its own (added before it took the scene's): back to the scene's, for its tools.
        <Button size="small" icon={<PictureOutlined />} disabled={frozen || busy} onClick={linkScenePhoto}>
          Dùng ảnh của cảnh (để tìm, sửa ảnh)
        </Button>
      )}
      <Flex align="center" gap={16} wrap>
        <PlaceSegmented
          label="Vị trí ảnh chèn"
          value={(places.find((place) => place.y === layer.y)?.value as "top" | "middle" | "bottom") ?? ""}
          disabled={frozen || busy}
          onChange={(value) => {
            const chosen = places.find((place) => place.value === value);
            if (chosen) void move(layer, chosen.y);
          }}
        />
        <Flex align="center" gap={8} style={{ flex: "1 1 180px", minWidth: 140 }}>
          <Typography.Text strong style={{ fontSize: 12, flex: "none" }}>
            Cao
          </Typography.Text>
          <Slider
            style={{ flex: 1, margin: "0 6px" }}
            min={HALF_HEIGHT_MIN}
            max={HALF_HEIGHT_MAX}
            value={layer.height}
            disabled={frozen || busy}
            tooltip={{ formatter: (value) => `${value}%` }}
            onChangeComplete={(value) =>
              void run(() => api<VideoDetail>(`/layers/${layer.id}`, "PATCH", { height: value }))
            }
          />
          <Typography.Text type="secondary" style={{ fontSize: 12, flex: "none" }}>
            {layer.height}%
          </Typography.Text>
        </Flex>
      </Flex>
      {!split && (
        <Button size="small" danger icon={<DeleteOutlined />} disabled={frozen || busy} onClick={() => remove(layer)}>
          Xoá ảnh chèn
        </Button>
      )}
    </Flex>
  ) : (
    <Flex vertical gap={6}>
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        {otherPhoto
          ? "Cảnh đang dùng ảnh món (cỡ Nhỏ/Vừa/Lớn). Đổi sang ảnh chèn để ảnh tràn sát hai mép, cao khoảng 38% khung."
          : "Ảnh tràn ngang khung, cao khoảng 1/3, hiện cùng lời đọc đến hết cảnh."}
      </Typography.Text>
      {!split && (
        // The scene's photo, found and edited with the scene's tools below the card's frame.
        <Button
          size="small"
          type="primary"
          icon={<PictureOutlined />}
          disabled={frozen || busy}
          onClick={linkScenePhoto}
        >
          {otherPhoto ? "Đổi ảnh món thành ảnh chèn" : "Thêm ảnh chèn"}
        </Button>
      )}
    </Flex>
  );

  const notes = (
    <>
      {overlapping && <Alert type="warning" showIcon title="Chữ đang đè lên ảnh chèn" data-testid="text-over-inset" />}
      {error && <Alert type="error" showIcon title={error} />}
    </>
  );

  if (split) {
    return (
      <div className="inset-split" data-testid="half-photo-panel">
        <div className="inset-split__preview">
          <Flex vertical gap={4}>
            {stageNode}
            <Typography.Text type="secondary" style={{ fontSize: 12, textAlign: "center" }}>
              1 preview gộp, cập nhật ngay
            </Typography.Text>
          </Flex>
        </div>
        <Flex vertical gap={10} className="inset-split__controls">
          <Flex align="center" gap={8} wrap>
            <Typography.Text strong>Ảnh chèn</Typography.Text>
            <Switch
              size="small"
              aria-label={layer ? "Xoá ảnh chèn" : otherPhoto ? "Đổi ảnh món thành ảnh chèn" : "Thêm ảnh chèn"}
              checked={!!layer}
              disabled={frozen || busy}
              onChange={(on) => (on ? void linkScenePhoto() : layer && remove(layer))}
            />
          </Flex>
          {controlsNode}
          {notes}
          {children}
        </Flex>
      </div>
    );
  }

  return (
    <Flex vertical gap={6} data-testid="half-photo-panel">
      <Typography.Text strong style={{ fontSize: 12 }}>
        Ảnh chèn
      </Typography.Text>
      {stageNode}
      {controlsNode}
      {notes}
      {children}
    </Flex>
  );
}
