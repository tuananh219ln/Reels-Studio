"use client";

import {
  ArrowDownOutlined,
  ArrowUpOutlined,
  DeleteOutlined,
  DownOutlined,
  DragOutlined,
  InboxOutlined,
  PictureOutlined,
  PlayCircleOutlined,
  RightOutlined,
  ScissorOutlined,
  SearchOutlined,
  SwapOutlined,
} from "@ant-design/icons";
import {
  App,
  Alert,
  Button,
  Card,
  Col,
  Dropdown,
  Flex,
  Popconfirm,
  Row,
  Space,
  Spin,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import { cloneElement, useRef, useState } from "react";
import { api, errorMessage, upload, type SceneData, type StockSource, type VideoDetail } from "@/lib/api";
import AutoSaveField, { useEditor } from "./AutoSaveField";
import MediaEditor from "./MediaEditor";
import StockPicker from "./StockPicker";
import TextPositionModal from "./TextPositionModal";
import VoiceText from "./VoiceText";

const MAX_IMAGE_BYTES = 15 * 1024 * 1024;
const IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"];
const MAX_VIDEO_BYTES = 50 * 1024 * 1024;
const VIDEO_TYPES = ["video/mp4", "video/quicktime", "video/webm"];
// The script's lengths (docs/content.md): at most 10 words on a scene, 12 on the title.
const MAX_SCENE_WORDS = 10;
const MAX_TITLE_WORDS = 12;
const TEXT_HELP =
  "Bọc một từ trong dấu sao (*từ*) để tô đỏ từ đó. Xuống dòng để ngắt dòng trên video. " +
  "Để trống nếu cảnh không hiện chữ.";

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
  expanded,
  onToggle,
  onMove,
  onDelete,
  onPreview,
}: {
  scene: SceneData;
  label: string;
  voiceEnabled: boolean;
  expanded: boolean;
  onToggle: () => void;
  /** "Xem từ cảnh này": the browser preview, starting at this scene. */
  onPreview?: () => void;
  onMove?: (step: -1 | 1) => void;
  onDelete?: () => void;
}) {
  const editor = useEditor();
  const frozen = editor.locked || editor.readOnly;
  const patch = (
    body: Partial<Pick<SceneData, "text" | "seconds" | "keywords" | "image_prompt" | "voice_text">> & {
      video_start?: number;
    },
  ) => api<VideoDetail>(`/scenes/${scene.id}`, "PATCH", body);

  return (
    <Card
      data-testid={scene.is_title ? "title-scene" : "scene"}
      title={<SceneHeader scene={scene} label={label} expanded={expanded} onToggle={onToggle} />}
      size="small"
      // A closed card keeps its fields mounted, so text not yet saved is never lost by closing it.
      styles={{ body: expanded ? undefined : { display: "none" } }}
      extra={
        <Space size={4}>
          {onPreview && (
            <Tooltip title="Xem từ cảnh này">
              <Button
                aria-label="Xem từ cảnh này"
                size="small"
                icon={<PlayCircleOutlined />}
                onClick={async () => {
                  // The preview shows the saved scene: the field being typed in is saved first.
                  await editor.flush();
                  onPreview();
                }}
              />
            </Tooltip>
          )}
          {!scene.is_title && (
            <>
              <Tooltip title="Lên trên">
                <Button
                  aria-label="Lên trên"
                  size="small"
                  icon={<ArrowUpOutlined />}
                  disabled={frozen || !onMove}
                  onClick={() => onMove?.(-1)}
                />
              </Tooltip>
              <Tooltip title="Xuống dưới">
                <Button
                  aria-label="Xuống dưới"
                  size="small"
                  icon={<ArrowDownOutlined />}
                  disabled={frozen || !onMove}
                  onClick={() => onMove?.(1)}
                />
              </Tooltip>
              <Popconfirm
                title="Xóa cảnh này?"
                okText="Xóa"
                cancelText="Huỷ"
                okButtonProps={{ danger: true }}
                onConfirm={onDelete}
                disabled={frozen}
              >
                <Button aria-label="Xóa cảnh" size="small" danger icon={<DeleteOutlined />} disabled={frozen} />
              </Popconfirm>
            </>
          )}
        </Space>
      }
    >
      <Row gutter={[16, 12]}>
        <Col xs={24} sm={9} md={8}>
          {/* On a phone the column is the full width: keep the 9:16 frame a thumbnail, centred. */}
          <div style={{ maxWidth: 220, margin: "0 auto" }}>
            <ScenePicture scene={scene} voiceEnabled={voiceEnabled} />
          </div>
        </Col>
        <Col xs={24} sm={15} md={16}>
          <Flex vertical gap={4}>
            <AutoSaveField
              label="Chữ trên màn hình"
              value={scene.text}
              multiline
              save={(text) => patch({ text })}
              help={TEXT_HELP}
              words={{ max: scene.is_title ? MAX_TITLE_WORDS : MAX_SCENE_WORDS }}
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
            <AutoSaveField
              label="Từ khóa tìm ảnh"
              value={scene.keywords.join(", ")}
              placeholder="cụ thể nhất trước, cách nhau bằng dấu phẩy"
              save={(text) => patch({ keywords: parseKeywords(text) })}
            />
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

/** The card's title row; a click anywhere on it opens or closes the card. Closed, it sums the scene up. */
function SceneHeader({
  scene,
  label,
  expanded,
  onToggle,
}: {
  scene: SceneData;
  label: string;
  expanded: boolean;
  onToggle: () => void;
}) {
  const summary = scene.text.replaceAll("*", "").replace(/\s+/g, " ").trim();
  const status =
    scene.blocking.length > 0 ? (
      <Tag color="error">{scene.blocking.length} lỗi</Tag>
    ) : scene.warnings.length > 0 ? (
      <Tag color="warning">{scene.warnings.length} cảnh báo</Tag>
    ) : (
      <Tag color="success">Sẵn sàng</Tag>
    );
  return (
    <Flex
      role="button"
      tabIndex={0}
      aria-expanded={expanded}
      aria-label={`${expanded ? "Thu gọn" : "Mở"} ${label}`}
      data-testid="scene-toggle"
      align="center"
      gap={10}
      style={{ cursor: "pointer", minWidth: 0, padding: "6px 0" }}
      onClick={onToggle}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onToggle();
        }
      }}
    >
      <RightOutlined
        style={{
          fontSize: 12,
          color: "#8c8c8c",
          transition: "transform 0.2s",
          transform: `rotate(${expanded ? 90 : 0}deg)`,
        }}
      />
      {!expanded &&
        (scene.preview_url ? (
          // eslint-disable-next-line @next/next/no-img-element -- the api draws the preview; next/image adds nothing
          <img
            src={scene.preview_url}
            alt=""
            style={{ width: 40, height: 40, objectFit: "cover", borderRadius: 6, flex: "none" }}
          />
        ) : (
          <div style={{ width: 40, height: 40, borderRadius: 6, background: "#f0f0f0", flex: "none" }} />
        ))}
      <Typography.Text strong style={{ flex: "none" }}>
        {label}
      </Typography.Text>
      <Typography.Text type="secondary" style={{ flex: "none", fontWeight: "normal" }}>
        {scene.seconds.toLocaleString("vi-VN", { maximumFractionDigits: 1 })}s
      </Typography.Text>
      {!expanded && (
        <Typography.Text
          type="secondary"
          ellipsis
          style={{ flex: 1, minWidth: 0, fontWeight: "normal" }}
          data-testid="scene-summary"
        >
          {summary || "(không có chữ)"}
        </Typography.Text>
      )}
      <span style={{ marginLeft: expanded ? "auto" : 0, flex: "none" }}>{status}</span>
    </Flex>
  );
}

type Busy = "upload" | "video" | "remove" | "find";

const PIXABAY: StockSource = { id: "pixabay", label: "Pixabay", available: true };

function ScenePicture({ scene, voiceEnabled }: { scene: SceneData; voiceEnabled: boolean }) {
  const { message, modal } = App.useApp();
  const editor = useEditor();
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState<Busy | null>(null);
  const [error, setError] = useState<{ kind: Busy; message: string } | null>(null);
  const [picking, setPicking] = useState(false);
  const [placing, setPlacing] = useState(false);
  const [framing, setFraming] = useState(false);
  const [dragging, setDragging] = useState(false);
  // Where "Tìm ảnh khác" searches: Pixabay until the member picks another source from the arrow menu.
  const [findSource, setFindSource] = useState<StockSource>(PIXABAY);
  const [sources, setSources] = useState<StockSource[] | null>(null);

  async function loadSources() {
    if (sources !== null) {
      return;
    }
    try {
      const offered = (await api<StockSource[]>("/stock/sources")).filter((item) => item.available);
      setSources(offered.length > 0 ? offered : [PIXABAY]);
    } catch {
      setSources([PIXABAY]);
    }
  }

  // Busy and errors are this scene's own: working on one scene never blocks the others.
  async function run(kind: Busy, action: () => Promise<VideoDetail>) {
    setBusy(kind);
    setError(null);
    try {
      editor.onSaved(await action());
    } catch (err) {
      setError({ kind, message: errorMessage(err) });
    } finally {
      setBusy(null);
    }
  }

  /** A dropped or chosen file: a photo or a clip, each checked like the api does, asking first when it swaps kinds. */
  function chosen(file: File | undefined) {
    if (input.current) {
      input.current.value = "";
    }
    if (!file) {
      return;
    }
    const photo = IMAGE_TYPES.includes(file.type);
    const clip = VIDEO_TYPES.includes(file.type);
    if (!photo && !clip) {
      message.error("Chỉ nhận ảnh JPG, PNG, WebP hoặc video MP4, MOV, WebM");
      return;
    }
    if (photo && file.size > MAX_IMAGE_BYTES) {
      message.error("Ảnh quá 15 MB, hãy chọn ảnh nhỏ hơn");
      return;
    }
    if (clip && file.size > MAX_VIDEO_BYTES) {
      message.error("Video quá 50 MB, hãy chọn video ngắn hơn hoặc nén nhỏ lại");
      return;
    }
    const send = () =>
      photo
        ? run("upload", () => upload<VideoDetail>(`/scenes/${scene.id}/image`, file))
        : run("video", () => upload<VideoDetail>(`/scenes/${scene.id}/video`, file));
    const swaps = photo ? scene.video !== null : scene.has_image;
    if (!swaps) {
      void send();
      return;
    }
    modal.confirm({
      title: photo ? "Ảnh sẽ thay video của cảnh này?" : "Video sẽ thay ảnh của cảnh này?",
      okText: "Đổi",
      cancelText: "Huỷ",
      onOk: () => void send(),
    });
  }

  const frame = { width: "100%", aspectRatio: "9 / 16", borderRadius: 6 } as const;
  const hasPicture = scene.has_image || scene.video !== null;
  const reason = scene.text_problem && hasPicture ? scene.text_problem : null;
  const off = editor.locked || editor.readOnly || busy !== null;
  const which = scene.is_title ? "cảnh tiêu đề" : "cảnh";
  const canPlace = !!scene.preview_url && !reason && !!scene.textbox_url && !!scene.frame_url;
  const uploading = busy === "upload" || busy === "video";

  return (
    <Flex vertical gap={8}>
      <div className="scene-media" style={{ position: "relative" }}>
        {scene.preview_url && !reason ? (
          // A plain <img>: the preview is drawn by the api with the renderer's own code.
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={scene.preview_url}
            alt={`Xem trước ${which}`}
            style={{ ...frame, objectFit: "cover", display: "block" }}
            data-testid="scene-preview"
          />
        ) : (
          <Flex
            align="center"
            justify="center"
            data-testid="scene-no-preview"
            style={{
              ...frame,
              padding: 12,
              textAlign: "center",
              boxSizing: "border-box",
              background: hasPicture ? "#FFF7E6" : "#FFF1F0",
              border: `1px solid ${hasPicture ? "#FFD591" : "#FFA39E"}`,
            }}
          >
            <Typography.Text type="danger">{reason ?? scene.image_error ?? "Chưa có ảnh"}</Typography.Text>
          </Flex>
        )}
        {/* Quick actions over the picture, shown on hover (always on touch screens); none in view mode. */}
        {hasPicture && !editor.readOnly && (
          <Flex vertical gap={6} className="scene-media__overlay" data-testid="scene-media-actions">
            <Button
              size="small"
              icon={<ScissorOutlined />}
              disabled={off}
              onClick={async () => {
                // The trim starts from the saved seconds and start: the one being typed is saved first.
                await editor.flush();
                setFraming(true);
              }}
            >
              {scene.video ? "Cắt video" : "Chỉnh khung"}
            </Button>
            {canPlace && (
              <Button
                size="small"
                icon={<DragOutlined />}
                disabled={off}
                onClick={async () => {
                  // The box is drawn from the saved text: the text being typed is saved first.
                  await editor.flush();
                  setPlacing(true);
                }}
              >
                {scene.text_position ? "Vị trí chữ (riêng)" : "Vị trí chữ"}
              </Button>
            )}
            <Flex gap={6}>
              <Button
                size="small"
                icon={<SwapOutlined />}
                disabled={off}
                style={{ flex: 1 }}
                onClick={() => input.current?.click()}
              >
                Thay
              </Button>
              {scene.video && (
                <Popconfirm
                  title="Xoá video của cảnh này?"
                  okText="Xoá"
                  cancelText="Huỷ"
                  okButtonProps={{ danger: true }}
                  disabled={off}
                  onConfirm={() => run("remove", () => api<VideoDetail>(`/scenes/${scene.id}/video`, "DELETE"))}
                >
                  <Button
                    size="small"
                    danger
                    aria-label="Xoá video"
                    icon={<DeleteOutlined />}
                    loading={busy === "remove"}
                    disabled={off}
                  />
                </Popconfirm>
              )}
            </Flex>
          </Flex>
        )}
      </div>
      {scene.video && (
        // The clip as uploaded, without sound: the render never uses its sound either.
        <video
          src={scene.video.url}
          muted
          loop
          playsInline
          controls
          preload="metadata"
          aria-label={`Video của ${which}`}
          data-testid="scene-video"
          style={{ width: "100%", maxHeight: 200, borderRadius: 6, background: "#000" }}
        />
      )}
      <input
        ref={input}
        type="file"
        accept={[...IMAGE_TYPES, ...VIDEO_TYPES].join(",")}
        hidden
        aria-label={`Tải ảnh/video lên cho ${which}`}
        onChange={(event) => chosen(event.target.files?.[0])}
      />
      {!editor.readOnly && (
        <>
          <Flex
            vertical
            align="center"
            justify="center"
            role="button"
            tabIndex={off ? -1 : 0}
            aria-disabled={off}
            data-testid="scene-dropzone"
            onClick={() => !off && input.current?.click()}
            onKeyDown={(event) => {
              if (!off && (event.key === "Enter" || event.key === " ")) {
                event.preventDefault();
                input.current?.click();
              }
            }}
            onDragOver={(event) => {
              event.preventDefault();
              setDragging(!off);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(event) => {
              event.preventDefault();
              setDragging(false);
              if (!off) {
                chosen(event.dataTransfer.files[0]);
              }
            }}
            style={{
              padding: "10px 8px",
              textAlign: "center",
              borderRadius: 6,
              border: `1px dashed ${dragging ? "#1677ff" : "#d9d9d9"}`,
              background: dragging ? "#e6f4ff" : "#fafafa",
              cursor: off ? "not-allowed" : "pointer",
              opacity: off && !uploading ? 0.6 : 1,
            }}
          >
            {uploading ? <Spin size="small" /> : <InboxOutlined style={{ fontSize: 20, color: "#1677ff" }} />}
            <Typography.Text style={{ fontSize: 12 }}>
              {uploading ? "Đang tải lên…" : "Kéo thả hoặc bấm để tải ảnh/video lên"}
            </Typography.Text>
          </Flex>
          <Switching
            show={scene.video !== null}
            title="Ảnh hoặc video chọn được sẽ thay video của cảnh này?"
            disabled={off}
            onConfirm={async () => {
              // The grid starts from the keywords on screen, so their save goes first.
              await editor.flush();
              setPicking(true);
            }}
          >
            <Button icon={<PictureOutlined />} disabled={off} block>
              Chọn từ kho ảnh/video
            </Button>
          </Switching>
          <Space.Compact block>
            <Switching
              show={scene.video !== null}
              title="Ảnh tìm được sẽ thay video của cảnh này?"
              disabled={off}
              onConfirm={() =>
                run("find", async () => {
                  // The api searches the saved keywords: the one being typed is saved first.
                  await editor.flush();
                  return api<VideoDetail>(`/scenes/${scene.id}/find-image?source=${findSource.id}`, "POST");
                })
              }
            >
              {/* The api walks on from the photo in use, so a scene that has one gets a different one. */}
              <Button icon={<SearchOutlined />} loading={busy === "find"} disabled={off} style={{ flex: 1 }}>
                {scene.has_image ? "Tìm ảnh khác" : "Tìm ảnh"} ({findSource.label})
              </Button>
            </Switching>
            <Dropdown
              trigger={["click"]}
              disabled={off}
              onOpenChange={(open) => open && void loadSources()}
              menu={{
                selectable: true,
                selectedKeys: [findSource.id],
                items: (sources ?? [findSource]).map((item) => ({ key: item.id, label: item.label })),
                onClick: ({ key }) => setFindSource(sources?.find((item) => item.id === key) ?? findSource),
              }}
            >
              <Button aria-label="Đổi nguồn ảnh" icon={<DownOutlined />} disabled={off} />
            </Dropdown>
          </Space.Compact>
        </>
      )}
      {error && (
        <Typography.Text type="danger" data-testid="image-error">
          {error.message}
        </Typography.Text>
      )}
      {error?.kind === "find" && scene.keywords.length === 0 && scene.keywords_en.length === 0 && (
        <Typography.Text type="secondary" data-testid="keywords-hint">
          Nhập từ khóa ở ô “Từ khóa tìm ảnh” của cảnh này rồi bấm lại.
        </Typography.Text>
      )}
      {placing && <TextPositionModal scene={scene} onClose={() => setPlacing(false)} onSaved={editor.onSaved} />}
      {framing && <MediaEditor scene={scene} voiceEnabled={voiceEnabled} onClose={() => setFraming(false)} />}
      {picking && (
        <StockPicker
          sceneId={scene.id}
          keywords={scene.keywords}
          keywordsEn={scene.keywords_en}
          onClose={() => setPicking(false)}
        />
      )}
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
