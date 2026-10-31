"use client";

import {
  ArrowDownOutlined,
  ArrowUpOutlined,
  DeleteOutlined,
  UploadOutlined,
  VideoCameraOutlined,
} from "@ant-design/icons";
import { App, Alert, Button, Card, Col, Flex, Popconfirm, Row, Space, Tooltip, Typography } from "antd";
import { cloneElement, useRef, useState } from "react";
import { api, errorMessage, upload, type SceneData, type VideoDetail } from "@/lib/api";
import AutoSaveField, { useEditor } from "./AutoSaveField";
import VoiceText from "./VoiceText";

const MAX_IMAGE_BYTES = 15 * 1024 * 1024;
const IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"];
const MAX_VIDEO_BYTES = 50 * 1024 * 1024;
const VIDEO_TYPES = ["video/mp4", "video/quicktime", "video/webm"];

function parseSeconds(text: string): number {
  const seconds = Number(text.trim().replace(",", "."));
  if (!text.trim() || !Number.isFinite(seconds)) {
    throw new Error("Nhập số giây, ví dụ 4 hoặc 3,5");
  }
  return seconds;
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
  const patch = (
    body: Partial<Pick<SceneData, "text" | "seconds" | "image_prompt" | "voice_text">> & {
      video_start?: number;
    },
  ) => api<VideoDetail>(`/scenes/${scene.id}`, "PATCH", body);

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
              hint="*từ* để tô đỏ, xuống dòng để ngắt dòng, để trống nếu cảnh không hiện chữ"
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
              {scene.video && (
                <AutoSaveField
                  label="Bắt đầu từ giây"
                  value={String(scene.video.start)}
                  inputMode="decimal"
                  width={130}
                  save={async (text) => patch({ video_start: parseSeconds(text) })}
                />
              )}
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
  const video = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState<"upload" | "video" | "remove" | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run(kind: "upload" | "video" | "remove", action: () => Promise<VideoDetail>) {
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

  function chosenVideo(file: File | undefined) {
    if (video.current) {
      video.current.value = "";
    }
    if (!file) {
      return;
    }
    if (!VIDEO_TYPES.includes(file.type)) {
      message.error("Video phải là MP4, MOV hoặc WebM");
      return;
    }
    if (file.size > MAX_VIDEO_BYTES) {
      message.error("Video quá 50 MB, hãy chọn video ngắn hơn hoặc nén nhỏ lại");
      return;
    }
    void run("video", () => upload<VideoDetail>(`/scenes/${scene.id}/video`, file));
  }

  const frame = { width: "100%", aspectRatio: "9 / 16", borderRadius: 6 } as const;
  const hasPicture = scene.has_image || scene.video !== null;
  const reason = scene.text_problem && hasPicture ? scene.text_problem : null;
  const off = editor.locked || busy !== null;
  const which = scene.is_title ? "cảnh tiêu đề" : "cảnh";

  return (
    <Flex vertical gap={8}>
      {scene.preview_url && !reason ? (
        // A plain <img>: the preview is drawn by the api with the renderer's own code.
        // eslint-disable-next-line @next/next/no-img-element
        <img src={scene.preview_url} alt={`Xem trước ${scene.is_title ? "cảnh tiêu đề" : "cảnh"}`}
          style={{ ...frame, objectFit: "cover", display: "block" }} data-testid="scene-preview" />
      ) : (
        <Flex align="center" justify="center" data-testid="scene-no-preview"
          style={{ ...frame, padding: 12, textAlign: "center", boxSizing: "border-box",
            background: hasPicture ? "#FFF7E6" : "#FFF1F0",
            border: `1px solid ${hasPicture ? "#FFD591" : "#FFA39E"}` }}>
          <Typography.Text type="danger">
            {reason ?? scene.image_error ?? "Chưa có ảnh"}
          </Typography.Text>
        </Flex>
      )}
      {scene.video && (
        // The clip as uploaded, without sound: the render never uses its sound either.
        <video src={scene.video.url} muted loop playsInline controls preload="metadata"
          aria-label={`Video của ${which}`} data-testid="scene-video"
          style={{ width: "100%", maxHeight: 200, borderRadius: 6, background: "#000" }} />
      )}
      <input ref={input} type="file" accept="image/jpeg,image/png,image/webp" hidden
        aria-label={`Tải ảnh lên cho ${which}`}
        onChange={(event) => chosen(event.target.files?.[0])} />
      <input ref={video} type="file" accept="video/mp4,video/quicktime,video/webm" hidden
        aria-label={`Tải video lên cho ${which}`}
        onChange={(event) => chosenVideo(event.target.files?.[0])} />
      <Switching show={scene.has_image} title="Video sẽ thay ảnh của cảnh này?" disabled={off}
        onConfirm={() => video.current?.click()}>
        <Button icon={<VideoCameraOutlined />} loading={busy === "video"} disabled={off}>
          Tải video lên
        </Button>
      </Switching>
      {scene.video && (
        <Popconfirm title="Xoá video của cảnh này?" okText="Xoá" cancelText="Huỷ" okButtonProps={{ danger: true }}
          disabled={off}
          onConfirm={() => run("remove", () => api<VideoDetail>(`/scenes/${scene.id}/video`, "DELETE"))}>
          <Button danger icon={<DeleteOutlined />} loading={busy === "remove"} disabled={off}>
            Xoá video
          </Button>
        </Popconfirm>
      )}
      <Switching show={scene.video !== null} title="Ảnh sẽ thay video của cảnh này?" disabled={off}
        onConfirm={() => input.current?.click()}>
        <Button icon={<UploadOutlined />} loading={busy === "upload"} disabled={off}>
          Tải ảnh lên
        </Button>
      </Switching>
      {error && <Typography.Text type="danger" data-testid="image-error">{error}</Typography.Text>}
    </Flex>
  );
}

/** A photo and a clip replace each other, so switching from one to the other asks first; otherwise a plain click. */
function Switching({
  show,
  title,
  disabled,
  onConfirm,
  children,
}: {
  show: boolean;
  title: string;
  disabled: boolean;
  onConfirm: () => void;
  children: React.ReactElement<{ onClick?: () => void }>;
}) {
  if (!show) {
    return cloneElement(children, { onClick: disabled ? undefined : onConfirm });
  }
  return (
    <Popconfirm title={title} okText="Đổi" cancelText="Huỷ" disabled={disabled} onConfirm={onConfirm}>
      {children}
    </Popconfirm>
  );
}
