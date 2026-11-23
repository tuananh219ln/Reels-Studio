"use client";

import { Flex, Select, Slider, Typography } from "antd";
import { useState } from "react";
import { api, errorMessage, type ImageFit, type SceneData, type VideoDetail } from "@/lib/api";
import { useEditor } from "./AutoSaveField";

const KIND_LABELS: Record<ImageFit, string> = {
  cover: "lấp đầy khung",
  square: "cắt vuông, nền mờ",
  whole: "giữ nguyên ảnh, nền mờ",
};

/**
 * "Khung ảnh" of a content scene's photo (api reels_render.framing): fill the 9:16 frame as before, or lay the photo
 * across it over its own blurred copy, cut square or whole, with the text on the blurred part. "Tự động" chooses by
 * the photo's shape. A square cut of a photo that is not square slides along its longer side.
 */
export default function PhotoFrameField({ scene, disabled }: { scene: SceneData; disabled: boolean }) {
  const editor = useEditor();
  const frame = scene.image_frame;
  // The square's place while the slider is dragged; the saved one otherwise.
  const [dragged, setDragged] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!frame) {
    return null;
  }
  const off = disabled || saving || editor.readOnly;
  const [width, height] = frame.shape ?? [0, 0];
  const slides = frame.kind === "square" && frame.shape !== null && width !== height;
  const across = width > height;

  async function save(body: Record<string, unknown>) {
    setSaving(true);
    setError(null);
    try {
      editor.onSaved(await api<VideoDetail>(`/scenes/${scene.id}`, "PATCH", body));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Flex vertical gap={4} data-testid="photo-frame">
      <Flex align="center" gap={6} wrap>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          Khung ảnh
        </Typography.Text>
        <Select
          size="small"
          aria-label="Khung ảnh"
          style={{ minWidth: 200 }}
          value={frame.fit ?? "auto"}
          disabled={off}
          loading={saving}
          onChange={(value: string) => void save({ image_fit: value === "auto" ? null : value })}
          options={[
            { value: "auto", label: frame.fit === null ? `Tự động (${KIND_LABELS[frame.kind]})` : "Tự động" },
            { value: "cover", label: "Lấp đầy khung" },
            { value: "square", label: "Cắt vuông, nền mờ" },
            { value: "whole", label: "Giữ nguyên ảnh, nền mờ" },
          ]}
        />
      </Flex>
      {slides && (
        <Flex align="center" gap={8}>
          <Typography.Text type="secondary" style={{ fontSize: 12, flex: "none" }}>
            {across ? "Trái" : "Trên"}
          </Typography.Text>
          <Slider
            aria-label="Dịch khung vuông"
            style={{ flex: 1, margin: "0 4px" }}
            min={0}
            max={1}
            step={0.01}
            value={dragged ?? frame.offset ?? 0.5}
            disabled={off}
            tooltip={{ open: false }}
            onChange={setDragged}
            onChangeComplete={(value: number) => void save({ image_crop_offset: value }).then(() => setDragged(null))}
          />
          <Typography.Text type="secondary" style={{ fontSize: 12, flex: "none" }}>
            {across ? "Phải" : "Dưới"}
          </Typography.Text>
        </Flex>
      )}
      {error && (
        <Typography.Text type="danger" style={{ fontSize: 12 }}>
          {error}
        </Typography.Text>
      )}
    </Flex>
  );
}
