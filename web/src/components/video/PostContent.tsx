"use client";

import { CopyOutlined } from "@ant-design/icons";
import { App, Alert, Button, Card, Flex, Select, Typography } from "antd";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, errorMessage, type AffiliateProduct, type VideoDetail } from "@/lib/api";
import AutoSaveField, { useEditor } from "./AutoSaveField";

type PostFields = Pick<VideoDetail, "caption" | "hashtags" | "affiliates" | "pinned_comment" | "music_suggestions">;

const lines = (text: string) =>
  text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
const words = (text: string) => text.split(/\s+/).filter(Boolean);

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

  return (
    <Card title="Nội dung đăng" size="small">
      <Flex vertical gap={4}>
        <AutoSaveField
          label="Caption"
          value={video.caption}
          multiline
          rows={5}
          save={(caption) => patch({ caption })}
        />
        <Warnings messages={warningsFor("caption")} />
        <AutoSaveField
          label="Hashtag"
          value={video.hashtags.join(" ")}
          placeholder="#xuongkhop #duongsinh"
          save={(text) => patch({ hashtags: words(text) })}
        />
        <AutoSaveField
          label="Gợi ý sản phẩm (AI)"
          value={video.affiliates.join("\n")}
          multiline
          hint="Gợi ý để tìm sản phẩm trên Shopee; mỗi dòng một sản phẩm"
          save={(text) => patch({ affiliates: lines(text) })}
        />
        <ShopeeProducts video={video} />
        <AutoSaveField
          label="Bình luận ghim"
          value={video.pinned_comment}
          multiline
          save={(pinned_comment) => patch({ pinned_comment })}
        />
        <Warnings messages={warningsFor("pinned_comment")} />
        <AutoSaveField
          label="Gợi ý nhạc"
          value={video.music_suggestions.join("\n")}
          multiline
          hint="Tìm tên nhạc này trong TikTok hoặc Facebook khi đăng; mỗi dòng một bản"
          save={(text) => patch({ music_suggestions: lines(text) })}
        />
        <Flex wrap gap={8} style={{ marginBottom: 12 }}>
          <Button icon={<CopyOutlined />} onClick={() => copy(video.post_text, "caption + hashtag")}>
            Copy caption + hashtag
          </Button>
          <Button icon={<CopyOutlined />} onClick={() => copy(video.pinned_comment, "bình luận ghim")}>
            Copy bình luận ghim
          </Button>
          <Button icon={<CopyOutlined />} onClick={() => copy(video.music_suggestions.join("\n"), "gợi ý nhạc")}>
            Copy gợi ý nhạc
          </Button>
        </Flex>
        <Typography.Text strong>Tự rà soát an toàn của AI</Typography.Text>
        {video.self_review.length ? (
          <ul style={{ margin: "4px 0 0", paddingLeft: 20 }} data-testid="self-review">
            {video.self_review.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        ) : (
          <Typography.Text type="secondary">Không có câu nào phải sửa</Typography.Text>
        )}
      </Flex>
    </Card>
  );
}

function Warnings({ messages }: { messages: string[] }) {
  return messages.map((text) => <Alert key={text} type="warning" showIcon title={text} style={{ marginBottom: 8 }} />);
}

/** The approved Shopee products whose links go in the comment the worker writes under the reel, after the pinned
 * comment. Chosen before posting so the first comment already holds them; a change edits a comment already written. */
function ShopeeProducts({ video }: { video: VideoDetail }) {
  const { message } = App.useApp();
  const { onSaved } = useEditor();
  const [products, setProducts] = useState<AffiliateProduct[] | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let live = true;
    api<AffiliateProduct[]>("/affiliate-products?status=approved").then(
      (found) => live && setProducts(found),
      () => live && setProducts([]),
    );
    return () => {
      live = false;
    };
  }, []);

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
  return (
    <Flex vertical gap={4} style={{ marginBottom: 12 }}>
      <Typography.Text strong>Sản phẩm Shopee trong bình luận</Typography.Text>
      <Select
        mode="multiple"
        aria-label="Sản phẩm Shopee trong bình luận"
        placeholder="Chọn sản phẩm đã duyệt"
        loading={products === null || saving}
        value={video.affiliate_product_ids}
        onChange={save}
        optionFilterProp="label"
        options={usable.map((product) => ({ value: product.id, label: product.name }))}
        notFoundContent={
          <Typography.Text type="secondary">
            Chưa có sản phẩm đã duyệt. Thêm ở <Link href="/affiliate">Affiliate Shopee</Link>.
          </Typography.Text>
        }
      />
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        Link các sản phẩm này đi sau bình luận ghim, trong bình luận app tự viết dưới reel.
      </Typography.Text>
    </Flex>
  );
}
