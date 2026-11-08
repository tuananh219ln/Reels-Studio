"use client";

import { DeleteOutlined, PictureOutlined } from "@ant-design/icons";
import { Alert, App, Button, Flex, Segmented, Typography } from "antd";
import { useRef, useState } from "react";
import { api, errorMessage, type SceneData, type SceneLayer, type VideoDetail } from "@/lib/api";
import { useEditor } from "./AutoSaveField";
import LayerStage from "./preview/LayerStage";
import { FRAME_HEIGHT, FRAME_WIDTH, HALF_PLACES, isHalf } from "./preview/layers";
import { placeBox } from "./TextPositionModal";

const percent = (value: number, of: number) => `${(value / of) * 100}%`;

/**
 * "Ảnh chèn nửa khung" on a content scene's card of a "Video xuyên suốt" (a slide video has none): the video's
 * backdrop playing, with the half-frame photo over it and the scene's text box on top, so the photo is placed against
 * what is really under it. The photo is the scene's own, found and edited with the scene's picture tools, as "Ảnh món"
 * was; it is dragged up and down (snapping to the top half, the middle and the bottom half) or placed with a quick
 * choice.
 */
export default function HalfPhotoPanel({
  scene,
  backdrop,
}: {
  scene: SceneData;
  /** The title scene of a "Video xuyên suốt": its photo or clip runs under this scene. */
  backdrop: SceneData | null;
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

  /** The half-frame photo shows the scene's own photo (a new one, an "Ảnh món" turned into one, or its own let go). */
  const linkScenePhoto = () =>
    run(() => api<VideoDetail>("/layers/half-photo", "POST", { scene_id: scene.id, scene_photo: true }));

  const move = (target: SceneLayer, y: number) => run(() => api<VideoDetail>(`/layers/${target.id}`, "PATCH", { y }));

  const ground = backdrop ?? scene;
  const picture = ground.frame_url ?? ground.preview_url;
  const corner = box && scene.textbox_url ? placeBox(box, scene.placed_at, false) : null;

  return (
    <Flex vertical gap={6} data-testid="half-photo-panel">
      <Typography.Text strong style={{ fontSize: 12 }}>
        Ảnh chèn nửa khung
      </Typography.Text>
      {
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
      }
      {layer ? (
        <>
          {layer.own_image === false ? (
            // It shows the scene's photo, so the scene's own picture tools find and edit it.
            <Typography.Text type="secondary" style={{ fontSize: 12 }} data-testid="half-photo-scene-tools">
              Ảnh chèn là ảnh của cảnh: tìm ảnh, tải lên, lấy từ kho, dán link, tạo ảnh AI, chỉnh khung hay sửa ảnh ở
              khung ảnh của cảnh bên dưới.
            </Typography.Text>
          ) : (
            // One with a photo of its own (added before it took the scene's): back to the scene's, for its tools.
            <Button size="small" icon={<PictureOutlined />} disabled={frozen || busy} onClick={linkScenePhoto}>
              Dùng ảnh của cảnh (để tìm, sửa ảnh)
            </Button>
          )}
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            Kéo ảnh lên xuống trong khung, hoặc chọn nhanh:
          </Typography.Text>
          <Segmented
            size="small"
            block
            aria-label="Vị trí ảnh chèn"
            value={HALF_PLACES.find((place) => place.y === layer.y)?.label ?? ""}
            disabled={frozen || busy}
            options={HALF_PLACES.map((place) => place.label)}
            onChange={(label) => {
              const chosen = HALF_PLACES.find((place) => place.label === label);
              if (chosen) void move(layer, chosen.y);
            }}
          />
          <Button
            size="small"
            danger
            icon={<DeleteOutlined />}
            disabled={frozen || busy}
            onClick={() =>
              modal.confirm({
                title: "Xoá ảnh chèn?",
                content: "Ảnh chèn bị xoá hẳn, không hoàn tác được. Muốn dùng lại thì thêm ảnh lần nữa.",
                okText: "Xoá",
                okButtonProps: { danger: true },
                cancelText: "Huỷ",
                onOk: () => run(() => api<VideoDetail>(`/layers/${layer.id}`, "DELETE")),
              })
            }
          >
            Xoá ảnh chèn
          </Button>
        </>
      ) : (
        <>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {otherPhoto
              ? "Cảnh đang dùng ảnh món (cỡ Nhỏ/Vừa/Lớn). Đổi sang ảnh chèn để ảnh rộng hết khung 1080, cao nửa khung."
              : "Ảnh rộng hết khung, cao nửa khung, viền trắng, hiện cùng lời đọc đến hết cảnh."}
          </Typography.Text>
          {/* The scene's photo, found and edited with the scene's tools below the card's frame. */}
          <Button
            size="small"
            type="primary"
            icon={<PictureOutlined />}
            disabled={frozen || busy}
            onClick={linkScenePhoto}
          >
            {otherPhoto ? "Đổi ảnh món thành ảnh chèn" : "Thêm ảnh chèn"}
          </Button>
        </>
      )}
      {error && <Alert type="error" showIcon title={error} />}
    </Flex>
  );
}
