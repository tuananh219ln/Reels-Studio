"use client";

import { useMe } from "@/components/MeContext";
import { ArrowLeftOutlined, DeleteOutlined, LinkOutlined, RobotOutlined } from "@ant-design/icons";
import { Alert, App, Button, Card, Col, Flex, Input, Popconfirm, Result, Row, Select, Spin, Typography } from "antd";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  ApiError,
  api,
  errorMessage,
  type Article,
  type ArticleOptions,
  type Knowledge,
  type PageComments,
} from "@/lib/api";
import StatusText from "@/components/StatusText";
import {
  ARTICLE_STATUS_TONES,
  MakeReelButton,
  PostsCard,
  CommentCard,
  PublishButton,
} from "@/components/article/ArticlePosting";
import { usePolling } from "@/lib/polling";

// While a job runs or the worker owes an answer, the page asks every 2.5 s; otherwise it waits for the member.
const BUSY_REFRESH_MS = 2500;

/** What the article will look like in the feed: the Page's name is chosen when posting, so it is a placeholder. */
function FeedPreview({
  article,
  caption,
  productLine,
}: {
  article: Article;
  caption: string;
  productLine: string | null;
}) {
  const pointer = productLine && !caption.toLowerCase().includes(productLine.replace(/\.$/, "").toLowerCase());
  const text = [caption.trim(), pointer ? productLine : "", article.hashtags.join(" ")].filter(Boolean).join("\n\n");
  return (
    <Card size="small" title="Xem trước trên Facebook" data-testid="article-preview">
      <Flex vertical gap={10}>
        <Flex gap={8} align="center">
          <div
            style={{ width: 36, height: 36, borderRadius: "50%", background: "var(--ant-color-fill-secondary)" }}
            aria-hidden
          />
          <Flex vertical>
            <Typography.Text strong>Tên Page</Typography.Text>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              Chọn Page lúc đăng
            </Typography.Text>
          </Flex>
        </Flex>
        <Typography.Paragraph style={{ margin: 0, whiteSpace: "pre-wrap" }}>
          {text || <Typography.Text type="secondary">(chưa có caption)</Typography.Text>}
        </Typography.Paragraph>
        {article.has_image && (
          // eslint-disable-next-line @next/next/no-img-element -- a private file behind the login
          <img
            src={`/api/articles/${article.id}/image?v=${article.image_version}`}
            alt="Ảnh của bài"
            style={{ width: "100%", borderRadius: 6, display: "block" }}
          />
        )}
        {(article.pinned_comment || article.products.length > 0) && (
          <div
            style={{ background: "var(--ant-color-fill-quaternary)", borderRadius: 8, padding: "8px 10px" }}
            data-testid="article-preview-comment"
          >
            <Typography.Text strong style={{ fontSize: 12 }}>
              Bình luận ghim (worker viết khi bài lên)
            </Typography.Text>
            <Typography.Paragraph style={{ margin: 0, whiteSpace: "pre-wrap", fontSize: 13 }}>
              {[article.pinned_comment, ...article.products.map((product) => `${product.name}: link Shopee của Page`)]
                .filter(Boolean)
                .join("\n")}
            </Typography.Paragraph>
          </div>
        )}
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          Link sản phẩm (nếu có) nằm ở bình luận ghim, không nằm trong bài.
        </Typography.Text>
      </Flex>
    </Card>
  );
}

export default function ArticlePage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { message, modal } = App.useApp();
  const { me } = useMe();
  const [article, setArticle] = useState<Article | null>(null);
  const [missing, setMissing] = useState(false);
  const [options, setOptions] = useState<ArticleOptions | null>(null);
  const [groups, setGroups] = useState<Knowledge["topics"]>([]);
  const [comments, setComments] = useState<PageComments["comments"]>([]);
  const [topic, setTopic] = useState("");
  const [caption, setCaption] = useState("");
  const [link, setLink] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  // The fields a member is typing in keep their text when a reload arrives meanwhile.
  const typing = useRef({ topic: false, caption: false });

  const show = useCallback((next: Article) => {
    setArticle(next);
    if (!typing.current.topic) setTopic(next.topic);
    if (!typing.current.caption) setCaption(next.caption);
  }, []);

  const load = useCallback(async () => {
    try {
      show(await api<Article>(`/articles/${id}`));
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) setMissing(true);
      else message.error(errorMessage(err));
    }
  }, [id, show, message]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- the first load; state is set only after the request answers
    void load();
    api<ArticleOptions>("/articles/options")
      .then(setOptions)
      .catch(() => undefined);
    api<Knowledge>("/knowledge")
      .then((data) => setGroups(data.topics))
      .catch(() => undefined);
  }, [load]);

  const writing = article?.busy ?? false;
  // The worker still owes an answer: a job, a post on its way, a comment or a reading asked for.
  const waiting =
    writing ||
    (article?.posts ?? []).some(
      (post) => post.status === "pending" || post.comment.state === "pending" || post.numbers.pending,
    );
  const poll = useCallback(async () => {
    if (waiting) await load();
  }, [waiting, load]);
  usePolling(poll, BUSY_REFRESH_MS);

  useEffect(() => {
    if (article?.kind === "tra_loi_binh_luan") {
      api<PageComments>("/comments?state=all")
        .then((data) => setComments(data.comments))
        .catch(() => undefined);
    }
  }, [article?.kind]);

  async function run(action: string, call: () => Promise<Article>, done?: string) {
    setBusy(action);
    try {
      show(await call());
      if (done) message.success(done);
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  function save(fields: Record<string, unknown>) {
    return run("save", () => api<Article>(`/articles/${id}`, "PATCH", fields));
  }

  function saveTyped(field: "topic" | "caption", value: string) {
    typing.current[field] = false;
    return article && value !== article[field] ? save({ [field]: value }) : Promise.resolve();
  }

  function writeWithAi() {
    const go = () => run("caption", () => api<Article>(`/articles/${id}/caption`, "POST"));
    if (caption.trim()) {
      modal.confirm({
        title: "AI viết lại caption?",
        content: "Caption và hashtag hiện tại sẽ được thay bằng bài AI viết.",
        okText: "Viết lại",
        cancelText: "Không",
        onOk: go,
      });
    } else {
      void go();
    }
  }

  if (missing) {
    return (
      <Result
        status="404"
        title="Không tìm thấy bài viết"
        subTitle="Có thể bài đã bị xoá."
        extra={
          <Link prefetch={false} href="/articles">
            Về danh sách bài viết
          </Link>
        }
      />
    );
  }
  if (!article) {
    return (
      <Flex justify="center" style={{ padding: 64 }}>
        <Spin />
      </Flex>
    );
  }

  const locked = writing || busy !== null;
  const failed = article.job?.status === "failed" ? article.job.error : null;
  const aiWriting = article.job?.status === "queued" || article.job?.status === "running";

  return (
    <Flex vertical gap={16}>
      <Flex justify="space-between" align="center" gap={12} wrap>
        <Flex align="center" gap={12} wrap>
          <Link prefetch={false} href="/articles" aria-label="Về danh sách bài viết">
            <ArrowLeftOutlined />
          </Link>
          <Typography.Title level={3} style={{ margin: 0, fontWeight: 600 }}>
            {article.hook || article.topic || "Bài viết mới"}
          </Typography.Title>
          {aiWriting ? (
            <StatusText tone="active">AI đang viết…</StatusText>
          ) : (
            <StatusText tone={ARTICLE_STATUS_TONES[article.status]} data-testid="article-status">
              {article.status_label}
            </StatusText>
          )}
        </Flex>
        <Flex gap={8} wrap>
          <MakeReelButton article={article} />
          <PublishButton
            article={article}
            options={options}
            disabled={locked}
            onSaved={show}
            beforePublish={() => saveTyped("caption", caption)}
          />
          {article.created_by_id === me.id && (
            <Popconfirm
              title="Xoá bài viết này?"
              okText="Xoá"
              cancelText="Không"
              okButtonProps={{ danger: true }}
              onConfirm={async () => {
                try {
                  await api(`/articles/${id}`, "DELETE");
                  router.push("/articles");
                } catch (err) {
                  message.error(errorMessage(err));
                }
              }}
            >
              <Button danger icon={<DeleteOutlined />} disabled={writing}>
                Xoá
              </Button>
            </Popconfirm>
          )}
        </Flex>
      </Flex>

      {failed && <Alert type="error" showIcon title={`AI viết chưa được: ${failed}`} />}
      {article.publish_error && (
        <Alert
          type="error"
          showIcon
          title={`Đăng chưa được: ${article.publish_error}`}
          description="Sửa rồi bấm Đăng lại, hoặc Thử lại trong Job logs."
        />
      )}

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={14}>
          <Flex vertical gap={16}>
            <Card size="small" title="Nội dung">
              <Flex vertical gap={12}>
                <Flex gap={12} wrap>
                  <label style={{ flex: "1 1 200px" }}>
                    <Typography.Text type="secondary">Nhóm chủ đề</Typography.Text>
                    <Select
                      aria-label="Nhóm chủ đề"
                      style={{ width: "100%" }}
                      value={article.knowledge_topic_id ?? undefined}
                      disabled={locked}
                      options={groups.map((group) => ({ value: group.id, label: group.name }))}
                      onChange={(value) => save({ knowledge_topic_id: value })}
                    />
                  </label>
                  <label style={{ flex: "1 1 200px" }}>
                    <Typography.Text type="secondary">Dạng bài</Typography.Text>
                    <Select
                      aria-label="Dạng bài"
                      style={{ width: "100%" }}
                      value={article.kind}
                      disabled={locked}
                      options={options?.kinds ?? [{ value: article.kind, label: article.kind_label }]}
                      onChange={(value) => save({ kind: value })}
                    />
                  </label>
                </Flex>
                <label>
                  <Typography.Text type="secondary">Chủ đề của bài</Typography.Text>
                  <Input.TextArea
                    aria-label="Chủ đề của bài"
                    value={topic}
                    maxLength={300}
                    autoSize={{ minRows: 1, maxRows: 3 }}
                    disabled={writing}
                    onChange={(event) => {
                      typing.current.topic = true;
                      setTopic(event.target.value);
                    }}
                    onBlur={() => saveTyped("topic", topic)}
                  />
                </label>
                {article.kind === "tra_loi_binh_luan" && (
                  <label>
                    <Typography.Text type="secondary">Bình luận được trả lời</Typography.Text>
                    <Select
                      aria-label="Bình luận được trả lời"
                      style={{ width: "100%" }}
                      showSearch
                      allowClear
                      optionFilterProp="label"
                      disabled={locked}
                      value={article.source_comment?.id}
                      placeholder="Chọn bình luận"
                      options={[
                        ...(article.source_comment &&
                        !comments.some((comment) => comment.id === article.source_comment!.id)
                          ? [article.source_comment]
                          : []),
                        ...comments,
                      ].map((comment) => ({
                        value: comment.id,
                        label: `${comment.author || "Người xem"}: ${comment.message}`,
                      }))}
                      onChange={(value) => save(value ? { source_comment_id: value } : { clear_source_comment: true })}
                    />
                  </label>
                )}
                <Flex justify="space-between" align="end" gap={8} wrap>
                  <Typography.Text type="secondary">Caption</Typography.Text>
                  <Button
                    icon={<RobotOutlined />}
                    loading={busy === "caption" || aiWriting}
                    disabled={locked || !topic.trim()}
                    title={topic.trim() ? undefined : "Nhập chủ đề của bài trước"}
                    onClick={writeWithAi}
                  >
                    {aiWriting ? "AI đang viết…" : "AI viết"}
                  </Button>
                </Flex>
                <Input.TextArea
                  aria-label="Caption"
                  value={caption}
                  maxLength={5000}
                  autoSize={{ minRows: 8, maxRows: 24 }}
                  disabled={writing}
                  placeholder="Dòng đầu là câu mở bài (và là chữ trên Thẻ chữ). Bài sức khỏe nên có một câu nhắc nhẹ, như người quen dặn nhau, và kết bằng 1 câu hỏi."
                  onChange={(event) => {
                    typing.current.caption = true;
                    setCaption(event.target.value);
                  }}
                  onBlur={() => saveTyped("caption", caption)}
                />
                <label>
                  <Typography.Text type="secondary">
                    Hashtag (tối đa {options?.max_hashtags ?? 5}, đặt ở cuối bài)
                  </Typography.Text>
                  <Select
                    aria-label="Hashtag"
                    mode="tags"
                    style={{ width: "100%" }}
                    value={article.hashtags}
                    disabled={locked}
                    maxCount={options?.max_hashtags ?? 5}
                    tokenSeparators={[" ", ","]}
                    open={false}
                    onChange={(value) => save({ hashtags: value })}
                  />
                </label>
                {article.checks.blocking.map((issue) => (
                  <Alert key={issue.message} type="error" showIcon title={issue.message} />
                ))}
                {article.checks.warnings.map((issue) => (
                  <Alert key={issue.message} type="warning" showIcon title={issue.message} />
                ))}
              </Flex>
            </Card>

            <Card
              size="small"
              title="Ảnh (không bắt buộc)"
              extra={
                article.has_image && (
                  <Button
                    size="small"
                    disabled={locked}
                    loading={busy === "remove"}
                    onClick={() => run("remove", () => api<Article>(`/articles/${id}/image`, "DELETE"), "Đã bỏ ảnh")}
                  >
                    Bỏ ảnh
                  </Button>
                )
              }
            >
              <Flex vertical gap={12}>
                <Typography.Text type="secondary">
                  {article.has_image
                    ? `Đang dùng: ${article.image_kind_label}${article.image_source ? ` (${article.image_source})` : ""}`
                    : "Chưa có ảnh: bài sẽ đăng dạng chỉ chữ."}
                </Typography.Text>
                <div>
                  <Typography.Text strong>Thẻ chữ</Typography.Text>
                  <Typography.Paragraph type="secondary" style={{ margin: "2px 0 8px" }}>
                    Dòng đầu của caption trên nền màu. Lưu caption trước khi tạo thẻ.
                  </Typography.Paragraph>
                  <Flex gap={8} wrap>
                    {(options?.card_presets ?? []).map((preset) => (
                      <Button
                        key={preset.value}
                        disabled={locked || !article.hook}
                        loading={busy === `card-${preset.value}`}
                        style={{ background: preset.background, color: preset.color, borderColor: preset.background }}
                        onClick={() =>
                          run(
                            `card-${preset.value}`,
                            () => api<Article>(`/articles/${id}/text-card`, "POST", { preset: preset.value }),
                            "Đã tạo thẻ chữ",
                          )
                        }
                      >
                        {preset.label}
                      </Button>
                    ))}
                  </Flex>
                </div>
                <div>
                  <Typography.Text strong>Ảnh từ link</Typography.Text>
                  <Flex gap={8} style={{ marginTop: 8 }}>
                    <Input
                      aria-label="Link ảnh"
                      prefix={<LinkOutlined />}
                      placeholder="Dán link ảnh…"
                      value={link}
                      onChange={(event) => setLink(event.target.value)}
                    />
                    <Button
                      disabled={locked || !link.trim()}
                      loading={busy === "link"}
                      onClick={() =>
                        run(
                          "link",
                          async () => {
                            const saved = await api<Article>(`/articles/${id}/image-from-url`, "POST", { url: link });
                            setLink("");
                            return saved;
                          },
                          "Đã lấy ảnh",
                        )
                      }
                    >
                      Lấy ảnh
                    </Button>
                  </Flex>
                </div>
              </Flex>
            </Card>
            <CommentCard article={article} options={options} disabled={locked} onSaved={show} reload={load} />
          </Flex>
        </Col>
        <Col xs={24} lg={10}>
          <Flex vertical gap={16}>
            <PostsCard article={article} options={options} onSaved={show} />
            <FeedPreview
              article={article}
              caption={caption}
              productLine={article.products.length ? (options?.product_line ?? null) : null}
            />
          </Flex>
        </Col>
      </Row>
    </Flex>
  );
}
