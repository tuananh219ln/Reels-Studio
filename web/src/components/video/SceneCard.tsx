"use client";

import {
  ArrowDownOutlined,
  ArrowUpOutlined,
  DeleteOutlined,
  PictureOutlined,
  ReloadOutlined,
  UploadOutlined,
} from "@ant-design/icons";
import { App, Alert, Button, Card, Col, Flex, Popconfirm, Row, Space, Tooltip, Typography } from "antd";
import { useRef, useState } from "react";
import { api, errorMessage, upload, type SceneData, type VideoDetail } from "@/lib/api";
import AutoSaveField, { useEditor } from "./AutoSaveField";
import VoiceText from "./VoiceText";
import PixabayPicker from "./PixabayPicker";

const MAX_IMAGE_BYTES = 15 * 1024 * 1024;
const IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"];

function parseSeconds(text: string): number {
  const seconds = Number(text.trim().replace(",", "."));
  if (!text.trim() || !Number.isFinite(seconds)) {
    throw new Error("Nhập số giây, ví dụ 4 hoặc 3,5");
  }
  return seconds;
}

function parseKeywords(text: string): string[] {
  return text
    .split(",")
    .map((keyword) => keyword.trim())
    .filter(Boolean);
}

export default function SceneCard({
  scene,
  label,
  voiceEnabled,
  onMove,
  onDelete,
}: {
  scene: SceneData;
  label: string;
  voiceEnabled: boolean;
  onMove?: (step: -1 | 1) => void;
  onDelete?: () => void;
}) {
  const editor = useEditor();
  const patch = (body: Partial<Pick<SceneData, "text" | "seconds" | "keywords" | "image_prompt" | "voice_text">>) =>
    api<VideoDetail>(`/scenes/${scene.id}`, "PATCH", body);

  return (
    <Card
      data-testid={scene.is_title ? "title-scene" : "scene"}
      title={label}
      size="small"
      extra={
        !scene.is_title && (
          <Space size={4}>
            <Tooltip title="Lên trên">
              <Button aria-label="Lên trên" size="small" icon={<ArrowUpOutlined />} disabled={editor.locked || !onMove}
                onClick={() => onMove?.(-1)} />
            </Tooltip>
            <Tooltip title="Xuống dưới">
              <Button aria-label="Xuống dưới" size="small" icon={<ArrowDownOutlined />}
                disabled={editor.locked || !onMove} onClick={() => onMove?.(1)} />
            </Tooltip>
            <Popconfirm title="Xóa cảnh này?" okText="Xóa" cancelText="Huỷ" okButtonProps={{ danger: true }}
              onConfirm={onDelete} disabled={editor.locked}>
              <Button aria-label="Xóa cảnh" size="small" danger icon={<DeleteOutlined />} disabled={editor.locked} />
            </Popconfirm>
          </Space>
        )
      }
    >
      <Row gutter={[16, 12]}>
        <Col xs={24} sm={9} md={7}>
          <ScenePicture scene={scene} />
        </Col>
        <Col xs={24} sm={15} md={17}>
          <Flex vertical gap={4}>
            <AutoSaveField
              label="Chữ trên màn hình"
              value={scene.text}
              multiline
              save={(text) => patch({ text })}
              hint="*từ* để tô đỏ, xuống dòng để ngắt dòng"
            />
            {voiceEnabled && <VoiceText scene={scene} save={(voice_text) => patch({ voice_text })} />}
            <Flex wrap gap={16}>
              <AutoSaveField
                label="Số giây"
                value={String(scene.seconds)}
                inputMode="decimal"
                width={110}
                save={async (text) => patch({ seconds: parseSeconds(text) })}
              />
              <div style={{ flex: 1, minWidth: 220 }}>
                <AutoSaveField
                  label="Từ khóa tìm ảnh"
                  value={scene.keywords.join(", ")}
                  placeholder="cụ thể nhất trước, cách nhau bằng dấu phẩy"
                  save={(text) => patch({ keywords: parseKeywords(text) })}
                />
              </div>
            </Flex>
            {!scene.is_title && (
              <AutoSaveField
                label="Prompt ảnh 9:16"
                value={scene.image_prompt}
                multiline
                save={(text) => patch({ image_prompt: text })}
              />
            )}
            {scene.blocking.map((reason) => (
              <Alert key={reason} type="error" showIcon title={reason} data-testid="scene-blocking" />
            ))}
            {scene.warnings.map((warning) => (
              <Alert key={warning} type="warning" showIcon title={warning} data-testid="scene-warning" />
            ))}
          </Flex>
        </Col>
      </Row>
    </Card>
  );
}

function ScenePicture({ scene }: { scene: SceneData }) {
  const { message } = App.useApp();
  const editor = useEditor();
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState<"upload" | "find" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [picking, setPicking] = useState(false);

  async function run(kind: "upload" | "find", action: () => Promise<VideoDetail>) {
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

  function chosen(file: File | undefined) {
    if (input.current) {
      input.current.value = "";
    }
    if (!file) {
      return;
    }
    if (!IMAGE_TYPES.includes(file.type)) {
      message.error("Ảnh phải là JPG, PNG hoặc WebP");
      return;
    }
    if (file.size > MAX_IMAGE_BYTES) {
      message.error("Ảnh quá 15 MB, hãy chọn ảnh nhỏ hơn");
      return;
    }
    void run("upload", () => upload<VideoDetail>(`/scenes/${scene.id}/image`, file));
  }

  const frame = { width: "100%", aspectRatio: "9 / 16", borderRadius: 6 } as const;
  const reason = scene.text_problem && scene.has_image ? scene.text_problem : null;
  const noKeywords = scene.keywords.length === 0;

  return (
    <Flex vertical gap={8}>
      {scene.preview_url && !reason ? (
        // A plain <img>: the preview is drawn by the api with the renderer's own code.
        <img src={scene.preview_url} alt={`Xem trước ${scene.is_title ? "cảnh tiêu đề" : "cảnh"}`}
          style={{ ...frame, objectFit: "cover", display: "block" }} data-testid="scene-preview" />
      ) : (
        <Flex align="center" justify="center" data-testid="scene-no-preview"
          style={{ ...frame, padding: 12, textAlign: "center", boxSizing: "border-box",
            background: scene.has_image ? "#FFF7E6" : "#FFF1F0",
            border: `1px solid ${scene.has_image ? "#FFD591" : "#FFA39E"}` }}>
          <Typography.Text type="danger">
            {reason ?? scene.image_error ?? "Chưa có ảnh"}
          </Typography.Text>
        </Flex>
      )}
      <input ref={input} type="file" accept="image/jpeg,image/png,image/webp" hidden
        aria-label={`Tải ảnh lên cho ${scene.is_title ? "cảnh tiêu đề" : "cảnh"}`}
        onChange={(event) => chosen(event.target.files?.[0])} />
      <Button icon={<UploadOutlined />} loading={busy === "upload"} disabled={editor.locked || busy !== null}
        onClick={() => input.current?.click()}>
        Tải ảnh lên
      </Button>
      <Tooltip title={noKeywords ? "Nhập từ khóa để tìm ảnh" : undefined}>
        <Button icon={<ReloadOutlined />} loading={busy === "find"}
          disabled={editor.locked || busy !== null || noKeywords}
          onClick={() =>
            run("find", async () => {
              // Search with the keywords on screen: their save (started by leaving the field) goes first.
              await editor.flush();
              return api<VideoDetail>(`/scenes/${scene.id}/find-image`, "POST");
            })
          }>
          Tìm lại ảnh
        </Button>
      </Tooltip>
      <Button icon={<PictureOutlined />} disabled={editor.locked || busy !== null}
        onClick={async () => {
          // The grid starts from the keywords on screen, so their save goes first.
          await editor.flush();
          setPicking(true);
        }}>
        Chọn từ Pixabay
      </Button>
      {error && <Typography.Text type="danger" data-testid="image-error">{error}</Typography.Text>}
      <PixabayPicker sceneId={scene.id} keyword={scene.keywords[0] ?? ""} open={picking}
        onClose={() => setPicking(false)} />
    </Flex>
  );
}
