"use client";

import {
  api,
  compositePreview,
  errorMessage,
  type Article,
  type ArticleImage,
  type CompositeOptions,
  type CompositeResult,
} from "@/lib/api";
import { Alert, App, Flex, Input, Modal, Radio, Select, Slider, Switch, Typography } from "antd";
import { useEffect, useMemo, useState } from "react";

const PRESETS = [
  { value: "cam", label: "Cam" },
  { value: "xanh_la", label: "Xanh lá" },
];

const MODES = [
  { value: "auto", label: "Tự động" },
  { value: "cover", label: "Cắt vừa" },
  { value: "blur", label: "Nền mờ" },
];

const WARNINGS: Record<string, string> = {
  FONT_TOO_SMALL: "Chữ nhỏ, khó đọc: hãy rút gọn tiêu đề.",
  LOW_RES_SOURCE: "Ảnh gốc rộng dưới 800 px nên có thể mờ.",
  UPSCALED: "Ảnh bị phóng to quá 1.5 lần nên có thể mờ.",
};

const MODE_LABEL = { cover: "Cắt vừa", blur: "Nền mờ" };

/**
 * "Ảnh ghép chữ + ảnh": one 4:5 photo, a band of text over the dish photo. It makes a new composite from one of the
 * article's photos, or (`editing`) opens a composite again with the options it was made from. The preview is drawn by
 * the api, by the same code as the saved photo, so what is shown is what is posted. Leaving the lines or the tag empty
 * lets the api take them from the caption and the plan.
 */
export default function ArticleComposite({
  article,
  editing,
  onClose,
  onSaved,
}: {
  article: Article;
  /** The composite being opened again; null makes a new one. */
  editing: ArticleImage | null;
  onClose: () => void;
  onSaved: (article: Article, imageId: number) => void;
}) {
  const { message } = App.useApp();
  const sources = useMemo(() => article.images.filter((image) => image.source !== "composite"), [article.images]);
  const kept = editing?.composite ?? null;
  const [sourceId, setSourceId] = useState<number | null>(sources[0]?.id ?? null);
  const [lines, setLines] = useState<string[]>(() => [0, 1, 2].map((i) => kept?.lines[i] ?? ""));
  const [tag, setTag] = useState(kept?.tag ?? "");
  const [preset, setPreset] = useState<CompositeOptions["preset"]>(kept?.preset ?? "cam");
  const [mode, setMode] = useState<CompositeOptions["mode"]>(kept?.mode ?? "auto");
  const [focusX, setFocusX] = useState(kept?.focus_x ?? 0.5);
  const [focusY, setFocusY] = useState(kept?.focus_y ?? 0.5);
  const [replace, setReplace] = useState(true);
  const [saving, setSaving] = useState(false);
  const [shown, setShown] = useState<{
    url: string;
    mode: "cover" | "blur";
    fontSize: number;
    warnings: string[];
  } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const cleanLines = lines.map((line) => line.trim()).filter(Boolean);
  const source = editing ? { image_id: editing.id } : { image_id: sourceId };
  const options = {
    lines: cleanLines.length > 0 ? cleanLines : null,
    tag: tag.trim() || null,
    preset,
    mode,
    focus_x: focusX,
    focus_y: focusY,
  };
  const key = JSON.stringify([source, options]);

  // The preview follows the fields, a moment after the last keystroke.
  useEffect(() => {
    if (source.image_id == null) return;
    const controller = new AbortController();
    let url: string | null = null;
    const timer = window.setTimeout(() => {
      compositePreview(article.id, { ...source, ...options }, controller.signal)
        .then((preview) => {
          url = preview.url;
          setShown((old) => {
            if (old) URL.revokeObjectURL(old.url);
            return preview;
          });
          setError(null);
        })
        .catch((err) => {
          if (!(err instanceof DOMException)) setError(errorMessage(err));
        });
    }, 350);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
      if (url && url !== shown?.url) URL.revokeObjectURL(url);
    };
    // `key` stands for source and options.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, article.id]);

  useEffect(() => () => setShown((old) => (old && URL.revokeObjectURL(old.url), null)), []);

  async function save() {
    setSaving(true);
    try {
      let saved: Article & { composite_result: CompositeResult };
      if (editing) {
        saved = await api(`/articles/${article.id}/images/${editing.id}/composite`, "PUT", {
          ...options,
          lines: options.lines ?? [],
        });
      } else {
        saved = await api(`/articles/${article.id}/images/composite`, "POST", { ...source, ...options, replace });
      }
      const result = saved.composite_result;
      onSaved(saved, result.image_id);
      const extra = result.warnings.find((warning) => warning.code === "EXTRA_IMAGES");
      message.success("Đã lưu ảnh ghép");
      if (extra) message.warning("Bài còn ảnh khác ngoài ảnh ghép: Facebook sẽ xếp lưới và ảnh ghép bị thu nhỏ.");
      onClose();
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  const cover = (shown?.mode ?? mode) === "cover";
  return (
    <Modal
      open
      title={editing ? "Sửa ảnh ghép" : "Ảnh ghép chữ + ảnh"}
      onCancel={onClose}
      width={820}
      okText={editing ? "Lưu ảnh ghép" : "Tạo ảnh ghép"}
      cancelText="Đóng"
      onOk={() => void save()}
      okButtonProps={{ loading: saving, disabled: source.image_id == null || error !== null }}
      data-testid="article-composite"
    >
      <Flex gap={16} wrap>
        <Flex vertical gap={10} style={{ flex: "1 1 320px", minWidth: 280 }}>
          {!editing && (
            <label>
              <Typography.Text type="secondary">Ảnh món (một ảnh đã gắn trong bài)</Typography.Text>
              <Select
                style={{ width: "100%" }}
                aria-label="Ảnh món"
                value={sourceId}
                onChange={setSourceId}
                options={sources.map((image) => ({
                  value: image.id,
                  label: `Ảnh ${image.position + 1} · ${image.source_label}`,
                }))}
              />
            </label>
          )}
          <div>
            <Typography.Text type="secondary">
              Tiêu đề, tối đa 3 dòng (15–22 ký tự mỗi dòng). Để trống: tự ngắt từ dòng đầu caption.
            </Typography.Text>
            <Flex vertical gap={6}>
              {lines.map((line, index) => (
                <Input
                  key={index}
                  aria-label={`Dòng tiêu đề ${index + 1}`}
                  placeholder={`Dòng ${index + 1}`}
                  value={line}
                  maxLength={60}
                  onChange={(event) => setLines(lines.map((old, i) => (i === index ? event.target.value : old)))}
                />
              ))}
            </Flex>
          </div>
          <label>
            <Typography.Text type="secondary">Nhãn series (để trống: theo kế hoạch nếu có)</Typography.Text>
            <Input
              aria-label="Nhãn series"
              placeholder="NGÀY 5 · THỰC PHẨM TỐT CHO SỨC KHỎE"
              value={tag}
              maxLength={60}
              onChange={(event) => setTag(event.target.value)}
            />
          </label>
          <Flex gap={12} wrap align="center">
            <Select
              aria-label="Màu dải chữ"
              value={preset}
              onChange={setPreset}
              options={PRESETS}
              style={{ width: 120 }}
            />
            <Radio.Group
              aria-label="Kiểu ảnh"
              optionType="button"
              value={mode}
              onChange={(event) => setMode(event.target.value)}
              options={MODES}
            />
          </Flex>
          {mode !== "blur" && cover && (
            <Flex vertical gap={0}>
              <Typography.Text type="secondary">Điểm cắt (khi món không nằm giữa ảnh)</Typography.Text>
              <Flex gap={12} align="center">
                <span>Ngang</span>
                <Slider
                  aria-label="Điểm cắt ngang"
                  style={{ flex: 1 }}
                  min={0}
                  max={1}
                  step={0.01}
                  value={focusX}
                  onChange={setFocusX}
                />
              </Flex>
              <Flex gap={12} align="center">
                <span>Dọc</span>
                <Slider
                  aria-label="Điểm cắt dọc"
                  style={{ flex: 1 }}
                  min={0}
                  max={1}
                  step={0.01}
                  value={focusY}
                  onChange={setFocusY}
                />
              </Flex>
            </Flex>
          )}
          {!editing && (
            <Flex gap={8} align="center">
              <Switch aria-label="Gỡ thẻ chữ và ảnh nguồn" checked={replace} onChange={setReplace} />
              <span>Gỡ thẻ chữ và ảnh nguồn cũ khỏi bài, ảnh ghép lên đầu</span>
            </Flex>
          )}
        </Flex>
        <Flex vertical gap={8} style={{ flex: "0 0 300px" }} align="center">
          {shown ? (
            // The preview is a blob drawn by the api, so next/image has nothing to optimise.
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={shown.url}
              alt="Xem trước ảnh ghép"
              style={{ width: 300, borderRadius: 6, border: "1px solid #ddd" }}
            />
          ) : (
            <Typography.Text type="secondary">
              {source.image_id == null ? "Bài chưa có ảnh món để ghép" : "Đang vẽ…"}
            </Typography.Text>
          )}
          {shown && (
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {MODE_LABEL[shown.mode]} · chữ {shown.fontSize}px
            </Typography.Text>
          )}
          {shown?.warnings.map((code) =>
            WARNINGS[code] ? (
              <Alert key={code} type="warning" showIcon title={WARNINGS[code]} style={{ width: "100%" }} />
            ) : null,
          )}
          {error && <Alert type="error" showIcon title={error} style={{ width: "100%" }} />}
        </Flex>
      </Flex>
    </Modal>
  );
}
