"use client";

import { FileTextOutlined } from "@ant-design/icons";
import { Flex } from "antd";
import type { Article } from "@/lib/api";

/** The article's picture, small; a text post shows a page icon. */
export default function ArticleThumb({ article, size = 56 }: { article: Article; size?: number }) {
  if (!article.has_image) {
    return (
      <Flex
        align="center"
        justify="center"
        style={{ width: size, height: size, borderRadius: 6, background: "var(--ant-color-fill-tertiary)" }}
        aria-label="Bài chỉ chữ"
      >
        <FileTextOutlined style={{ fontSize: size / 2.6, color: "var(--ant-color-text-tertiary)" }} />
      </Flex>
    );
  }
  return (
    // eslint-disable-next-line @next/next/no-img-element -- a private file behind the login, not an optimisable asset
    <img
      src={`/api/articles/${article.id}/image?v=${article.image_version}`}
      alt=""
      width={size}
      height={size}
      style={{ objectFit: "cover", borderRadius: 6, display: "block" }}
    />
  );
}
