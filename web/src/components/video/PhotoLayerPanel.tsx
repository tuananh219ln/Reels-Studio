"use client";

import { Alert, Flex, Segmented, Switch, Typography } from "antd";
import { useState } from "react";
import { api, errorMessage, type SceneData, type SceneLayer, type VideoDetail } from "@/lib/api";
import { useEditor } from "./AutoSaveField";
import { ANIMATIONS } from "./preview/layers";
import { PHOTO_PLACES, PHOTO_SHAPES, PHOTO_SIZES, photoLayer } from "./videoModes";

/**
 * "Ảnh món trong cảnh này" on a scene of a "Video xuyên suốt": a photo layer that shows the scene's own photo (chosen
 * with the scene's picture tools) framed over the backdrop, for the whole scene. Its frame, size, place and entrance
 * are named presets; the studio drags it anywhere.
 */
export default function PhotoLayerPanel({ scene }: { scene: SceneData }) {
  const editor = useEditor();
  const frozen = editor.locked || editor.readOnly;
  const layer = photoLayer(scene.layers);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

  const change = (fields: Partial<SceneLayer>) =>
    layer && run(() => api<VideoDetail>(`/layers/${layer.id}`, "PATCH", fields));
  const place = layer ? PHOTO_PLACES.find((item) => item.x === layer.x && item.y === layer.y)?.label : undefined;

  return (
    <Flex vertical gap={8} data-testid="photo-layer">
      <Flex align="center" gap={8}>
        <Switch
          size="small"
          checked={Boolean(layer)}
          loading={busy}
          disabled={frozen}
          aria-label="Ảnh món trong cảnh này"
          onChange={(on) =>
            run(() =>
              on
                ? api<VideoDetail>("/layers", "POST", { scene_id: scene.id, kind: "photo" })
                : api<VideoDetail>(`/layers/${layer!.id}`, "DELETE"),
            )
          }
        />
        <Typography.Text>Ảnh món trong cảnh này</Typography.Text>
      </Flex>
      {!layer && (
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          Cảnh dùng nền chung của video (ảnh hoặc video ở cảnh tiêu đề). Bật để chồng ảnh một món lên nền.
        </Typography.Text>
      )}
      {layer && (
        <Flex vertical gap={6}>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            Ảnh món là ảnh của cảnh này: chọn ở khung ảnh bên dưới (tìm ảnh, tải lên, kho tư liệu hay ảnh AI). Kéo ảnh
            tới chỗ bất kỳ trong Xem trước.
          </Typography.Text>
          <Option label="Khung">
            <Segmented
              size="small"
              value={layer.style}
              disabled={frozen || busy}
              options={PHOTO_SHAPES}
              onChange={(style) => change({ style: style as string })}
            />
          </Option>
          <Option label="Cỡ">
            <Segmented
              size="small"
              value={layer.size}
              disabled={frozen || busy}
              options={PHOTO_SIZES}
              onChange={(size) => change({ size: size as string })}
            />
          </Option>
          <Option label="Vị trí">
            <Segmented
              size="small"
              // A place dragged in the studio matches none of the quick places.
              value={place ?? ""}
              disabled={frozen || busy}
              options={PHOTO_PLACES.map((item) => item.label)}
              onChange={(label) => {
                const chosen = PHOTO_PLACES.find((item) => item.label === label)!;
                void change({ x: chosen.x, y: chosen.y });
              }}
            />
          </Option>
          <Option label="Hiện ra">
            <Segmented
              size="small"
              value={layer.animation}
              disabled={frozen || busy}
              options={ANIMATIONS}
              onChange={(animation) => change({ animation: animation as string })}
            />
          </Option>
        </Flex>
      )}
      {error && <Alert type="error" showIcon title={error} />}
    </Flex>
  );
}

function Option({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <Flex align="center" gap={8} wrap>
      <Typography.Text type="secondary" style={{ width: 56, flex: "none" }}>
        {label}
      </Typography.Text>
      {children}
    </Flex>
  );
}
