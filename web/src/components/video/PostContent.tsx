"use client";

import { CopyOutlined } from "@ant-design/icons";
import { App, Alert, Button, Card, Flex, Select, Tabs, Typography } from "antd";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import ShopeeSuggestions from "@/components/affiliate/ShopeeSuggestions";
import StatusText from "@/components/StatusText";
import { api, errorMessage, type AffiliateProduct, type VideoDetail } from "@/lib/api";
import AutoSaveField, { useEditor } from "./AutoSaveField";
import ExtraComments from "./ExtraComments";

type PostFields = Pick<VideoDetail, "caption" | "hashtags" | "affiliates" | "pinned_comment" | "music_suggestions">;

const lines = (text: string) =>
  text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
const words = (text: string) => text.split(/\s+/).filter(Boolean);

/** The tabs of the post texts: the caption and hashtags; the comment with the products whose links go in it; the music
 * and the AI's safety review. */
export type PostTabKey = "caption" | "comments" | "extras";

export default function PostContent({
  video,
  tab,
  onTab,
}: {
  video: VideoDetail;
  tab?: PostTabKey;
  onTab?: (tab: PostTabKey) => void;
}) {
  const { message } = App.useApp();
  const [own, setOwn] = useState<PostTabKey>("caption");
  const active = tab ?? own;
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

  /** A "Copy" in a block's title: it copies without opening or closing the block. */
  const copyButton = (label: string, text: string, what: string) => (
    <Button
      size="small"
      icon={<CopyOutlined />}
      onClick={(event) => {
        event.stopPropagation();
        void copy(text, what);
      }}
    >
      {label}
    </Button>
  );

  const pinnedWarnings = warningsFor("pinned_comment");
  const extraCount = video.extra_comments.length;
  const commentSummary = [
    video.pinned_comment.trim() ? "1 ghim" : "Chưa có bình luận ghim",
    extraCount ? `${extraCount} thêm` : null,
    pinnedWarnings.length ? `${pinnedWarnings.length} cảnh báo` : null,
  ]
    .filter(Boolean)
    .join(", ");
  const products = video.affiliate_product_ids.length;
  const shop = video.platform === "tiktok" ? "Sản phẩm TikTok Shop" : "Sản phẩm Shopee";
  const reviewSummary = video.hand_written
    ? "Chưa rà soát (kịch bản tự viết)"
    : video.self_review.length
      ? `${video.self_review.length} điểm đã sửa`
      : "Không có câu nào phải sửa";
  // A tab's name with, small beside it, what is in it: the member sees what is there without opening it.
  const tabLabel = (title: string, summary: React.ReactNode) => (
    <span>
      {title}{" "}
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        {summary}
      </Typography.Text>
    </span>
  );

  // Each tab keeps its fields mounted, so text not yet saved survives a change of tab.
  return (
    <Card size="small" styles={{ body: { paddingTop: 0 } }} data-testid="post-blocks">
      <Tabs
        size="small"
        activeKey={active}
        onChange={(key) => {
          setOwn(key as PostTabKey);
          onTab?.(key as PostTabKey);
        }}
        tabBarExtraContent={
          active === "caption"
            ? copyButton("Copy caption + hashtag", video.post_text, "caption + hashtag")
            : active === "comments"
              ? copyButton("Copy ghim", video.pinned_comment, "bình luận ghim")
              : copyButton("Copy nhạc", video.music_suggestions.join("\n"), "gợi ý nhạc")
        }
        items={[
          {
            key: "caption",
            forceRender: true,
            label: "Caption & hashtag",
            children: (
              <Flex vertical gap={4}>
                <AutoSaveField
                  label="Caption"
                  value={video.caption}
                  multiline
                  rows={3}
                  save={(caption) => patch({ caption })}
                />
                <Warnings messages={warningsFor("caption")} />
                <AutoSaveField
                  label="Hashtag"
                  value={video.hashtags.join(" ")}
                  placeholder="#xuongkhop #duongsinh"
                  save={(text) => patch({ hashtags: words(text) })}
                />
              </Flex>
            ),
          },
          {
            key: "comments",
            forceRender: true,
            label: tabLabel(
              "Bình luận & sản phẩm",
              <>
                {commentSummary}, {shop.replace("Sản phẩm ", "")}:{" "}
                {products ? (
                  <StatusText tone="success">đã gắn {products}</StatusText>
                ) : (
                  <StatusText tone="warning">chưa gắn</StatusText>
                )}
              </>,
            ),
            // In the order it happens: the products, whose links go into the pinned comment, then the comments.
            children: (
              <Flex vertical gap={4}>
                <Typography.Text strong>{shop}</Typography.Text>
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
                <Typography.Text strong>Bình luận</Typography.Text>
                <AutoSaveField
                  label="Bình luận ghim"
                  value={video.pinned_comment}
                  multiline
                  save={(pinned_comment) => patch({ pinned_comment })}
                />
                <Warnings messages={pinnedWarnings} />
                <ExtraComments video={video} />
              </Flex>
            ),
          },
          {
            key: "extras",
            forceRender: true,
            label: tabLabel("Nhạc & an toàn", `${video.music_suggestions.length || "chưa có"} nhạc, ${reviewSummary}`),
            children: (
              <Flex vertical gap={8}>
                <AutoSaveField
                  label="Gợi ý nhạc"
                  value={video.music_suggestions.join("\n")}
                  multiline
                  hint="Tìm tên nhạc này trong TikTok hoặc Facebook khi đăng; mỗi dòng một bản"
                  save={(text) => patch({ music_suggestions: lines(text) })}
                />
                <Typography.Text strong>Rà soát an toàn của AI</Typography.Text>
                {video.hand_written ? (
                  <Alert
                    type="warning"
                    showIcon
                    data-testid="hand-written-review"
                    title="Video tự viết nên chưa được AI rà soát an toàn. Hãy tự kiểm tra nội dung theo luật an toàn của kênh trước khi đăng."
                  />
                ) : video.self_review.length ? (
                  <ul style={{ margin: 0, paddingLeft: 20 }} data-testid="self-review">
                    {video.self_review.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                ) : (
                  <Typography.Text type="secondary">Không có câu nào phải sửa</Typography.Text>
                )}
              </Flex>
            ),
          },
        ]}
      />
    </Card>
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
