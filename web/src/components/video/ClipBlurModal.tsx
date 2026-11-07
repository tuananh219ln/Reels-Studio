"use client";

import { Button, Flex, Modal, Typography } from "antd";
import { useState } from "react";
import { api, errorMessage, type SceneData, type VideoDetail } from "@/lib/api";
import { useEditor } from "./AutoSaveField";
import { BoxCanvas, type Box } from "./ImageEditModal";

/**
 * "Làm mờ vùng" on a clip scene: boxes drawn over the scene's frame (as the video shows it) are blurred for the whole
 * scene at render, for a logo or a channel name burned into the clip. Saved at once; the next render blurs them.
 */
export default function ClipBlurModal({ scene, onClose }: { scene: SceneData; onClose: () => void }) {
  const editor = useEditor();
  const [boxes, setBoxes] = useState<Box[]>(scene.video?.blur ?? []);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const which = scene.is_title ? "cảnh tiêu đề" : "cảnh";

  async function save(next: Box[]) {
    setSaving(true);
    setError(null);
    try {
      editor.onSaved(await api<VideoDetail>(`/scenes/${scene.id}/video-blur`, "POST", { boxes: next }));
      onClose();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal
      open
      centered
      width={720}
      title={`Làm mờ vùng trên video ${which}`}
      onCancel={onClose}
      footer={[
        (scene.video?.blur.length ?? 0) > 0 && (
          <Button key="clear" danger disabled={saving} onClick={() => void save([])}>
            Bỏ làm mờ
          </Button>
        ),
        <Button key="cancel" onClick={onClose}>
          Huỷ
        </Button>,
        <Button key="save" type="primary" loading={saving} onClick={() => void save(boxes)}>
          Lưu vùng mờ
        </Button>,
      ]}
    >
      <Flex wrap gap={24} align="flex-start">
        <div style={{ flex: "1 1 280px", minWidth: 0, display: "flex", justifyContent: "center" }}>
          <BoxCanvas
            src={scene.frame_url ?? ""}
            alt={`Khung hình của ${which}`}
            boxes={boxes}
            drawing
            onChange={setBoxes}
          />
        </div>
        <Flex vertical gap={12} style={{ flex: "1 1 220px", minWidth: 0 }}>
          <Typography.Text type="secondary">
            Kéo chuột (hoặc ngón tay) để khoanh logo, tên kênh hay chữ dính trên video. Vùng khoanh được làm mờ suốt
            cảnh khi render, nên hợp với logo đứng yên một chỗ.
          </Typography.Text>
          <Typography.Text data-testid="blur-box-count">
            {boxes.length ? `${boxes.length} vùng sẽ được làm mờ` : "Chưa khoanh vùng nào"}
          </Typography.Text>
          {boxes.length > 0 && (
            <Button size="small" onClick={() => setBoxes([])} style={{ alignSelf: "flex-start" }}>
              Bỏ hết khung
            </Button>
          )}
          {error && (
            <Typography.Text type="danger" data-testid="clip-blur-error">
              {error}
            </Typography.Text>
          )}
        </Flex>
      </Flex>
    </Modal>
  );
}
