"use client";

import VideoThumbnail from "@/components/VideoThumbnail";
import {
  api,
  errorMessage,
  fromVietnamInput,
  vietnamInputValue,
  type BoardPlatform,
  type LinkPreview,
  type LinkVideo,
  type VideoRow,
} from "@/lib/api";
import { App, Flex, Input, Modal, Select, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useEffect, useRef, useState } from "react";
import { PLATFORM_LABEL } from "./boardText";

/** Opened from a cell: the video and platform are fixed, the links are only checked against them. */
export type PasteTarget = { videoId: number; platform: BoardPlatform; videoName: string };

/** `edited`: the member typed the time, so a reading never replaces it with the platform's. */
type Choice = { videoId: number | null; channelId: number | null; publishedAt: string; edited: boolean };

const RESULT_COLOR: Record<LinkPreview["result"], string> = {
  matched: "green",
  choose: "gold",
  unknown_channel: "red",
  invalid: "red",
  unreachable: "red",
  duplicate: "red",
};

function short(url: string): string {
  return url.replace(/^https?:\/\/(www\.)?/, "").slice(0, 48);
}

/** "Dán link bài đã đăng": 1–50 links, read and matched as they are pasted, then saved together. */
export default function PasteLinksModal({
  target,
  onClose,
  onSaved,
}: {
  target: PasteTarget | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { message } = App.useApp();
  const [text, setText] = useState("");
  const [rows, setRows] = useState<LinkPreview[]>([]);
  const [choices, setChoices] = useState<Record<number, Choice>>({});
  const [reading, setReading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [videos, setVideos] = useState<{ value: number; label: string }[]>([]);
  const asked = useRef(0);

  useEffect(() => {
    // Every video, for picking one by hand; read once per opening.
    api<VideoRow[]>("/videos").then(
      (list) => setVideos(list.map((video) => ({ value: video.id, label: video.name || video.title || video.topic }))),
      () => setVideos([]),
    );
  }, []);

  // Read after a pause in typing (400 ms) or at once on a paste.
  useEffect(() => {
    const urls = text
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean);
    if (urls.length === 0) {
      asked.current += 1;
      return;
    }
    const ask = ++asked.current;
    const timer = setTimeout(async () => {
      setReading(true);
      try {
        const result = await api<{ items: LinkPreview[] }>("/posts/links/preview", "POST", {
          urls,
          video_id: target?.videoId ?? null,
          platform: target?.platform ?? null,
        });
        if (ask !== asked.current) return;
        setRows(result.items);
        setChoices(
          Object.fromEntries(
            result.items.map((row, index) => [
              index,
              {
                videoId: row.video?.id ?? null,
                channelId: row.channel?.id ?? null,
                publishedAt: row.published_at,
                edited: false,
              },
            ]),
          ),
        );
      } catch (err) {
        if (ask === asked.current) message.error(errorMessage(err));
      } finally {
        setReading(false);
      }
    }, 400);
    return () => clearTimeout(timer);
  }, [text, target, message]);

  // Lines cleared: nothing left to show or save, whatever the last answer said.
  const shown = text.trim() ? rows : [];
  const savable = shown
    .map((row, index) => ({ row, choice: choices[index] }))
    .filter(
      ({ row, choice }) =>
        (row.result === "matched" || row.result === "choose") && choice?.videoId != null && choice?.channelId != null,
    );

  function choose(index: number, change: Partial<Choice>) {
    setChoices((current) => ({ ...current, [index]: { ...current[index], ...change } }));
  }

  async function save() {
    setSaving(true);
    try {
      const result = await api<{ saved: number }>("/posts/links", "POST", {
        items: savable.map(({ row, choice }) => ({
          url: row.url,
          video_id: choice.videoId,
          channel_id: choice.channelId,
          published_at: choice.publishedAt,
          published_at_edited: choice.edited,
        })),
      });
      message.success(`Đã lưu ${result.saved} link`);
      onSaved();
      onClose();
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  const columns: ColumnsType<LinkPreview> = [
    {
      title: "Link",
      key: "link",
      width: 200,
      render: (_, row) => (
        <Typography.Text style={{ fontSize: 12 }} ellipsis={{ tooltip: row.url ?? row.input }}>
          {short(row.url ?? row.input)}
        </Typography.Text>
      ),
    },
    {
      title: "Nền tảng · Kênh",
      key: "channel",
      width: 200,
      render: (_, row, index) => {
        if (!row.platform) return "—";
        const platform = PLATFORM_LABEL[row.platform];
        if (row.channel_options.length > 1) {
          return (
            <Flex vertical gap={2}>
              <span>{platform}</span>
              <Select
                size="small"
                aria-label="Chọn Page"
                placeholder="Chọn Page"
                value={choices[index]?.channelId ?? undefined}
                onChange={(value) => choose(index, { channelId: value })}
                options={row.channel_options.map((option) => ({ value: option.id, label: option.name }))}
                style={{ width: 180 }}
              />
            </Flex>
          );
        }
        return `${platform}${row.channel ? ` · ${row.channel.name}` : ""}`;
      },
    },
    {
      title: "Khớp với video",
      key: "video",
      width: 280,
      render: (_, row, index) => {
        if (row.result === "duplicate" && row.existing_video) {
          return <Typography.Text type="secondary">Đang gắn: {row.existing_video.name}</Typography.Text>;
        }
        if (row.result !== "matched" && row.result !== "choose") return null;
        if (target) return target.videoName;
        const suggested = row.suggestions.map((video: LinkVideo) => ({
          value: video.id,
          label: `${video.name} (${video.score ?? 0}%)`,
        }));
        const others = videos.filter((option) => !suggested.some((item) => item.value === option.value));
        const chosen = row.video;
        return (
          <Flex gap={8} align="center">
            {chosen && <VideoThumbnail name={chosen.name} url={chosen.thumbnail_url} width={24} />}
            <Select
              size="small"
              showSearch
              aria-label="Chọn video"
              placeholder="Tìm video theo tiêu đề"
              optionFilterProp="label"
              value={choices[index]?.videoId ?? undefined}
              onChange={(value) => choose(index, { videoId: value })}
              options={[
                ...(suggested.length ? [{ label: "Gợi ý", options: suggested }] : []),
                { label: "Mọi video", options: others },
              ]}
              style={{ width: 240 }}
            />
          </Flex>
        );
      },
    },
    {
      title: "Giờ đăng",
      key: "at",
      width: 190,
      render: (_, row, index) =>
        row.result === "matched" || row.result === "choose" ? (
          <Input
            size="small"
            type="datetime-local"
            aria-label="Giờ đăng"
            value={choices[index] ? vietnamInputValue(choices[index].publishedAt) : ""}
            onChange={(event) =>
              event.target.value && choose(index, { publishedAt: fromVietnamInput(event.target.value), edited: true })
            }
          />
        ) : null,
    },
    {
      title: "Kết quả",
      key: "result",
      width: 170,
      render: (_, row) => (
        <Flex vertical gap={2} align="flex-start">
          <Tag color={RESULT_COLOR[row.result]} style={{ marginInlineEnd: 0 }}>
            {row.result === "matched" ? "✓ " : row.result === "choose" ? "? " : "✕ "}
            {row.message}
          </Tag>
          {row.result === "unknown_channel" && row.platform !== "facebook" && (
            <a href="/fanpages" target="_blank" rel="noreferrer" style={{ fontSize: 12 }}>
              Thêm kênh
            </a>
          )}
        </Flex>
      ),
    },
  ];

  return (
    <Modal
      open
      title="Dán link bài đã đăng"
      width={1100}
      onCancel={onClose}
      okText={`Lưu ${savable.length} link`}
      cancelText="Hủy"
      okButtonProps={{ disabled: savable.length === 0, loading: saving }}
      onOk={save}
      destroyOnHidden
    >
      <Flex vertical gap={12}>
        {target && (
          <Typography.Text type="secondary">
            Video: <b>{target.videoName}</b> · {PLATFORM_LABEL[target.platform]}
          </Typography.Text>
        )}
        <Input.TextArea
          aria-label="Link bài đã đăng"
          placeholder={
            "Dán 1–50 link, mỗi dòng một link\nhttps://www.tiktok.com/@kenh/video/…\nhttps://youtube.com/shorts/…"
          }
          autoSize={{ minRows: 3, maxRows: 8 }}
          value={text}
          onChange={(event) => setText(event.target.value)}
        />
        {(shown.length > 0 || reading) && (
          <Table<LinkPreview>
            rowKey={(_, index) => String(index)}
            size="small"
            loading={reading}
            columns={columns}
            dataSource={shown}
            pagination={false}
            scroll={{ x: "max-content" }}
          />
        )}
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          Bài Facebook được đọc view ngay sau khi lưu. View TikTok và YouTube sẽ tự cập nhật ở bản sau; giờ đăng mặc
          định là lúc dán, sửa được trước khi lưu.
        </Typography.Text>
      </Flex>
    </Modal>
  );
}
