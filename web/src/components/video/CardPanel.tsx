"use client";

import { DeleteOutlined, FolderOpenOutlined, UploadOutlined } from "@ant-design/icons";
import { Alert, App, Button, Collapse, Flex, Input, InputNumber, Slider, Switch, Typography } from "antd";
import { useRef, useState } from "react";
import { api, errorMessage, upload as sendFile, type SceneData, type SceneLayer, type VideoDetail } from "@/lib/api";
import { useEditor } from "./AutoSaveField";
import MediaLibraryPicker from "./MediaLibraryPicker";
import { FRAME_HEIGHT, isCard } from "./preview/layers";

/** A card's width in percent of the frame's width (layers.CARD_WIDTH_MIN, CARD_WIDTH_MAX). */
const WIDTH_MIN = 50;
const WIDTH_MAX = 100;
const MAX_PARTS = 12;

type Part = { until: number; text: string };

/** The parts as saved, or one part for the whole card (its words the scene's narration) when it shows whole. */
function savedParts(scene: SceneData, card: SceneLayer): Part[] {
  const steps = card.reveal ?? [];
  if (steps.length > 0) return steps.map((step) => ({ until: step.until, text: step.text }));
  return [{ until: 1, text: scene.voice_text }];
}

/**
 * "Thẻ" (2026-11-15, the comment-reading pages): a screenshot of a post laid whole over the scene's picture, hung from
 * its top edge (layers.CARD). Added from the computer, the library or a link; its width and top edge changed here (or
 * dragged on the studio's phone); "Hiện dần" splits it into parts, each coming in as the narration reaches its words:
 * a click on the card adds a cut there, and each part gets the words read while it comes in.
 */
export default function CardPanel({ scene }: { scene: SceneData }) {
  const editor = useEditor();
  const { modal } = App.useApp();
  const frozen = editor.locked || editor.readOnly;
  const card = scene.layers.find(isCard);
  const file = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [link, setLink] = useState("");
  const [fromLibrary, setFromLibrary] = useState(false);
  // The parts being edited; null while they are as saved.
  const [draft, setDraft] = useState<Part[] | null>(null);
  const off = frozen || busy !== null;
  const parts = draft ?? (card ? savedParts(scene, card) : []);
  const revealing = (card?.reveal?.length ?? 0) > 0;

  async function run(kind: string, action: () => Promise<VideoDetail>): Promise<boolean> {
    setBusy(kind);
    setError(null);
    try {
      editor.onSaved(await action());
      return true;
    } catch (err) {
      setError(errorMessage(err));
      return false;
    } finally {
      setBusy(null);
    }
  }

  function upload(picked: File) {
    void run("upload", () => sendFile<VideoDetail>("/layers/card/upload", picked, { scene_id: String(scene.id) })).then(
      (done) => {
        if (done) setDraft(null);
      },
    );
  }

  function useLink() {
    const url = link.trim();
    if (!url) return;
    void run("link", () => api<VideoDetail>("/layers/card", "POST", { scene_id: scene.id, url })).then((done) => {
      if (done) {
        setLink("");
        setDraft(null);
      }
    });
  }

  const patch = (body: Record<string, unknown>) =>
    card ? run("patch", () => api<VideoDetail>(`/layers/${card.id}`, "PATCH", body)) : Promise.resolve(false);

  function remove() {
    if (!card) return;
    modal.confirm({
      title: "Xoá thẻ?",
      content: "Thẻ bị xoá hẳn cùng ảnh của nó và phần hiện dần, không hoàn tác được.",
      okText: "Xoá",
      okButtonProps: { danger: true },
      cancelText: "Huỷ",
      onOk: () => run("delete", () => api<VideoDetail>(`/layers/${card.id}`, "DELETE")).then(() => setDraft(null)),
    });
  }

  /** A click on the card: a cut there, splitting the part it falls in. */
  function cutAt(fraction: number) {
    if (off || parts.length >= MAX_PARTS) return;
    const at = Math.round(fraction * 1000) / 1000;
    if (at <= 0.02 || at >= 0.98 || parts.some((part) => Math.abs(part.until - at) < 0.02)) return;
    const index = parts.findIndex((part) => part.until > at);
    const next = [...parts];
    next.splice(index, 0, { until: at, text: "" });
    setDraft(next);
  }

  function removeCut(index: number) {
    // The part merges with the one below it, its words first.
    const next = [...parts];
    const [gone] = next.splice(index, 1);
    next[index] = { ...next[index], text: [gone.text, next[index].text].filter(Boolean).join(" ") };
    setDraft(next);
  }

  const saveParts = () =>
    run("reveal", () =>
      api<VideoDetail>("/layers/card/reveal", "PUT", {
        scene_id: scene.id,
        parts: parts.map((part, index) =>
          index === parts.length - 1 ? { text: part.text } : { until: part.until, text: part.text },
        ),
      }),
    ).then((done) => {
      if (done) setDraft(null);
    });

  const turnOffReveal = () =>
    run("reveal", () => api<VideoDetail>("/layers/card/reveal", "PUT", { scene_id: scene.id, parts: [] })).then(
      (done) => {
        if (done) setDraft(null);
      },
    );

  const pickers = (
    <Flex wrap gap={8} align="center">
      <input
        ref={file}
        type="file"
        accept="image/*"
        hidden
        data-testid="card-file"
        onChange={(event) => {
          const picked = event.target.files?.[0];
          event.target.value = "";
          if (picked) upload(picked);
        }}
      />
      <Button
        size="small"
        icon={<UploadOutlined />}
        loading={busy === "upload"}
        disabled={off}
        onClick={() => file.current?.click()}
      >
        Tải ảnh thẻ
      </Button>
      <Button size="small" icon={<FolderOpenOutlined />} disabled={off} onClick={() => setFromLibrary(true)}>
        Từ Kho
      </Button>
      <Input.Search
        size="small"
        style={{ flex: "1 1 220px", minWidth: 0 }}
        placeholder="Dán link ảnh thẻ"
        aria-label="Link ảnh thẻ"
        enterButton="Dùng"
        value={link}
        disabled={off}
        loading={busy === "link"}
        onChange={(event) => setLink(event.target.value)}
        onSearch={useLink}
      />
    </Flex>
  );

  return (
    <Flex vertical gap={8} data-testid="card-panel">
      {!card ? (
        <>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            Ảnh chụp một bài đăng hay bình luận (ví dụ thẻ Threads trắng) đặt nguyên vẹn trên nền của cảnh, giữa theo
            chiều ngang, dưới chữ của cảnh.
          </Typography.Text>
          {pickers}
        </>
      ) : (
        <>
          <Flex gap={12} wrap align="flex-start">
            <div
              data-testid="card-picture"
              role="button"
              tabIndex={-1}
              aria-label="Bấm vào thẻ để thêm chỗ cắt"
              style={{ position: "relative", width: 160, cursor: off ? "default" : "crosshair", flex: "none" }}
              onClick={(event) => {
                const rect = event.currentTarget.getBoundingClientRect();
                cutAt((event.clientY - rect.top) / rect.height);
              }}
            >
              {/* eslint-disable-next-line @next/next/no-img-element -- drawn by the api with the render core's own code */}
              <img src={card.image_url} alt="Thẻ" style={{ width: "100%", display: "block", borderRadius: 4 }} />
              {parts.slice(0, -1).map((part, index) => (
                <div
                  key={part.until}
                  data-testid="card-cut"
                  style={{
                    position: "absolute",
                    left: 0,
                    right: 0,
                    top: `${part.until * 100}%`,
                    borderTop: "2px dashed #ff4fd8",
                  }}
                >
                  <span
                    style={{
                      position: "absolute",
                      right: 2,
                      top: 2,
                      fontSize: 11,
                      background: "#ff4fd8",
                      color: "#fff",
                      padding: "0 4px",
                      borderRadius: 3,
                    }}
                  >
                    {index + 1}
                  </span>
                </div>
              ))}
            </div>
            <Flex vertical gap={6} style={{ flex: "1 1 200px", minWidth: 0 }}>
              <Typography.Text style={{ fontSize: 12 }}>Cỡ thẻ (% bề rộng khung)</Typography.Text>
              <Slider
                aria-label="Cỡ thẻ"
                min={WIDTH_MIN}
                max={WIDTH_MAX}
                defaultValue={card.height}
                key={`${card.id}-${card.height}`}
                disabled={off}
                onChangeComplete={(value) => void patch({ height: value })}
              />
              <Flex align="center" gap={8}>
                <Typography.Text style={{ fontSize: 12 }}>Mép trên</Typography.Text>
                <InputNumber
                  aria-label="Mép trên của thẻ"
                  size="small"
                  min={0}
                  max={FRAME_HEIGHT - 1}
                  step={10}
                  defaultValue={card.y}
                  key={`${card.id}-${card.y}`}
                  disabled={off}
                  suffix="px"
                  onBlur={(event) => {
                    const value = Number(event.target.value.replace(/[^\d]/g, ""));
                    if (Number.isFinite(value) && value !== card.y) void patch({ y: value });
                  }}
                />
              </Flex>
              <Button size="small" danger icon={<DeleteOutlined />} disabled={off} onClick={remove}>
                Xoá thẻ
              </Button>
            </Flex>
          </Flex>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            Đổi ảnh thẻ (giữ cỡ và chỗ, bỏ phần hiện dần):
          </Typography.Text>
          {pickers}
          <Flex align="center" gap={8}>
            <Switch
              size="small"
              aria-label="Hiện dần"
              checked={revealing || draft !== null}
              disabled={off}
              onChange={(on) => {
                if (on) setDraft(savedParts(scene, card));
                else if (revealing) void turnOffReveal();
                else setDraft(null);
              }}
            />
            <Typography.Text>Hiện dần</Typography.Text>
            {revealing && draft === null && (
              <Typography.Text type="secondary" style={{ fontSize: 12 }} data-testid="card-reveal-summary">
                {card.reveal?.length} phần
              </Typography.Text>
            )}
          </Flex>
          {(revealing || draft !== null) && (
            <Flex vertical gap={6} data-testid="card-reveal">
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                Bấm vào thẻ để thêm chỗ cắt. Mỗi phần hiện khi giọng đọc tới lời của phần đó; lời đọc của cảnh được thay
                bằng lời các phần nối lại.
              </Typography.Text>
              {parts.map((part, index) => (
                <Flex key={`${index}-${part.until}`} gap={6} align="flex-start">
                  <Typography.Text style={{ fontSize: 12, width: 52, flex: "none", paddingTop: 4 }}>
                    Phần {index + 1}
                  </Typography.Text>
                  <Input.TextArea
                    aria-label={`Lời đọc phần ${index + 1}`}
                    autoSize={{ minRows: 1, maxRows: 4 }}
                    value={part.text}
                    disabled={off}
                    onChange={(event) =>
                      setDraft(parts.map((item, at) => (at === index ? { ...item, text: event.target.value } : item)))
                    }
                  />
                  {index < parts.length - 1 && (
                    <Button
                      size="small"
                      type="text"
                      aria-label={`Bỏ chỗ cắt ${index + 1}`}
                      icon={<DeleteOutlined />}
                      disabled={off}
                      onClick={() => removeCut(index)}
                    />
                  )}
                </Flex>
              ))}
              <Flex gap={8}>
                <Button
                  size="small"
                  type="primary"
                  loading={busy === "reveal"}
                  disabled={off || parts.length < 2 || draft === null}
                  onClick={() => void saveParts()}
                >
                  Lưu hiện dần
                </Button>
                {draft !== null && (
                  <Button size="small" disabled={off} onClick={() => setDraft(null)}>
                    Huỷ
                  </Button>
                )}
              </Flex>
            </Flex>
          )}
        </>
      )}
      {error && <Alert type="error" showIcon message={error} />}
      {fromLibrary && (
        <MediaLibraryPicker
          sceneId={scene.id}
          videoId={scene.video_id}
          hasPicture={Boolean(card)}
          usedFor="thẻ"
          onUse={(mediaId) => api<VideoDetail>("/layers/card", "POST", { scene_id: scene.id, media_id: mediaId })}
          onClose={() => {
            setFromLibrary(false);
            setDraft(null);
          }}
        />
      )}
    </Flex>
  );
}

/** "Thẻ" folded under a content scene's fields, open once the scene has a card. */
export function CardFold({ scene }: { scene: SceneData }) {
  const card = scene.layers.find(isCard);
  return (
    <Collapse
      ghost
      size="small"
      defaultActiveKey={card ? ["card"] : []}
      items={[
        {
          key: "card",
          label: (
            <Typography.Text type="secondary" style={{ fontSize: 13 }}>
              {card
                ? `Thẻ${card.reveal?.length ? ` · hiện dần ${card.reveal.length} phần` : ""}`
                : "Thẻ (ảnh chụp bài đăng)"}
            </Typography.Text>
          ),
          styles: { header: { padding: "2px 0" }, body: { padding: "4px 0 0" } },
          children: <CardPanel scene={scene} />,
        },
      ]}
    />
  );
}
