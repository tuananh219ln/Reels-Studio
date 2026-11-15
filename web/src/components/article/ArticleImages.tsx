"use client";

import ImageProviderMenu from "@/components/video/ImageProviderMenu";
import MediaLibraryPicker from "@/components/video/MediaLibraryPicker";
import StockPicker from "@/components/video/StockPicker";
import {
  api,
  errorMessage,
  upload,
  type Article,
  type ArticleAspect,
  type ArticleOptions,
  type LogoPosition,
} from "@/lib/api";
import { googleImagesUrl, looksLikeLink, tiktokSearchUrl, unwrapLink } from "@/lib/mediaLinks";
import {
  DeleteOutlined,
  DownOutlined,
  FontSizeOutlined,
  GoogleOutlined,
  InboxOutlined,
  PictureOutlined,
  PlusOutlined,
  RobotOutlined,
  SearchOutlined,
  SnippetsOutlined,
  TikTokOutlined,
} from "@ant-design/icons";
import { Alert, App, Button, Card, Dropdown, Flex, Input, Modal, Select, Space, Switch, Typography } from "antd";
import { useEffect, useRef, useState } from "react";

const IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"];

export const LOGO_POSITIONS: { value: LogoPosition; label: string }[] = [
  { value: "top_left", label: "Trên trái" },
  { value: "top_center", label: "Trên giữa" },
  { value: "top_right", label: "Trên phải" },
  { value: "middle_left", label: "Giữa trái" },
  { value: "center", label: "Chính giữa" },
  { value: "middle_right", label: "Giữa phải" },
  { value: "bottom_left", label: "Dưới trái" },
  { value: "bottom_center", label: "Dưới giữa" },
  { value: "bottom_right", label: "Dưới phải" },
];

const ASPECTS: { value: ArticleAspect; label: string }[] = [
  { value: "1:1", label: "Vuông 1:1" },
  { value: "4:5", label: "Dọc 4:5" },
  { value: "1.91:1", label: "Ngang 1.91:1" },
];

/**
 * "Ảnh bài viết": up to 10 photos, taken with the same tools as a scene's photo ("Lấy ảnh", "Tìm ảnh", "Tạo mới") and
 * the same pickers and api searches, each added last instead of replacing a scene's picture. The chosen photo is shown
 * as it will be posted to the Page picked in "Logo của Page", with its logo; each photo has its own logo switch and
 * place. Photos are dragged to change their order.
 */
export default function ArticleImages({
  article,
  options,
  disabled,
  onSaved,
}: {
  article: Article;
  options: ArticleOptions | null;
  disabled: boolean;
  onSaved: (article: Article) => void;
}) {
  const { message } = App.useApp();
  const id = article.id;
  const images = article.images;
  const max = 10;
  const [selectedId, setSelectedId] = useState<number | null>(images[0]?.id ?? null);
  const selected = images.find((image) => image.id === selectedId) ?? images[0] ?? null;
  const pages = options?.fanpages ?? [];
  const [pageId, setPageId] = useState<number | null>(null);
  const previewPage = pageId ?? pages[0]?.id ?? null;
  const [busy, setBusy] = useState<string | null>(null);
  const [query, setQuery] = useState(article.image_query);
  const [prompt, setPrompt] = useState(article.image_prompt);
  const [advanced, setAdvanced] = useState(Boolean(article.image_prompt));
  const [picking, setPicking] = useState(false);
  const [fromLibrary, setFromLibrary] = useState(false);
  const [pasting, setPasting] = useState(false);
  const [pastedLink, setPastedLink] = useState("");
  const [dragged, setDragged] = useState<number | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const typing = useRef({ query: false, prompt: false });

  // A reload (the AI's photo, a teammate's edit) refreshes the fields not being typed in.
  useEffect(() => {
    if (!typing.current.query) setQuery(article.image_query);
    if (!typing.current.prompt) setPrompt(article.image_prompt);
  }, [article.image_query, article.image_prompt]);

  const full = images.length >= max;
  const off = disabled || busy !== null;
  const aiRunning = article.image_job?.status === "queued" || article.image_job?.status === "running";
  const aiFailed = article.image_job?.status === "failed" ? article.image_job.error : null;
  const words = query.trim() || article.topic.trim() || article.hook;

  async function run(action: string, call: () => Promise<Article>, done?: string) {
    setBusy(action);
    try {
      const saved = await call();
      onSaved(saved);
      if (done) message.success(done);
      return saved;
    } catch (err) {
      message.error(errorMessage(err));
      return null;
    } finally {
      setBusy(null);
    }
  }

  /** A new photo was added: it is the one shown. */
  async function add(action: string, call: () => Promise<Article & { notice?: string }>, done: string) {
    const saved: (Article & { notice?: string }) | null = await run(action, call, done);
    if (saved) {
      setSelectedId(saved.images[saved.images.length - 1]?.id ?? null);
      // A photo from a stock photo site (watermark, licence): kept, with a warning.
      if (saved.notice) message.warning(saved.notice);
    }
  }

  function save(fields: Record<string, unknown>) {
    return run("save", () => api<Article>(`/articles/${id}`, "PATCH", fields));
  }

  function saveTyped(field: "image_query" | "image_prompt", value: string) {
    typing.current[field === "image_query" ? "query" : "prompt"] = false;
    return value !== article[field] ? save({ [field]: value }) : Promise.resolve(null);
  }

  async function uploadFiles(files: File[]) {
    const photos = files.filter((file) => IMAGE_TYPES.includes(file.type)).slice(0, max - images.length);
    if (photos.length === 0) {
      message.error("Chỉ nhận ảnh JPG, PNG hoặc WebP");
      return;
    }
    for (const file of photos) {
      await add("upload", () => upload<Article>(`/articles/${id}/images`, file), "Đã thêm ảnh");
    }
  }

  function fromLink(link: string) {
    return add(
      "link",
      () => api<Article>(`/articles/${id}/images/from-url`, "POST", { url: unwrapLink(link) }),
      "Đã lấy ảnh",
    );
  }

  /** "Dán…": the clipboard read directly when the browser allows it, otherwise a box to paste into. */
  async function pasteFromClipboard() {
    try {
      for (const item of await navigator.clipboard.read()) {
        const type = item.types.find((name) => IMAGE_TYPES.includes(name));
        if (type) {
          const blob = await item.getType(type);
          await uploadFiles([new File([blob], `anh-dan.${type.split("/")[1].replace("jpeg", "jpg")}`, { type })]);
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

  async function generate(provider?: "cloudflare" | "gemini") {
    // The job reads the saved words: those being typed are saved first.
    await saveTyped("image_query", query);
    await saveTyped("image_prompt", prompt);
    await run(
      "ai",
      () => api<Article>(`/articles/${id}/images/ai${provider ? `?provider=${provider}` : ""}`, "POST"),
      "Đang tạo ảnh AI, ảnh sẽ được thêm vào cuối",
    );
  }

  function openSite(url: (keyword: string) => string) {
    if (!words) {
      message.info("Nhập từ khóa tìm ảnh trước");
      return;
    }
    window.open(url(words), "_blank", "noopener");
  }

  function drop(targetId: number) {
    if (dragged === null || dragged === targetId) return;
    const ids = images.map((image) => image.id).filter((item) => item !== dragged);
    ids.splice(ids.indexOf(targetId), 0, dragged);
    setDragged(null);
    void run("order", () => api<Article>(`/articles/${id}/images/order`, "PUT", { ids }));
  }

  const previewSrc = selected
    ? `${selected.preview_url}${previewPage ? `&fanpage_id=${previewPage}` : ""}&logo=${selected.logo_enabled}-${selected.logo_position ?? ""}`
    : null;

  const tools = (
    <Flex vertical gap={8} style={{ width: 220, flex: "none" }} data-testid="article-image-tools">
      <Typography.Text type="secondary" style={{ fontSize: 12, fontWeight: 600 }}>
        LẤY ẢNH
      </Typography.Text>
      <Flex gap={6}>
        <input
          ref={input}
          type="file"
          accept={IMAGE_TYPES.join(",")}
          multiple
          hidden
          aria-label="Chọn ảnh tải lên"
          onChange={(event) => {
            const files = Array.from(event.target.files ?? []);
            event.target.value = "";
            void uploadFiles(files);
          }}
        />
        <Button
          icon={<InboxOutlined />}
          disabled={off || full}
          loading={busy === "upload"}
          onClick={() => input.current?.click()}
          style={{ flex: 1 }}
        >
          Tải lên
        </Button>
        <Button
          aria-label="Dán ảnh/link"
          icon={<SnippetsOutlined />}
          disabled={off || full}
          loading={busy === "link"}
          onClick={() => void pasteFromClipboard()}
          style={{ flex: 1 }}
        >
          Dán…
        </Button>
      </Flex>
      <Button icon={<PictureOutlined />} disabled={off || full} block onClick={() => setFromLibrary(true)}>
        Chọn từ kho
      </Button>
      <Typography.Text type="secondary" style={{ fontSize: 12, fontWeight: 600 }}>
        TÌM ẢNH
      </Typography.Text>
      <Button icon={<SearchOutlined />} disabled={off || full} block onClick={() => setPicking(true)}>
        Tìm ảnh (Pexels…)
      </Button>
      <Flex gap={6}>
        <Button
          icon={<GoogleOutlined />}
          disabled={off}
          onClick={() => openSite(googleImagesUrl)}
          title="Mở Google Ảnh với từ khóa; sao chép ảnh ưng ý rồi bấm Dán…"
          style={{ flex: 1 }}
        >
          Google
        </Button>
        <Button
          icon={<TikTokOutlined />}
          disabled={off}
          onClick={() => openSite(tiktokSearchUrl)}
          title="Mở TikTok với từ khóa; sao chép link ảnh ưng ý rồi bấm Dán…"
          style={{ flex: 1 }}
        >
          TikTok
        </Button>
      </Flex>
      <Typography.Text type="secondary" style={{ fontSize: 12, fontWeight: 600 }}>
        TẠO MỚI
      </Typography.Text>
      <Space.Compact block>
        <Button
          icon={<RobotOutlined />}
          disabled={off || full || aiRunning}
          loading={busy === "ai" || aiRunning}
          onClick={() => void generate()}
          style={{ flex: 1 }}
        >
          {aiRunning ? "Đang tạo ảnh AI…" : "Tạo ảnh AI"}
        </Button>
        <ImageProviderMenu disabled={off || full || aiRunning} onPick={(provider) => void generate(provider)} />
      </Space.Compact>
      <Dropdown
        trigger={["click"]}
        disabled={off || full || !article.hook}
        menu={{
          items: (options?.card_presets ?? []).map((preset) => ({
            key: preset.value,
            label: `Thẻ chữ ${preset.label}`,
          })),
          onClick: ({ key }) =>
            void add(
              "card",
              () => api<Article>(`/articles/${id}/images/text-card`, "POST", { preset: key }),
              "Đã tạo thẻ chữ",
            ),
        }}
      >
        <Button
          icon={<FontSizeOutlined />}
          disabled={off || full || !article.hook}
          loading={busy === "card"}
          block
          title={article.hook ? "Dòng đầu của caption trên nền màu" : "Viết caption trước (dòng đầu là chữ trên thẻ)"}
        >
          Thẻ chữ <DownOutlined style={{ fontSize: 10 }} />
        </Button>
      </Dropdown>
    </Flex>
  );

  return (
    <Card
      size="small"
      title={`Ảnh bài viết (${images.length}/${max}) · logo tự chèn`}
      extra={
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          Kéo để đổi thứ tự
        </Typography.Text>
      }
      data-testid="article-images"
    >
      <Flex vertical gap={12}>
        {aiFailed && <Alert type="error" showIcon title={`Tạo ảnh AI chưa được: ${aiFailed}`} />}
        <Flex gap={8} wrap data-testid="article-image-strip">
          {images.map((image, index) => (
            <button
              key={image.id}
              type="button"
              draggable={!off}
              aria-label={`Ảnh ${index + 1}`}
              aria-pressed={selected?.id === image.id}
              onClick={() => setSelectedId(image.id)}
              onDragStart={() => setDragged(image.id)}
              onDragOver={(event) => event.preventDefault()}
              onDrop={() => drop(image.id)}
              style={{
                width: 64,
                height: 64,
                padding: 0,
                borderRadius: 8,
                overflow: "hidden",
                cursor: "pointer",
                position: "relative",
                border:
                  selected?.id === image.id
                    ? "2px solid var(--ant-color-primary)"
                    : "1px solid var(--ant-color-border)",
                background: "var(--ant-color-fill-quaternary)",
              }}
            >
              {/* eslint-disable-next-line @next/next/no-img-element -- a private file behind the login */}
              <img
                src={image.url}
                alt=""
                style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }}
              />
              <span
                style={{
                  position: "absolute",
                  left: 4,
                  top: 2,
                  fontSize: 11,
                  color: "#fff",
                  textShadow: "0 0 3px rgba(0,0,0,0.8)",
                }}
              >
                {index + 1}
              </span>
            </button>
          ))}
          {!full && (
            <Button
              aria-label="Thêm ảnh"
              icon={<PlusOutlined />}
              disabled={off}
              onClick={() => input.current?.click()}
              style={{ width: 64, height: 64, borderStyle: "dashed" }}
            />
          )}
        </Flex>

        <Flex gap={16} wrap>
          <Flex vertical gap={8} style={{ flex: "1 1 260px", minWidth: 0 }}>
            {selected && previewSrc ? (
              <>
                {/* eslint-disable-next-line @next/next/no-img-element -- drawn by the api with the Page's logo */}
                <img
                  src={previewSrc}
                  alt={`Ảnh ${images.indexOf(selected) + 1} có logo`}
                  data-testid="article-image-preview"
                  style={{
                    width: "100%",
                    borderRadius: 8,
                    display: "block",
                    background: "var(--ant-color-fill-quaternary)",
                  }}
                />
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  {selected.source_label}
                  {selected.source_ref && !selected.source_ref.startsWith("ai:") ? ` · ${selected.source_ref}` : ""}
                  {selected.credit ? ` · Cần ghi nguồn: ${selected.credit}` : ""}
                </Typography.Text>
                <Flex gap={8} align="center" wrap>
                  <Switch
                    size="small"
                    checked={selected.logo_enabled}
                    disabled={off}
                    aria-label="Logo ảnh này"
                    onChange={(on) =>
                      void run("logo", () =>
                        api<Article>(`/articles/${id}/images/${selected.id}`, "PATCH", { logo_enabled: on }),
                      )
                    }
                  />
                  <Typography.Text style={{ fontSize: 13 }}>Logo ảnh này</Typography.Text>
                  <Select
                    size="small"
                    aria-label="Vị trí logo ảnh này"
                    style={{ minWidth: 140 }}
                    disabled={off || !selected.logo_enabled}
                    value={selected.logo_position ?? "page"}
                    options={[{ value: "page", label: "Theo Page" }, ...LOGO_POSITIONS]}
                    onChange={(value: string) =>
                      void run("logo", () =>
                        api<Article>(`/articles/${id}/images/${selected.id}`, "PATCH", {
                          logo_position: value === "page" ? null : value,
                        }),
                      )
                    }
                  />
                  <Button
                    size="small"
                    danger
                    type="text"
                    icon={<DeleteOutlined />}
                    disabled={off}
                    loading={busy === "remove"}
                    onClick={() =>
                      void run(
                        "remove",
                        () => api<Article>(`/articles/${id}/images/${selected.id}`, "DELETE"),
                        "Đã bỏ ảnh",
                      )
                    }
                  >
                    Bỏ ảnh
                  </Button>
                </Flex>
              </>
            ) : (
              <Typography.Text type="secondary">Chưa có ảnh: bài sẽ đăng dạng chỉ chữ.</Typography.Text>
            )}
            <label>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                Xem logo của Page
              </Typography.Text>
              <Select
                aria-label="Xem logo của Page"
                style={{ width: "100%" }}
                size="small"
                value={previewPage ?? undefined}
                placeholder="Chưa có Page của bạn"
                options={pages.map((page) => ({ value: page.id, label: page.name }))}
                onChange={(value: number) => setPageId(value)}
              />
            </label>
          </Flex>
          {tools}
        </Flex>

        <Flex gap={12} wrap align="end">
          <label style={{ flex: "1 1 240px" }}>
            <Typography.Text type="secondary">Từ khóa tìm ảnh</Typography.Text>
            <Input
              aria-label="Từ khóa tìm ảnh"
              value={query}
              maxLength={200}
              disabled={disabled}
              placeholder={article.topic || "VD: bữa sáng, yến mạch sữa chua"}
              onChange={(event) => {
                typing.current.query = true;
                setQuery(event.target.value);
              }}
              onBlur={() => void saveTyped("image_query", query)}
            />
          </label>
          <label>
            <Typography.Text type="secondary">Tỉ lệ ảnh AI</Typography.Text>
            <Select
              aria-label="Tỉ lệ ảnh AI"
              style={{ width: 150, display: "block" }}
              value={article.image_aspect}
              disabled={off}
              options={ASPECTS}
              onChange={(value) => void save({ image_aspect: value })}
            />
          </label>
        </Flex>
        <div>
          <Button type="link" size="small" style={{ padding: 0 }} onClick={() => setAdvanced(!advanced)}>
            {advanced ? "▾" : "›"} Nâng cao: Prompt ảnh AI
          </Button>
          {advanced && (
            <Input.TextArea
              aria-label="Prompt ảnh AI"
              value={prompt}
              maxLength={2000}
              autoSize={{ minRows: 2, maxRows: 6 }}
              disabled={disabled}
              placeholder="Để trống: dùng từ khóa tìm ảnh, rồi chủ đề của bài"
              onChange={(event) => {
                typing.current.prompt = true;
                setPrompt(event.target.value);
              }}
              onBlur={() => void saveTyped("image_prompt", prompt)}
            />
          )}
        </div>
      </Flex>

      {picking && (
        <StockPicker
          searchPath={`/articles/${id}/stock`}
          keywords={words ? [words] : []}
          keywordsEn={[]}
          forWhat="bài này"
          initialOrientation="all"
          title="Tìm ảnh cho bài viết"
          onPick={async (hit, searched) => {
            const saved = await api<Article>(`/articles/${id}/images/stock`, "POST", { ...searched, url: hit.url });
            onSaved(saved);
            setSelectedId(saved.images[saved.images.length - 1]?.id ?? null);
            message.success("Đã thêm ảnh");
          }}
          onClose={() => setPicking(false)}
        />
      )}
      {fromLibrary && (
        <MediaLibraryPicker
          topic={article.topic || article.hook}
          hasPicture={false}
          usedFor="bài viết"
          onUse={async (mediaId) => {
            const saved = await api<Article>(`/articles/${id}/images/library`, "POST", { media_id: mediaId });
            onSaved(saved);
            setSelectedId(saved.images[saved.images.length - 1]?.id ?? null);
          }}
          onClose={() => setFromLibrary(false)}
        />
      )}
      {pasting && (
        <Modal
          open
          title="Dán ảnh hoặc link ảnh"
          okText="Lấy ảnh"
          cancelText="Huỷ"
          okButtonProps={{ disabled: !pastedLink.trim() }}
          onCancel={() => setPasting(false)}
          onOk={() => {
            setPasting(false);
            void fromLink(pastedLink.trim());
          }}
        >
          <Input
            autoFocus
            aria-label="Link ảnh"
            placeholder="Dán ảnh (Ctrl+V) hoặc link ảnh vào đây…"
            value={pastedLink}
            onChange={(event) => setPastedLink(event.target.value)}
            onPaste={(event) => {
              const file = Array.from(event.clipboardData.files).find((item) => IMAGE_TYPES.includes(item.type));
              if (file) {
                event.preventDefault();
                setPasting(false);
                void uploadFiles([file]);
              }
            }}
          />
        </Modal>
      )}
    </Card>
  );
}
