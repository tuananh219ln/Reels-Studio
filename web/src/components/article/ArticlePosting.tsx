"use client";

import { SendOutlined, VideoCameraAddOutlined } from "@ant-design/icons";
import { Alert, App, Button, Card, Flex, Input, Popconfirm, Radio, Select, Typography } from "antd";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  ApiError,
  api,
  errorMessage,
  formatDateTime,
  fromVietnamInput,
  type Article,
  type ArticleNumbers,
  type ArticleOptions,
  type ArticlePost,
} from "@/lib/api";
import FormDrawer from "@/components/FormDrawer";
import ShopeeSuggestions from "@/components/affiliate/ShopeeSuggestions";
import StatusText, { type StatusTone } from "@/components/StatusText";

/** An article's status as a dot: a job running, waiting for its time, out, or failed. */
export const ARTICLE_STATUS_TONES: Record<Article["status"], StatusTone> = {
  draft: "idle",
  publishing: "active",
  unpublishing: "active",
  pending: "waiting",
  failed: "danger",
  scheduled: "waiting",
  published: "success",
};

const TONES: Record<ArticlePost["status"], StatusTone> = {
  pending: "waiting",
  scheduled: "waiting",
  published: "success",
  cancelled: "idle",
  deleted: "idle",
};

function count(value: number | null): string {
  return value === null ? "–" : value.toLocaleString("vi-VN");
}

/** "{reactions} cảm xúc · {comments} bình luận · {shares} chia sẻ · reach {reach}", the share/reach rate when known. */
export function numbersLine(numbers: ArticleNumbers, rate: number | null): string {
  const parts = [
    `${count(numbers.reactions)} cảm xúc`,
    `${count(numbers.comments)} bình luận`,
    `${count(numbers.shares)} chia sẻ`,
    `reach ${count(numbers.reach)}`,
  ];
  if (rate !== null) parts.push(`share/reach ${(rate * 100).toLocaleString("vi-VN", { maximumFractionDigits: 2 })}%`);
  return parts.join(" · ");
}

/** The 48-hour numbers against the Page's median of articles, or why they cannot be read yet. */
export function PostNumbers({ post, options }: { post: ArticlePost; options: ArticleOptions | null }) {
  const { latest, at_48h: mark, analysis, error, pending } = post.numbers;
  const minSamples = options?.min_samples ?? 5;
  return (
    <Flex vertical gap={2} data-testid="article-post-numbers">
      {mark ? (
        <Typography.Text strong={analysis.standout} style={{ fontSize: 13 }}>
          48h: {numbersLine(mark, analysis.share_rate)}
        </Typography.Text>
      ) : (
        <Typography.Text type="secondary" style={{ fontSize: 13 }}>
          chưa đo 48h
        </Typography.Text>
      )}
      {mark && analysis.samples < minSamples && (
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          chưa đủ dữ liệu (cần ≥{minSamples} bài đã đo 48h)
        </Typography.Text>
      )}
      {mark && analysis.times_median !== null && (
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          {analysis.times_median.toLocaleString("vi-VN")}× trung vị reach của Page
        </Typography.Text>
      )}
      {mark && mark.reach !== null && analysis.share_rate === null && (
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          share/reach chỉ tính khi reach từ {options?.min_rated_reach ?? 50}
        </Typography.Text>
      )}
      {latest && (
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          Mới nhất ({formatDateTime(latest.measured_at)}): {numbersLine(latest, null)}
        </Typography.Text>
      )}
      {pending && (
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          Đang chờ worker đọc số…
        </Typography.Text>
      )}
      {error && <Typography.Text type="danger">{error}</Typography.Text>}
    </Flex>
  );
}

/** "Đăng": the Page is chosen here, now or at a time. Warnings from the api (the same caption on another Page, a reel
 * of the Page within two hours) are asked about, then sent again with `confirm`. */
export function PublishButton({
  article,
  options,
  disabled,
  onSaved,
  beforePublish,
}: {
  article: Article;
  options: ArticleOptions | null;
  disabled: boolean;
  onSaved: (article: Article) => void;
  beforePublish: () => Promise<void>;
}) {
  const { message, modal } = App.useApp();
  const [open, setOpen] = useState(false);
  const [picked, setPicked] = useState<number | null>(null);
  const [mode, setMode] = useState<"now" | "later">("now");
  const [when, setWhen] = useState("");
  const [busy, setBusy] = useState(false);
  const pages = options?.fanpages ?? [];
  const fanpage = picked ?? (pages.length === 1 ? pages[0].id : null);
  const chosen = pages.find((page) => page.id === fanpage);

  async function send(confirm: boolean) {
    setBusy(true);
    try {
      await beforePublish();
      const scheduled_at = mode === "later" ? fromVietnamInput(when) : null;
      onSaved(
        await api<Article>(`/articles/${article.id}/publish`, "POST", { fanpage_id: fanpage, scheduled_at, confirm }),
      );
      setOpen(false);
      setMode("now");
      setWhen("");
      message.success(mode === "later" ? "Đã gửi hẹn giờ cho worker" : "Đã gửi đăng cho worker");
    } catch (err) {
      if (err instanceof ApiError && err.code === "confirm_needed") {
        modal.confirm({
          title: "Vẫn đăng bài này?",
          content: err.message,
          okText: "Vẫn đăng",
          cancelText: "Không",
          onOk: () => send(true),
        });
      } else {
        message.error(errorMessage(err));
      }
    } finally {
      setBusy(false);
    }
  }

  const blocking = article.checks.blocking;
  return (
    <>
      <Button type="primary" icon={<SendOutlined />} disabled={disabled} onClick={() => setOpen(true)}>
        Đăng
      </Button>
      <FormDrawer
        title="Đăng bài viết"
        open={open}
        onClose={() => setOpen(false)}
        okText="Đăng"
        onOk={() => send(false)}
        confirmLoading={busy}
        okButtonProps={{ disabled: !fanpage || (mode === "later" && !when) || blocking.length > 0 }}
      >
        {pages.length === 0 ? (
          <Typography.Text>
            Chưa có Fanpage nào đang dùng. Vào{" "}
            <Link prefetch={false} href="/fanpages">
              Quản lý Page
            </Link>{" "}
            để thêm.
          </Typography.Text>
        ) : (
          <Flex vertical gap={8}>
            {blocking.map((issue) => (
              <Alert key={issue.message} type="error" showIcon title={issue.message} />
            ))}
            {chosen?.error && (
              <Alert type="warning" showIcon title={`Lần kiểm tra gần nhất, Fanpage này lỗi: ${chosen.error}`} />
            )}
            <Select
              aria-label="Fanpage"
              value={fanpage}
              placeholder="Chọn Fanpage"
              onChange={setPicked}
              style={{ maxWidth: 320 }}
              options={pages.map((page) => ({
                value: page.id,
                label: page.owner ? `${page.name}, ${page.owner}` : page.name,
              }))}
            />
            <Radio.Group
              value={mode}
              onChange={(event) => setMode(event.target.value)}
              options={[
                { value: "now", label: "Đăng ngay" },
                { value: "later", label: "Hẹn giờ" },
              ]}
            />
            {mode === "later" && (
              <>
                <Input
                  type="datetime-local"
                  aria-label="Giờ đăng"
                  value={when}
                  style={{ maxWidth: 240 }}
                  onChange={(event) => setWhen(event.target.value)}
                />
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  Giờ Việt Nam. Nên chọn giờ khác khung giờ đăng reel của Page.
                </Typography.Text>
              </>
            )}
            <Typography.Text type="secondary">
              Đăng caption đã lưu, kèm ảnh nếu có.{" "}
              {article.products.length > 0
                ? "Khi bài lên, worker tự viết bình luận chứa link sản phẩm; ghim bình luận đó tay trên Facebook."
                : "Bài không gắn sản phẩm nên không có bình luận link."}
            </Typography.Text>
          </Flex>
        )}
      </FormDrawer>
    </>
  );
}

/** Every post of the article, newest first: status, Page, link, numbers, and what can be done with it. */
export function PostsCard({
  article,
  options,
  onSaved,
}: {
  article: Article;
  options: ArticleOptions | null;
  onSaved: (article: Article) => void;
}) {
  const { message } = App.useApp();
  const [busy, setBusy] = useState<string | null>(null);
  if (article.posts.length === 0) return null;

  async function act(post: ArticlePost, action: string, done: string) {
    setBusy(`${post.id}-${action}`);
    try {
      onSaved(await api<Article>(`/articles/posts/${post.id}/${action}`, "POST"));
      message.success(done);
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card size="small" title="Bài đã đăng">
      <Flex vertical gap={16}>
        {article.posts.map((post) => (
          <Flex key={post.id} vertical gap={6} data-testid="article-post">
            <Flex justify="space-between" gap={8} wrap align="center">
              <Flex gap={8} align="center" wrap>
                <StatusText tone={TONES[post.status]}>{post.status_label}</StatusText>
                <Typography.Text>{post.fanpage ?? "—"}</Typography.Text>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  {post.status === "scheduled" && post.scheduled_at
                    ? `hẹn ${formatDateTime(post.scheduled_at)}`
                    : formatDateTime(post.live_at)}
                </Typography.Text>
                {post.url && (
                  <a href={post.url} target="_blank" rel="noreferrer">
                    Xem bài
                  </a>
                )}
              </Flex>
              <Flex gap={6} wrap>
                {post.can_measure && (
                  <Button
                    size="small"
                    loading={busy === `${post.id}-metrics`}
                    onClick={() => act(post, "metrics", "Đã nhờ worker đọc số")}
                  >
                    Cập nhật số
                  </Button>
                )}
                {post.can_check && (
                  <Button
                    size="small"
                    disabled={article.busy}
                    loading={busy === `${post.id}-check`}
                    onClick={() => act(post, "check", "Đã nhờ worker kiểm tra bài")}
                  >
                    Kiểm tra
                  </Button>
                )}
                {post.can_take_down && (
                  <Popconfirm
                    title={post.status === "published" ? "Gỡ bài này khỏi Facebook?" : "Hủy bài này?"}
                    okText={post.status === "published" ? "Gỡ bài" : "Hủy đăng"}
                    cancelText="Không"
                    okButtonProps={{ danger: true }}
                    onConfirm={() => act(post, "take-down", "Đã gửi yêu cầu")}
                  >
                    <Button size="small" danger loading={busy === `${post.id}-take-down`}>
                      {post.status === "published" ? "Gỡ bài" : "Hủy đăng"}
                    </Button>
                  </Popconfirm>
                )}
              </Flex>
            </Flex>
            {(post.status === "published" || post.status === "deleted") && (
              <PostNumbers post={post} options={options} />
            )}
            {post.comment.state !== "off" && (
              <Flex gap={8} align="center" wrap>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  Bình luận link:{" "}
                  {
                    {
                      waiting: "sẽ viết khi bài lên",
                      pending: "worker đang viết…",
                      done: "đã viết, ghim tay trên Facebook",
                      failed: `lỗi: ${post.comment.error ?? ""}`,
                      off: "",
                    }[post.comment.state]
                  }
                </Typography.Text>
                {post.status === "published" && post.comment.state !== "pending" && article.products.length > 0 && (
                  <Button
                    size="small"
                    type="link"
                    loading={busy === `${post.id}-comment`}
                    onClick={() => act(post, "comment", "Đã nhờ worker viết bình luận")}
                  >
                    {post.comment.state === "done" ? "Cập nhật bình luận" : "Bình luận ngay"}
                  </Button>
                )}
              </Flex>
            )}
          </Flex>
        ))}
      </Flex>
    </Card>
  );
}

/** The comment under the post: the pinned comment, then the links of at most two approved Shopee products, chosen
 * from Shopee's suggestions for the article's product ideas (as on a video) or from the group's approved products. */
export function CommentCard({
  article,
  options,
  disabled,
  onSaved,
  reload,
}: {
  article: Article;
  options: ArticleOptions | null;
  disabled: boolean;
  onSaved: (article: Article) => void;
  reload: () => Promise<void>;
}) {
  const { message } = App.useApp();
  const [choices, setChoices] = useState<{ id: number; name: string }[]>([]);
  const [busy, setBusy] = useState(false);
  const [pinned, setPinned] = useState("");
  const [ideas, setIdeas] = useState("");
  const [editing, setEditing] = useState<"pinned" | "ideas" | null>(null);
  const max = options?.max_products ?? 2;

  // A reload (the AI wrote them, a teammate changed them) shows here unless the member is typing in that field.
  const shownPinned = editing === "pinned" ? pinned : article.pinned_comment;
  const shownIdeas = editing === "ideas" ? ideas : article.affiliates.join("\n");

  useEffect(() => {
    api<{ id: number; name: string }[]>(`/articles/${article.id}/product-choices`)
      .then(setChoices)
      .catch(() => undefined);
  }, [article.id, article.knowledge_topic_id, article.products]);

  async function run(call: () => Promise<Article>) {
    setBusy(true);
    try {
      onSaved(await call());
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  function savePinned() {
    setEditing(null);
    if (pinned !== article.pinned_comment) {
      void run(() => api<Article>(`/articles/${article.id}`, "PATCH", { pinned_comment: pinned }));
    }
  }

  function saveIdeas() {
    setEditing(null);
    const list = ideas
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean);
    if (list.join("\n") !== article.affiliates.join("\n")) {
      void run(() => api<Article>(`/articles/${article.id}`, "PATCH", { affiliates: list }));
    }
  }

  const known = new Map([...choices, ...article.products].map((product) => [product.id, product.name]));
  return (
    <Card size="small" title="Bình luận ghim và sản phẩm affiliate">
      <Flex vertical gap={10}>
        <label>
          <Typography.Text type="secondary">Bình luận ghim</Typography.Text>
          <Input.TextArea
            aria-label="Bình luận ghim"
            value={shownPinned}
            maxLength={2000}
            autoSize={{ minRows: 2, maxRows: 6 }}
            disabled={disabled}
            placeholder="Page tự bình luận dưới bài để ghim: gợi chuyện, mời người xem kể trải nghiệm. AI viết kèm caption."
            onFocus={() => {
              setPinned(article.pinned_comment);
              setEditing("pinned");
            }}
            onChange={(event) => setPinned(event.target.value)}
            onBlur={savePinned}
          />
        </label>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          Khi bài lên, worker tự viết bình luận này kèm link sản phẩm đã chọn ở dưới; ghim tay trên Facebook.
        </Typography.Text>
        <label>
          <Typography.Text type="secondary">Gợi ý sản phẩm (AI)</Typography.Text>
          <Input.TextArea
            aria-label="Gợi ý sản phẩm"
            value={shownIdeas}
            autoSize={{ minRows: 1, maxRows: 4 }}
            disabled={disabled}
            placeholder="Từ khoá app dùng để tìm sản phẩm trên Shopee; mỗi dòng một sản phẩm"
            onFocus={() => {
              setIdeas(article.affiliates.join("\n"));
              setEditing("ideas");
            }}
            onChange={(event) => setIdeas(event.target.value)}
            onBlur={saveIdeas}
          />
        </label>
        <ShopeeSuggestions
          base={`/affiliate-products/articles/${article.id}`}
          ideas={article.affiliates}
          state={article.suggest.state}
          attachedIds={article.products.map((product) => product.id)}
          onChanged={reload}
        />
        <Typography.Text strong>Sản phẩm Shopee trong bình luận (tối đa {max})</Typography.Text>
        <Select
          aria-label="Sản phẩm affiliate"
          mode="multiple"
          maxCount={max}
          value={article.products.map((product) => product.id)}
          loading={busy}
          disabled={disabled}
          placeholder={choices.length ? `Chọn tối đa ${max} sản phẩm đã duyệt` : "Nhóm này chưa có sản phẩm đã duyệt"}
          options={[...known].map(([value, label]) => ({ value, label }))}
          optionFilterProp="label"
          onChange={(ids) => run(() => api<Article>(`/articles/${article.id}/products`, "PUT", { product_ids: ids }))}
        />
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          Link chỉ nằm trong bình luận dưới bài. Khi có sản phẩm, bài tự kết bằng câu “
          {options?.product_line ?? "Link sản phẩm mình để ở bình luận ghim."}”.
        </Typography.Text>
      </Flex>
    </Card>
  );
}

/** "Làm reel từ bài này": a video draft on the article's topic, written by the usual script job. */
export function MakeReelButton({ article }: { article: Article }) {
  const { message } = App.useApp();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  return (
    <Popconfirm
      title="Tạo video nháp từ bài này?"
      description="AI sẽ viết kịch bản reel theo chủ đề của bài."
      okText="Tạo video"
      cancelText="Không"
      onConfirm={async () => {
        setBusy(true);
        try {
          const made = await api<{ video_id: number }>(`/articles/${article.id}/make-video`, "POST");
          router.push(`/videos/${made.video_id}`);
        } catch (err) {
          message.error(errorMessage(err));
          setBusy(false);
        }
      }}
    >
      <Button icon={<VideoCameraAddOutlined />} loading={busy} disabled={!article.topic && !article.hook}>
        Làm reel từ bài này
      </Button>
    </Popconfirm>
  );
}
