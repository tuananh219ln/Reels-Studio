"use client";

import { GoogleOutlined, LinkOutlined, SnippetsOutlined, TikTokOutlined } from "@ant-design/icons";
import { App, Button, Flex, Input, Typography } from "antd";
import { useState, type ClipboardEvent, type DragEvent } from "react";
import { api, errorMessage, upload, type MediaItem, type MediaLinksResult } from "@/lib/api";
import {
  fileFromDataUrl,
  googleImagesUrl,
  googleTransparentUrl,
  linkFromTransfer,
  tiktokSearchUrl,
  unwrapLink,
} from "@/lib/mediaLinks";

const MEDIA_TYPES = /^(image\/(jpeg|png|webp)|video\/(mp4|quicktime|webm))$/;

/**
 * Find a product's photos and clips on Google Ảnh and TikTok, then bring them back: the buttons open the search for
 * the product being worked on, and what is pasted or dropped in the box goes straight into the library, in the
 * product's folder. That may be a link (a photo's address, a TikTok video: the api downloads it), a photo copied with
 * "Sao chép hình ảnh", or a "data:" address (Google Ảnh's thumbnails), the last two uploaded like a chosen file.
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

  function done(added: MediaItem[]) {
    if (!added.length) return;
    message.success(`Đã thêm ${added.length} tư liệu vào “${folder || "Kho tư liệu"}”`);
    onAdded(added);
    setLinks("");
  }

  /** Photos or clips themselves (a copied photo, dropped files, a data: address): uploaded one by one. */
  async function addFiles(files: File[]) {
    const added: MediaItem[] = [];
    for (const file of files) {
      try {
        added.push(await upload<MediaItem>("/media", file, { folder }));
      } catch (err) {
        message.error(`${file.name}: ${errorMessage(err)}`);
      }
    }
    done(added);
  }

  /** Links typed or pasted, one or many: data: photos are uploaded, web addresses downloaded by the api. */
  async function addText(text: string) {
    const parts = text
      .split(/\s+/)
      .map((link) => unwrapLink(link.trim()))
      .filter(Boolean);
    const urls = parts.filter((link) => /^https?:\/\//i.test(link));
    const inline = parts.filter((link) => /^data:image\//i.test(link));
    if (!urls.length && !inline.length) {
      message.warning("Hãy dán ảnh, link ảnh hoặc link video TikTok");
      return;
    }
    setAdding(true);
    try {
      if (inline.length) await addFiles(await Promise.all(inline.map(fileFromDataUrl)));
      if (urls.length) {
        const result = await api<MediaLinksResult>("/media/links", "POST", { urls: urls.slice(0, 10), folder });
        done(result.added);
        for (const failure of result.failed) {
          message.error(`${failure.error} (${failure.url.slice(0, 60)})`);
        }
      }
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setAdding(false);
    }
  }

  /** What a paste or a drop holds, best first: files, then the photo in copied HTML, then plain text. */
  async function take(data: DataTransfer): Promise<boolean> {
    const files = Array.from(data.files).filter((file) => MEDIA_TYPES.test(file.type));
    if (files.length) {
      setAdding(true);
      try {
        await addFiles(files);
      } finally {
        setAdding(false);
      }
      return true;
    }
    const link = linkFromTransfer(data);
    const text = data.getData("text/plain").trim();
    if (link || text) {
      await addText(link && !/\s/.test(text) ? link : text || link || "");
      return true;
    }
    return false;
  }

  /** "Dán ảnh / link": one click reads the clipboard (the browser asks once), a photo first, then a link. */
  async function fromClipboard() {
    try {
      const items = await navigator.clipboard.read();
      const files: File[] = [];
      for (const item of items) {
        const type = item.types.find((name) => MEDIA_TYPES.test(name));
        if (type) {
          const blob = await item.getType(type);
          files.push(new File([blob], `anh-dan.${type.split("/")[1].replace("jpeg", "jpg")}`, { type }));
        }
      }
      if (files.length) {
        setAdding(true);
        try {
          await addFiles(files);
        } finally {
          setAdding(false);
        }
        return;
      }
      const text = (await navigator.clipboard.readText()).trim();
      if (text) return addText(text);
      message.warning("Clipboard chưa có ảnh hay link: chuột phải vào ảnh › Sao chép hình ảnh, rồi bấm lại");
    } catch {
      message.info(
        "Trình duyệt chưa cho đọc clipboard: bấm “Cho phép” khi được hỏi, hoặc bấm vào ô bên dưới rồi nhấn Ctrl+V",
      );
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
        <Button type="primary" icon={<SnippetsOutlined />} loading={adding} onClick={fromClipboard}>
          Dán ảnh / link
        </Button>
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
        aria-label="Dán ảnh, link ảnh hoặc video"
        value={links}
        disabled={adding}
        autoSize={{ minRows: 2, maxRows: 4 }}
        placeholder="Dán vào đây (Ctrl+V): ảnh đã sao chép (chuột phải › Sao chép hình ảnh), link ảnh, hoặc link video TikTok. Kéo ảnh từ tab khác thả vào cũng được."
        onChange={(event) => setLinks(event.target.value)}
        onPaste={(event: ClipboardEvent<HTMLTextAreaElement>) => {
          // Pasting is the whole gesture: what was pasted is added at once, no button to find.
          const data = event.clipboardData;
          if (data.files.length || data.getData("text/plain").trim() || data.getData("text/html")) {
            event.preventDefault();
            void take(data);
          }
        }}
        onDragOver={(event: DragEvent<HTMLTextAreaElement>) => event.preventDefault()}
        onDrop={(event: DragEvent<HTMLTextAreaElement>) => {
          event.preventDefault();
          void take(event.dataTransfer);
        }}
      />
      <Flex gap={8} align="center" wrap>
        <Button icon={<LinkOutlined />} disabled={adding || !links.trim()} onClick={() => addText(links)}>
          Thêm link đã gõ
        </Button>
        <Typography.Text type="secondary">
          Vào thư mục <strong>{folder || "(không thư mục)"}</strong>. Người thêm chịu trách nhiệm bản quyền.
        </Typography.Text>
      </Flex>
    </Flex>
  );
}
