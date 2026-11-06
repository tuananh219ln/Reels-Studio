"use client";

import { GoogleOutlined, LinkOutlined, TikTokOutlined } from "@ant-design/icons";
import { App, Button, Flex, Input, Typography } from "antd";
import { useState } from "react";
import { api, errorMessage, type MediaItem, type MediaLinksResult } from "@/lib/api";
import { googleImagesUrl, googleTransparentUrl, tiktokSearchUrl, unwrapLink } from "@/lib/mediaLinks";

/**
 * Find a product's photos and clips on Google Ảnh and TikTok, then paste the links back: the buttons open the search
 * for the product being worked on, and a link pasted in the box goes straight into the library, in the product's
 * folder (the api downloads it: a photo, or the TikTok video's first minute).
 */
export default function MediaLinkSearch({
  keyword: initial,
  folder,
  onAdded,
}: {
  /** The product's name (or the video's topic): what the buttons search for. */
  keyword: string;
  /** Where pasted links land in the library. */
  folder: string;
  onAdded: (items: MediaItem[]) => void;
}) {
  const { message } = App.useApp();
  const [keyword, setKeyword] = useState(initial);
  const [links, setLinks] = useState("");
  const [adding, setAdding] = useState(false);

  // A new product (or topic) from the page replaces what was typed: the "previous prop" pattern, not an effect.
  const [shownFor, setShownFor] = useState(initial);
  if (shownFor !== initial) {
    setShownFor(initial);
    setKeyword(initial);
  }

  async function add(text: string) {
    const urls = text
      .split(/\s+/)
      .map((link) => unwrapLink(link.trim()))
      .filter((link) => /^https?:\/\//i.test(link));
    if (!urls.length) {
      message.warning("Hãy dán link ảnh hoặc link video TikTok");
      return;
    }
    setAdding(true);
    try {
      const result = await api<MediaLinksResult>("/media/links", "POST", { urls: urls.slice(0, 10), folder });
      if (result.added.length) {
        message.success(`Đã thêm ${result.added.length} tư liệu vào “${folder || "Kho tư liệu"}”`);
        onAdded(result.added);
        setLinks("");
      }
      for (const failure of result.failed) {
        message.error(`${failure.error} (${failure.url.slice(0, 60)})`);
      }
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setAdding(false);
    }
  }

  const open = (url: string) => window.open(url, "_blank", "noopener,noreferrer");
  const term = keyword.trim();

  return (
    <Flex vertical gap={8}>
      <Flex gap={8} wrap align="center">
        <Input
          aria-label="Tên sản phẩm để tìm"
          value={keyword}
          onChange={(event) => setKeyword(event.target.value)}
          placeholder="Tên sản phẩm"
          style={{ flex: "1 1 220px" }}
        />
        <Button icon={<GoogleOutlined />} disabled={!term} onClick={() => open(googleTransparentUrl(term))}>
          Ảnh không nền
        </Button>
        <Button icon={<GoogleOutlined />} disabled={!term} onClick={() => open(googleImagesUrl(term))}>
          Ảnh Google
        </Button>
        <Button icon={<TikTokOutlined />} disabled={!term} onClick={() => open(tiktokSearchUrl(term))}>
          Clip TikTok
        </Button>
      </Flex>
      <Input.TextArea
        aria-label="Dán link ảnh hoặc video"
        value={links}
        disabled={adding}
        autoSize={{ minRows: 1, maxRows: 4 }}
        placeholder="Dán link ảnh (chuột phải › Sao chép địa chỉ hình ảnh) hoặc link video TikTok vào đây"
        onChange={(event) => setLinks(event.target.value)}
        onPaste={(event) => {
          // Pasting is the whole gesture: the link is added at once, no button to find.
          const pasted = event.clipboardData.getData("text");
          if (pasted.trim()) {
            event.preventDefault();
            void add(pasted);
          }
        }}
      />
      <Flex gap={8} align="center" wrap>
        <Button icon={<LinkOutlined />} loading={adding} disabled={!links.trim()} onClick={() => add(links)}>
          Thêm vào kho
        </Button>
        <Typography.Text type="secondary">
          Vào thư mục <strong>{folder || "(không thư mục)"}</strong>. Người dán link chịu trách nhiệm bản quyền.
        </Typography.Text>
      </Flex>
    </Flex>
  );
}
