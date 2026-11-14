"use client";

import { CopyOutlined } from "@ant-design/icons";
import { App, Alert, Button, Card, Flex, Select, Typography } from "antd";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import ShopeeSuggestions from "@/components/affiliate/ShopeeSuggestions";
import PostComment from "@/components/PostComment";
import StatusText from "@/components/StatusText";
import { api, errorMessage, type AffiliateProduct, type VideoDetail } from "@/lib/api";
import AutoSaveField, { useEditor } from "./AutoSaveField";
import ExtraComments from "./ExtraComments";

type PostFields = Pick<VideoDetail, "caption" | "hashtags" | "affiliates" | "pinned_comment">;

const lines = (text: string) =>
  text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
const words = (text: string) => text.split(/\s+/).filter(Boolean);

/** The blocks of the post texts a step of the progress line can point at (`data-post-block`). */
export type PostBlockKey = "caption" | "comments" | "products";

/**
 * The post's texts under "Sẵn sàng đăng?", in a fixed order: the caption, the comments, the products, and the
 * hashtags last, each a block of its own. "Copy caption + hashtag" stays at the top of the first: it copies both,
 * wherever the hashtags are typed. The music suggestions and the AI's safety review are not shown any more
 * (docs/decisions/2026-11-14-video-editor-spec.md); a hand-written video still says it was not reviewed.
 */
export default function PostContent({ video }: { video: VideoDetail }) {
  const { message } = App.useApp();
  const patch = (body: Partial<PostFields>) => api<VideoDetail>(`/videos/${video.id}`, "PATCH", body);
  const warningsFor = (field: string) =>
    video.video_warnings.filter((warning) => warning.field === field).map((warning) => warning.message);

  async function copy(text: string, what: string) {
    try {
      await navigator.clipboard.writeText(text);
      message.success(`Đã copy ${what}`);
    } catch {
      message.error("Trình duyệt không cho copy, hãy chọn chữ rồi copy tay");
    }
  }

  /** A "Copy" in a block's title. */
  const copyButton = (label: string, text: string, what: string) => (
    <Button size="small" icon={<CopyOutlined />} onClick={() => void copy(text, what)}>
      {label}
    </Button>
  );

  const products = video.affiliate_product_ids.length;
  const shop = video.platform === "tiktok" ? "Sản phẩm TikTok Shop" : "Sản phẩm Shopee";
  const block = { borderRadius: 10 } as const;

  return (
    <Flex vertical gap={12} data-testid="post-blocks">
      <Card
        size="small"
        title="Nội dung đăng"
        extra={copyButton("Copy caption + hashtag", video.post_text, "caption + hashtag")}
        style={block}
        data-post-block="caption"
      >
        <Flex vertical gap={4}>
          {video.hand_written && (
            <Alert
              type="warning"
              showIcon
              data-testid="hand-written-review"
              style={{ marginBottom: 8 }}
              title="Video tự viết nên chưa được AI rà soát an toàn. Hãy tự kiểm tra nội dung theo luật an toàn của kênh trước khi đăng."
            />
          )}
          <AutoSaveField
            label="Caption"
            value={video.caption}
            multiline
            rows={3}
            save={(caption) => patch({ caption })}
          />
          <Warnings messages={warningsFor("caption")} />
        </Flex>
      </Card>
      <Card
        size="small"
        title="Bình luận"
        extra={copyButton("Copy ghim", video.pinned_comment, "bình luận ghim")}
        style={block}
        data-post-block="comments"
      >
        <Flex vertical gap={4}>
          <AutoSaveField
            label="Bình luận ghim"
            value={video.pinned_comment}
            multiline
            save={(pinned_comment) => patch({ pinned_comment })}
          />
          <Warnings messages={warningsFor("pinned_comment")} />
          <ExtraComments video={video} />
          {video.platform === "facebook" && <CommentPosting video={video} />}
        </Flex>
      </Card>
      <Card
        size="small"
        title={
          <span>
            {shop}{" "}
            {products ? (
              <StatusText tone="success">{products} sản phẩm</StatusText>
            ) : (
              <StatusText tone="warning">chưa gắn</StatusText>
            )}
          </span>
        }
        style={block}
        data-post-block="products"
      >
        <Flex vertical gap={4}>
          <AutoSaveField
            label="Gợi ý sản phẩm (AI)"
            value={video.affiliates.join("\n")}
            multiline
            hint={
              video.platform === "tiktok"
                ? "Từ khoá để tìm sản phẩm trong mục “Thêm sản phẩm” của app TikTok; mỗi dòng một sản phẩm"
                : "Từ khoá app dùng để tìm sản phẩm trên Shopee; mỗi dòng một sản phẩm"
            }
            save={(text) => patch({ affiliates: lines(text) })}
          />
          {video.platform === "facebook" && <VideoSuggestions video={video} />}
          <AttachedProducts video={video} />
        </Flex>
      </Card>
      {/* Last, a block of its own: the label and the field. */}
      <div
        data-testid="hashtag-block"
        style={{ border: "1px solid #e7e5e2", borderRadius: 10, padding: 12, background: "#fff" }}
      >
        <AutoSaveField
          label="Hashtag"
          value={video.hashtags.join(" ")}
          placeholder="#xuongkhop #duongsinh"
          save={(text) => patch({ hashtags: words(text) })}
        />
      </div>
    </Flex>
  );
}

/** "Đăng bình luận": where the comment under the newest open post stands, with "Bình luận ngay" once it is live. */
function CommentPosting({ video }: { video: VideoDetail }) {
  const { onSaved } = useEditor();
  const reload = useCallback(() => {
    api<VideoDetail>(`/videos/${video.id}`).then(onSaved, () => undefined);
  }, [video.id, onSaved]);
  const post = video.publications.find((row) => row.status === "published" || row.status === "scheduled");
  return (
    <>
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        ↓ đăng khi bài lên
      </Typography.Text>
      <Flex vertical gap={2} style={{ padding: "6px 8px", background: "rgba(0,0,0,0.03)", borderRadius: 8 }}>
        <Typography.Text strong>Đăng bình luận</Typography.Text>
        {post ? (
          <PostComment post={post} onChanged={reload} />
        ) : (
          <Typography.Text type="secondary" style={{ fontSize: 13 }}>
            Chưa có bài: bình luận tự đăng khi bài lên, nếu bật “Tự bình luận” lúc đăng.
          </Typography.Text>
        )}
      </Flex>
    </>
  );
}

/** The video's Shopee suggestions: the shared block, refreshing the video once something changed. */
function VideoSuggestions({ video }: { video: VideoDetail }) {
  const { onSaved } = useEditor();
  const refresh = useCallback(async () => {
    onSaved(await api<VideoDetail>(`/videos/${video.id}`));
  }, [onSaved, video.id]);
  return (
    <ShopeeSuggestions
      base={`/affiliate-products/videos/${video.id}`}
      ideas={video.affiliates}
      state={video.suggest.state}
      searchedAt={video.suggest.at}
      attachedIds={video.affiliate_product_ids}
      onChanged={refresh}
    />
  );
}

function Warnings({ messages }: { messages: string[] }) {
  return messages.map((text) => <Alert key={text} type="warning" showIcon title={text} style={{ marginBottom: 8 }} />);
}

/** The approved products attached to the video: on Facebook their links go in the comment the worker writes under
 * the reel, after the pinned comment; on TikTok they are the cart a member adds in TikTok's app. Chosen before
 * posting so the first comment already holds them; a change edits a comment already written. */
function AttachedProducts({ video }: { video: VideoDetail }) {
  const { message } = App.useApp();
  const { onSaved } = useEditor();
  const [products, setProducts] = useState<AffiliateProduct[] | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let live = true;
    const platform = video.platform === "tiktok" ? "tiktok_shop" : "shopee";
    api<AffiliateProduct[]>(`/affiliate-products?status=approved&platform=${platform}`).then(
      (found) => live && setProducts(found),
      () => live && setProducts([]),
    );
    return () => {
      live = false;
    };
  }, [video.platform, video.affiliate_product_ids]);

  async function save(ids: number[]) {
    setSaving(true);
    try {
      await api(`/affiliate-products/videos/${video.id}`, "PUT", { product_ids: ids });
      onSaved(await api<VideoDetail>(`/videos/${video.id}`));
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  const usable = (products ?? []).filter((product) => product.problems.length === 0);
  const label = video.platform === "tiktok" ? "Sản phẩm TikTok Shop gắn giỏ" : "Sản phẩm Shopee trong bình luận";
  return (
    <Flex vertical gap={4} style={{ marginBottom: 12 }}>
      <Typography.Text strong>{label}</Typography.Text>
      <Select
        mode="multiple"
        aria-label={label}
        placeholder="Chọn sản phẩm đã duyệt"
        loading={products === null || saving}
        value={video.affiliate_product_ids}
        onChange={save}
        optionFilterProp="label"
        options={usable.map((product) => ({ value: product.id, label: product.name }))}
        notFoundContent={
          <Typography.Text type="secondary">
            Chưa có sản phẩm đã duyệt. Thêm ở <Link href="/affiliate">Affiliate</Link>.
          </Typography.Text>
        }
      />
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        {video.platform === "tiktok"
          ? "Gắn giỏ các sản phẩm này trong app TikTok khi đăng; TikTok không có bình luận chứa link."
          : "Link các sản phẩm này đi sau bình luận ghim, trong bình luận app tự viết dưới reel. Fanpage gắn tài khoản Shopee dùng link riêng của tài khoản đó."}
      </Typography.Text>
    </Flex>
  );
}
