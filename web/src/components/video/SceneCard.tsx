"use client";

import {
  ArrowDownOutlined,
  ArrowUpOutlined,
  DeleteOutlined,
  DownOutlined,
  DragOutlined,
  EyeInvisibleOutlined,
  EyeOutlined,
  GoogleOutlined,
  HighlightOutlined,
  FolderOpenOutlined,
  HistoryOutlined,
  InboxOutlined,
  PictureOutlined,
  PlayCircleOutlined,
  RightOutlined,
  RobotOutlined,
  ScissorOutlined,
  SearchOutlined,
  SnippetsOutlined,
  TikTokOutlined,
  UndoOutlined,
} from "@ant-design/icons";
import {
  App,
  Alert,
  Button,
  Card,
  Col,
  Dropdown,
  Flex,
  Input,
  Modal,
  Popconfirm,
  Row,
  Space,
  Spin,
  Tooltip,
  Typography,
} from "antd";
import { cloneElement, useEffect, useRef, useState } from "react";
import { api, errorMessage, upload, type SceneData, type StockSource, type VideoDetail } from "@/lib/api";
import { setGoogleTarget, useSentImage } from "@/lib/googleExtension";
import {
  fileFromDataUrl,
  googleImagesUrl,
  linkFromTransfer,
  looksLikeClipLink,
  looksLikeLink,
  tiktokSearchUrl,
  unwrapLink,
} from "@/lib/mediaLinks";
import AutoSaveField, { useEditor } from "./AutoSaveField";
import GroupMediaPicker from "./GroupMediaPicker";
import MediaLibraryPicker from "./MediaLibraryPicker";
import ClipBlurModal from "./ClipBlurModal";
import ImageEditModal from "./ImageEditModal";
import ImageProviderMenu from "./ImageProviderMenu";
import MediaEditor from "./MediaEditor";
import HalfPhotoPanel from "./HalfPhotoPanel";
import { isHalf } from "./preview/layers";
import { photoLayer } from "./videoModes";
import SceneViewer from "./SceneViewer";
import StockPicker, { DEFAULT_SOURCE } from "./StockPicker";
import TextPositionModal from "./TextPositionModal";
import VoiceText from "./VoiceText";
import { COLORS } from "@/app/theme";
import StatusText from "@/components/StatusText";

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

/** At a speed other than 1×, what the start field counts from; a clip at 1× needs no explaining. */
function clipSpeedHelp(speed: number): string | undefined {
  const shown = speed.toLocaleString("vi-VN");
  return speed === 1 ? undefined : `Clip chạy ${shown}×: mỗi giây của cảnh lấy ${shown} giây clip tính từ đây.`;
}

function parseKeywords(text: string): string[] {
  return text
    .split(",")
    .map((keyword) => keyword.trim())
    .filter(Boolean);
}

type ScenePatch = Partial<Pick<SceneData, "text" | "seconds" | "keywords" | "image_prompt" | "voice_text">> & {
  video_start?: number;
};

const patchScene = (scene: SceneData, body: ScenePatch) => api<VideoDetail>(`/scenes/${scene.id}`, "PATCH", body);

/*
 * The scene's fields, each saving itself, shared by the scene card on the video page and the studio's "Chỉnh cảnh N"
 * panel, so a field works the same wherever it is edited.
 */

/** "Chữ trên màn hình". */
export function SceneTextField({ scene }: { scene: SceneData }) {
  return (
    <AutoSaveField
      label="Chữ trên màn hình"
      value={scene.text}
      multiline
      save={(text) => patchScene(scene, { text })}
      help={TEXT_HELP}
      words={{ max: scene.is_title ? MAX_TITLE_WORDS : MAX_SCENE_WORDS }}
    />
  );
}

/** "Lời đọc", with its narration player, when the video has narration. */
export function SceneVoiceField({ scene, voiceEnabled }: { scene: SceneData; voiceEnabled: boolean }) {
  return voiceEnabled ? <VoiceText scene={scene} save={(voice_text) => patchScene(scene, { voice_text })} /> : null;
}

/** "Từ khóa tìm ảnh". */
export function SceneKeywordsField({ scene }: { scene: SceneData }) {
  return (
    <AutoSaveField
      label="Từ khóa tìm ảnh"
      value={scene.keywords.join(", ")}
      placeholder="cụ thể nhất trước, cách nhau bằng dấu phẩy"
      save={(text) => patchScene(scene, { keywords: parseKeywords(text) })}
    />
  );
}

/** "Prompt ảnh AI". */
export function ScenePromptField({ scene }: { scene: SceneData }) {
  return (
    <AutoSaveField
      label="Prompt ảnh AI"
      help={
        "Tả thứ có trong ảnh (món, cách bày, góc chụp), nên viết tiếng Anh. Phong cách chung (ánh sáng, khung " +
        "dọc, không chữ) được thêm tự động, sửa ở Cài đặt › Nguồn tư liệu." +
        (scene.is_title ? " Để trống thì dùng dòng chữ đầu của cảnh tiêu đề." : "")
      }
      value={scene.image_prompt}
      multiline
      save={(text) => patchScene(scene, { image_prompt: text })}
    />
  );
}

/** What blocks the scene's render, then what only warns. */
export function SceneIssues({ scene }: { scene: SceneData }) {
  return (
    <>
      {scene.blocking.map((reason) => (
        <Alert key={reason} type="error" showIcon title={reason} data-testid="scene-blocking" />
      ))}
      {scene.warnings.map((warning) => (
        <Alert key={warning} type="warning" showIcon title={warning} data-testid="scene-warning" />
      ))}
    </>
  );
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
  generating = false,
  editing = false,
  backdrop = false,
  backdropScene = null,
}: {
  scene: SceneData;
  label: string;
  voiceEnabled: boolean;
  /** "Video xuyên suốt": the title scene's picture is the backdrop of every scene; a content scene's own photo
   * shows only as its "Ảnh món". */
  backdrop?: boolean;
  /** The title scene, whose picture runs under a content scene of a "Video xuyên suốt". */
  backdropScene?: SceneData | null;
  /** An image job is making this scene's photo ("Tạo ảnh AI" on this card). */
  generating?: boolean;
  /** An image_edit job ("Sửa ảnh" on this card) is changing this scene's photo. */
  editing?: boolean;
  expanded: boolean;
  onToggle: () => void;
  /** "Xem từ cảnh này": the browser preview, starting at this scene. */
  onPreview?: () => void;
  onMove?: (step: -1 | 1) => void;
  onDelete?: () => void;
}) {
  const editor = useEditor();
  const frozen = editor.locked || editor.readOnly;
  const patch = (body: ScenePatch) => patchScene(scene, body);
  // Over a backdrop, a content scene's photo (and how to find it) matters only for a photo layer showing it: an
  // older video's "Ảnh món", or a half-frame photo without a photo of its own.
  const ownPicture =
    !backdrop ||
    scene.is_title ||
    Boolean(photoLayer(scene.layers)) ||
    scene.layers.some((layer) => isHalf(layer) && layer.own_image === false);

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
          <Flex vertical gap={8} style={{ maxWidth: 220, margin: "0 auto" }}>
            {backdrop && scene.is_title && (
              <Typography.Text type="secondary" style={{ fontSize: 12 }} data-testid="backdrop-note">
                Ảnh hoặc video của cảnh này là nền chung, chạy suốt cả video.
              </Typography.Text>
            )}
            {!scene.is_title && <HalfPhotoPanel scene={scene} backdrop={backdrop ? backdropScene : null} />}
            {ownPicture && (
              <ScenePicture scene={scene} voiceEnabled={voiceEnabled} generating={generating} editing={editing} />
            )}
          </Flex>
        </Col>
        <Col xs={24} sm={15} md={16}>
          <Flex vertical gap={4}>
            <SceneTextField scene={scene} />
            <SceneVoiceField scene={scene} voiceEnabled={voiceEnabled} />
            {/* Seconds (and a clip's start) beside the keywords: short fields, one row. */}
            <Flex wrap gap={16}>
              <AutoSaveField
                label="Số giây"
                value={String(scene.seconds)}
                inputMode="decimal"
                width={110}
                save={async (text) => patch({ seconds: parseSeconds(text) })}
              />
              {scene.video && ownPicture && (
                <AutoSaveField
                  label="Bắt đầu từ giây"
                  value={String(scene.video.start)}
                  help={clipSpeedHelp(scene.video.speed)}
                  inputMode="decimal"
                  width={130}
                  save={async (text) => patch({ video_start: parseSeconds(text) })}
                />
              )}
              {ownPicture && (
                <div style={{ flex: "1 1 220px", minWidth: 0 }}>
                  <SceneKeywordsField scene={scene} />
                </div>
              )}
            </Flex>
            {ownPicture && <ScenePromptField scene={scene} />}
            <SceneIssues scene={scene} />
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
      <StatusText tone="danger">{scene.blocking.length} lỗi</StatusText>
    ) : scene.warnings.length > 0 ? (
      <StatusText tone="warning">{scene.warnings.length} cảnh báo</StatusText>
    ) : (
      <StatusText tone="success">Sẵn sàng</StatusText>
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

type Busy = "upload" | "video" | "remove" | "find" | "link" | "ai" | "keep" | "restore";

const PEXELS: StockSource = { id: DEFAULT_SOURCE, label: "Pexels", available: true };

/** The sources "Tìm ảnh" offers, asked once for every scene of the page and again after half a minute. */
let offeredSources: { at: number; list: Promise<StockSource[]> } | null = null;

function stockSources(): Promise<StockSource[]> {
  if (offeredSources === null || Date.now() - offeredSources.at > 30_000) {
    offeredSources = {
      at: Date.now(),
      list: api<StockSource[]>("/stock/sources").then(
        (all) => {
          const offered = all.filter((item) => item.available);
          return offered.length > 0 ? offered : [PEXELS];
        },
        () => [PEXELS],
      ),
    };
  }
  return offeredSources.list;
}

/**
 * The scene's photo or clip and every way to change it. `compact` (the studio, where the phone already shows the
 * picture and trims the clip on the timeline) leaves out the large picture and its overlay, keeping "Chỉnh khung"
 * for a photo and "Xoá video" for a clip.
 */
export function ScenePicture({
  scene,
  voiceEnabled,
  generating,
  editing = false,
  compact = false,
}: {
  scene: SceneData;
  voiceEnabled: boolean;
  generating: boolean;
  editing?: boolean;
  compact?: boolean;
}) {
  const { message, modal } = App.useApp();
  const editor = useEditor();
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState<Busy | null>(null);
  const [error, setError] = useState<{ kind: Busy; message: string } | null>(null);
  const [picking, setPicking] = useState(false);
  // "Đã dùng trong nhóm" is open.
  const [reusing, setReusing] = useState(false);
  const [fromLibrary, setFromLibrary] = useState(false);
  const [placing, setPlacing] = useState(false);
  const [framing, setFraming] = useState(false);
  // "Sửa ảnh" is open.
  const [retouching, setRetouching] = useState(false);
  // "Làm mờ vùng" (a clip) is open.
  const [blurring, setBlurring] = useState(false);
  const [viewing, setViewing] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [pasting, setPasting] = useState(false);
  const [pastedLink, setPastedLink] = useState("");
  // Where "Tìm ảnh" searches: Pexels (or the first source offered without it) until the member picks another
  // source from the arrow menu.
  const [findSource, setFindSource] = useState<StockSource>(PEXELS);
  const [sources, setSources] = useState<StockSource[] | null>(null);
  const picked = useRef(false);

  useEffect(() => {
    let open = true;
    void stockSources().then((offered) => {
      if (!open) {
        return;
      }
      setSources(offered);
      if (!picked.current) {
        setFindSource(offered.find((item) => item.id === DEFAULT_SOURCE) ?? offered[0]);
      }
    });
    return () => {
      open = false;
    };
  }, []);

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

  /**
   * A link pasted or dragged from another tab: a data: photo is uploaded, any other link (a photo, a video file, a
   * TikTok video) the api fetches.
   */
  async function fromLink(text: string) {
    const link = unwrapLink(text.trim());
    if (/^data:image\//i.test(link)) {
      chosen(await fileFromDataUrl(link));
      return;
    }
    const send = () =>
      run("link", async () => {
        // A photo from a stock site (Shutterstock, Getty…) is kept, with a note that it is a licensed preview.
        const video = await api<VideoDetail & { notice?: string }>(`/scenes/${scene.id}/media-from-url`, "POST", {
          url: link,
        });
        if (video.notice) {
          void message.warning(video.notice, 10);
        }
        return video;
      });
    const clip = looksLikeClipLink(link);
    if (clip ? !scene.has_image : scene.video === null) {
      void send();
      return;
    }
    modal.confirm({
      title: clip ? "Video sẽ thay ảnh của cảnh này?" : "Ảnh sẽ thay video của cảnh này?",
      okText: "Đổi",
      cancelText: "Huỷ",
      onOk: () => void send(),
    });
  }

  /** What was pasted: a copied photo, or a photo's link. False when it was neither. */
  function fromPaste(data: DataTransfer): boolean {
    const file = Array.from(data.files).find((item) => item.type.startsWith("image/"));
    if (file) {
      chosen(file);
      return true;
    }
    const text = data.getData("text/plain").trim();
    if (looksLikeLink(text)) {
      void fromLink(text);
      return true;
    }
    return false;
  }

  /** "Tìm trên Google" / "Tìm trên TikTok": the keyword being typed is saved first, then the site opens in a tab. */
  async function search(url: (keyword: string) => string, keyword: string) {
    await editor.flush();
    if (url === googleImagesUrl) {
      // With the Chrome extension, "Gửi ảnh vào Reels Studio" on an image's menu now sends to this scene.
      setGoogleTarget(scene.id, `${scene.is_title ? "Cảnh tiêu đề" : "Cảnh"} “${keyword}”`);
    }
    window.open(url(keyword), "_blank", "noopener");
  }

  /** "Dán ảnh/link": the clipboard read directly when the browser allows it, otherwise a box to paste into. */
  async function pasteFromClipboard() {
    try {
      for (const item of await navigator.clipboard.read()) {
        const type = item.types.find((name) => IMAGE_TYPES.includes(name));
        if (type) {
          const blob = await item.getType(type);
          chosen(new File([blob], `anh-dan.${type.split("/")[1].replace("jpeg", "jpg")}`, { type }));
          return;
        }
        if (item.types.includes("text/plain")) {
          const text = (await (await item.getType("text/plain")).text()).trim();
          if (looksLikeLink(text)) {
            void fromLink(text);
            return;
          }
        }
      }
    } catch {
      // No clipboard permission, or a browser without clipboard.read: the box below takes the paste.
    }
    setPastedLink("");
    setPasting(true);
  }

  // "Gửi ảnh vào Reels Studio" from Google Ảnh (the Chrome extension) arrives like a pasted link.
  useSentImage(scene.id, (url) => void fromLink(url));

  /** "Tạo ảnh AI" for this scene; `provider` when picked from the arrow, the team's default otherwise. */
  function generate(provider?: "cloudflare" | "gemini") {
    return run("ai", async () => {
      // The job reads the saved prompt: the one being typed is saved first.
      await editor.flush();
      return api<VideoDetail>(`/scenes/${scene.id}/image-ai${provider ? `?provider=${provider}` : ""}`, "POST");
    });
  }

  const frame = { width: "100%", aspectRatio: "9 / 16", borderRadius: 6 } as const;
  const hasPicture = scene.has_image || scene.video !== null;
  const reason = scene.text_problem && hasPicture ? scene.text_problem : null;
  const off = editor.locked || editor.readOnly || busy !== null;
  const which = scene.is_title ? "cảnh tiêu đề" : "cảnh";
  const canPlace = !!scene.preview_url && !reason && !!scene.textbox_url && !!scene.frame_url;
  const uploading = busy === "upload" || busy === "video" || busy === "link";
  // Google is searched in either language; TikTok's Vietnamese videos are found by the Vietnamese keywords.
  const googleKeywords = [...new Set([...scene.keywords, ...scene.keywords_en])];
  const tiktokKeywords = scene.keywords.length ? scene.keywords : scene.keywords_en;
  const replaceQuestion = scene.video
    ? "Ảnh AI sẽ thay video của cảnh này?"
    : scene.image_ai
      ? "Tạo ảnh AI mới thay ảnh hiện tại?"
      : "Ảnh AI sẽ thay ảnh hiện tại của cảnh này?";

  return (
    <Flex
      vertical
      gap={8}
      onPaste={(event) => {
        // A paste into a text field stays text; elsewhere in this scene's picture column it may be a photo.
        const target = event.target as HTMLElement;
        if (off || target.closest("input, textarea, [contenteditable=true]")) {
          return;
        }
        if (fromPaste(event.clipboardData)) {
          event.preventDefault();
        }
      }}
    >
      {compact && !editor.readOnly && hasPicture && (
        <Flex gap={6} wrap>
          {!scene.video && (
            <Button size="small" icon={<ScissorOutlined />} disabled={off} onClick={() => setFraming(true)}>
              Chỉnh khung
            </Button>
          )}
          {!scene.video && (
            <Button size="small" icon={<HighlightOutlined />} disabled={off} onClick={() => setRetouching(true)}>
              Sửa ảnh
            </Button>
          )}
          {scene.video && (
            <Button size="small" icon={<EyeInvisibleOutlined />} disabled={off} onClick={() => setBlurring(true)}>
              Làm mờ vùng
            </Button>
          )}
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
              >
                Xoá video
              </Button>
            </Popconfirm>
          )}
        </Flex>
      )}
      {!compact && (
        <div className="scene-media">
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
          {/* Over the picture on hover (always on touch screens), stacked in its middle: look at the scene large
            ("Xem"), then edit it; only the look in view mode. */}
          {hasPicture && (
            <div className="scene-media__overlay" data-testid="scene-media-actions">
              <Button size="small" icon={<EyeOutlined />} onClick={() => setViewing(true)}>
                Xem
              </Button>
              {!editor.readOnly && (
                <>
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
                  {scene.video && (
                    <Button
                      size="small"
                      icon={<EyeInvisibleOutlined />}
                      disabled={off}
                      onClick={() => setBlurring(true)}
                    >
                      Làm mờ vùng
                    </Button>
                  )}
                  {!scene.video && (
                    <Button
                      size="small"
                      icon={<HighlightOutlined />}
                      disabled={off}
                      onClick={() => setRetouching(true)}
                    >
                      Sửa ảnh
                    </Button>
                  )}
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
                      >
                        Xoá video
                      </Button>
                    </Popconfirm>
                  )}
                </>
              )}
            </div>
          )}
        </div>
      )}
      {scene.motion && (
        // A "Cảnh động" an assistant wrote through the MCP connection; changed there, replaced like any clip here.
        <StatusText tone={scene.motion.pending ? "active" : "done"}>
          {scene.motion.pending ? "Đang dựng cảnh động" : `Cảnh động · ${scene.motion.seconds} giây`}
        </StatusText>
      )}
      {(scene.video?.blur.length ?? 0) > 0 && (
        <StatusText tone="done" data-testid="clip-blurred">
          Làm mờ {scene.video!.blur.length} vùng trên video
        </StatusText>
      )}
      {editing && (
        <StatusText tone="active" data-testid="image-editing">
          Đang sửa ảnh…
        </StatusText>
      )}
      {scene.image_edited && !editing && (
        // "Sửa ảnh" changed this photo; the one from before the first edit is kept on the server.
        <Flex wrap align="center" gap={4} data-testid="image-edited">
          <StatusText tone="done">Ảnh đã sửa</StatusText>
          {!editor.readOnly && (
            <Popconfirm
              title="Bỏ các lần sửa và dùng lại ảnh gốc?"
              okText="Khôi phục"
              cancelText="Huỷ"
              disabled={off}
              onConfirm={() => run("restore", () => api<VideoDetail>(`/scenes/${scene.id}/image-original`, "POST"))}
            >
              <Button size="small" type="link" icon={<UndoOutlined />} loading={busy === "restore"} disabled={off}>
                Khôi phục ảnh gốc
              </Button>
            </Popconfirm>
          )}
        </Flex>
      )}
      {scene.image_auto && (
        // "Tự tìm ảnh" picked this photo from a stock library after the script: often the wrong dish for
        // Vietnamese food, so a member looks before rendering. Never blocks the render.
        <Flex wrap align="center" gap={4} data-testid="image-auto">
          <StatusText tone="warning">Tự chọn, kiểm tra lại</StatusText>
          {!editor.readOnly && (
            <Button
              size="small"
              type="link"
              loading={busy === "keep"}
              disabled={off}
              onClick={() =>
                run("keep", () => api<VideoDetail>(`/scenes/${scene.id}`, "PATCH", { image_checked: true }))
              }
            >
              Giữ ảnh này
            </Button>
          )}
        </Flex>
      )}
      {scene.video && !compact && (
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
          {/* Upload, paste and Google on one row: the picture column is narrow, and these are the quick ones. */}
          <Flex gap={6}>
            <Flex
              align="center"
              gap={8}
              role="button"
              title="Kéo thả, dán hoặc bấm để tải ảnh/video lên"
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
                if (off) {
                  return;
                }
                const file = event.dataTransfer.files[0];
                if (file) {
                  chosen(file);
                  return;
                }
                // A photo dragged from another tab (Google Ảnh, a shop) arrives as its address, not as a file.
                const link = linkFromTransfer(event.dataTransfer);
                if (link) {
                  void fromLink(link);
                } else {
                  message.error("Không nhận ra ảnh vừa thả: hãy kéo chính tấm ảnh, hoặc sao chép ảnh rồi dán");
                }
              }}
              style={{
                flex: 1,
                minWidth: 0,
                height: 36,
                padding: "0 14px",
                borderRadius: 8,
                border: `1px dashed ${dragging ? COLORS.primary : "#C9D0D5"}`,
                background: dragging ? COLORS.primaryBg : COLORS.muted,
                cursor: off ? "not-allowed" : "pointer",
                opacity: off && !uploading ? 0.6 : 1,
              }}
            >
              {uploading ? <Spin size="small" /> : <InboxOutlined style={{ fontSize: 14, color: COLORS.primary }} />}
              <Typography.Text ellipsis style={{ fontSize: 13 }}>
                {uploading ? "Đang tải lên…" : "Tải lên"}
              </Typography.Text>
            </Flex>
            <Tooltip title="Dán ảnh, link ảnh, link video hoặc link TikTok đã sao chép">
              <Button
                aria-label="Dán ảnh/link"
                icon={<SnippetsOutlined />}
                disabled={off}
                onClick={() => void pasteFromClipboard()}
              />
            </Tooltip>
            <SiteSearch
              label="Tìm trên Google"
              icon={<GoogleOutlined />}
              tip="Tìm trên Google: mở Google Ảnh (ảnh dọc) với từ khóa bạn chọn; sao chép ảnh ưng ý rồi quay lại dán vào đây (có tiện ích Chrome của nhóm thì chuột phải vào ảnh, chọn “Gửi ảnh vào Reels Studio”)"
              keywords={googleKeywords}
              disabled={off}
              onSearch={(keyword) => void search(googleImagesUrl, keyword)}
            />
            <SiteSearch
              label="Tìm trên TikTok"
              icon={<TikTokOutlined />}
              tip="Tìm trên TikTok: mở video TikTok với từ khóa bạn chọn; sao chép link video ưng ý rồi quay lại dán vào đây"
              keywords={tiktokKeywords}
              disabled={off}
              onSearch={(keyword) => void search(tiktokSearchUrl, keyword)}
            />
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
            <Button className="scene-action" icon={<PictureOutlined />} disabled={off} block>
              Chọn từ kho ảnh/video
            </Button>
          </Switching>
          <Button
            className="scene-action"
            icon={<HistoryOutlined />}
            disabled={off}
            block
            onClick={async () => {
              // The list is ranked by the keywords on screen, so their save goes first.
              await editor.flush();
              setReusing(true);
            }}
          >
            Đã dùng trong nhóm
          </Button>
          <Button
            className="scene-action"
            icon={<FolderOpenOutlined />}
            disabled={off}
            block
            onClick={() => setFromLibrary(true)}
          >
            Kho tư liệu
          </Button>
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
              <Button
                className="scene-action"
                icon={<SearchOutlined />}
                loading={busy === "find"}
                disabled={off}
                style={{ flex: 1 }}
              >
                Tìm ảnh ({findSource.label})
              </Button>
            </Switching>
            <Dropdown
              trigger={["click"]}
              disabled={off}
              menu={{
                selectable: true,
                selectedKeys: [findSource.id],
                items: (sources ?? [findSource]).map((item) => ({ key: item.id, label: item.label })),
                onClick: ({ key }) => {
                  picked.current = true;
                  setFindSource(sources?.find((item) => item.id === key) ?? findSource);
                },
              }}
            >
              <Button aria-label="Đổi nguồn ảnh" icon={<DownOutlined />} disabled={off} />
            </Dropdown>
          </Space.Compact>
          {/* A job, like the bar's "Tạo ảnh AI cho cảnh thiếu", but for this scene only and replacing what it has. */}
          <Space.Compact block>
            <Switching show={hasPicture} title={replaceQuestion} disabled={off} onConfirm={() => void generate()}>
              <Button
                className="scene-action"
                icon={<RobotOutlined />}
                loading={generating || busy === "ai"}
                disabled={off}
                style={{ flex: 1 }}
              >
                {generating ? "Đang tạo ảnh AI…" : scene.image_ai ? "Tạo lại ảnh AI" : "Tạo ảnh AI"}
              </Button>
            </Switching>
            <ImageProviderMenu
              disabled={off}
              onPick={(provider) => {
                if (!hasPicture) {
                  void generate(provider);
                  return;
                }
                modal.confirm({
                  title: replaceQuestion,
                  okText: "Đổi",
                  cancelText: "Huỷ",
                  onOk: () => void generate(provider),
                });
              }}
            />
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
      {pasting && (
        <Modal
          open
          centered
          title={`Dán ảnh hoặc video cho ${which}`}
          okText="Lấy về"
          cancelText="Huỷ"
          okButtonProps={{ disabled: !looksLikeLink(pastedLink.trim()) }}
          onCancel={() => setPasting(false)}
          onOk={() => {
            setPasting(false);
            void fromLink(pastedLink);
          }}
        >
          <Typography.Paragraph type="secondary">
            Nhấn Cmd/Ctrl+V để dán ảnh đã sao chép (chuột phải vào ảnh, chọn “Sao chép hình ảnh”), hoặc dán link ảnh,
            link video (MP4, MOV, WebM) hay link video TikTok. Video dài hơn 60 giây chỉ lấy 60 giây đầu.
          </Typography.Paragraph>
          <Input
            autoFocus
            aria-label="Link ảnh hoặc video"
            placeholder="https://… (link ảnh, link video hoặc link TikTok)"
            value={pastedLink}
            onChange={(event) => setPastedLink(event.target.value)}
            onPaste={(event) => {
              const file = Array.from(event.clipboardData.files).find((item) => item.type.startsWith("image/"));
              if (file) {
                event.preventDefault();
                setPasting(false);
                chosen(file);
              }
            }}
          />
        </Modal>
      )}
      {viewing && <SceneViewer scene={scene} onClose={() => setViewing(false)} />}
      {placing && <TextPositionModal scene={scene} onClose={() => setPlacing(false)} onSaved={editor.onSaved} />}
      {framing && <MediaEditor scene={scene} voiceEnabled={voiceEnabled} onClose={() => setFraming(false)} />}
      {retouching && <ImageEditModal scene={scene} onClose={() => setRetouching(false)} />}
      {blurring && <ClipBlurModal scene={scene} onClose={() => setBlurring(false)} />}
      {picking && (
        <StockPicker
          sceneId={scene.id}
          keywords={scene.keywords}
          keywordsEn={scene.keywords_en}
          onClose={() => setPicking(false)}
        />
      )}
      {reusing && <GroupMediaPicker sceneId={scene.id} hasPicture={hasPicture} onClose={() => setReusing(false)} />}
      {fromLibrary && (
        <MediaLibraryPicker
          sceneId={scene.id}
          videoId={scene.video_id}
          hasPicture={hasPicture}
          onClose={() => setFromLibrary(false)}
        />
      )}
    </Flex>
  );
}

/**
 * "Tìm trên Google" / "Tìm trên TikTok": with one keyword the site opens on it; with several the member picks which,
 * since the first one is not always the one that finds the right picture.
 */
function SiteSearch({
  label,
  icon,
  tip,
  keywords,
  disabled,
  onSearch,
}: {
  label: string;
  icon: React.ReactNode;
  tip: string;
  keywords: string[];
  disabled: boolean;
  onSearch: (keyword: string) => void;
}) {
  const button = (
    <Button
      aria-label={label}
      icon={icon}
      disabled={disabled}
      onClick={keywords.length > 1 ? undefined : () => onSearch(keywords[0] ?? "")}
    />
  );
  if (keywords.length <= 1) {
    return <Tooltip title={tip}>{button}</Tooltip>;
  }
  return (
    <Tooltip title={tip}>
      <Dropdown
        trigger={["click"]}
        disabled={disabled}
        menu={{
          items: [
            { key: "head", type: "group", label: `${label} với từ khóa:` },
            ...keywords.map((keyword) => ({ key: keyword, label: keyword })),
          ],
          onClick: ({ key }) => onSearch(key),
        }}
      >
        {button}
      </Dropdown>
    </Tooltip>
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
