"use client";

import { DeleteOutlined, PlusOutlined } from "@ant-design/icons";
import { App, Button, Flex, Input, Tooltip, Typography } from "antd";
import { useState } from "react";
import { api, errorMessage, type VideoDetail } from "@/lib/api";
import AutoSaveField, { useEditor } from "./AutoSaveField";

/** At most this many (api routes_videos.MAX_EXTRA_COMMENTS). */
const MAX = 5;

/** "Bình luận thêm" under "Bình luận ghim": more comments the Page writes under each reel after the first, in order,
 * when the post's comment is written (post_comments.py). Each saved line is edited in place; "Thêm bình luận" adds
 * one at the end. */
export default function ExtraComments({ video }: { video: VideoDetail }) {
  const { message } = App.useApp();
  const { onSaved, locked } = useEditor();
  const [draft, setDraft] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const comments = video.extra_comments;

  const save = (next: string[]) =>
    api<VideoDetail>(`/videos/${video.id}`, "PATCH", { extra_comments: next.filter((text) => text.trim()) });

  async function change(next: string[]) {
    setBusy(true);
    try {
      onSaved(await save(next));
      return true;
    } catch (err) {
      message.error(errorMessage(err));
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function add() {
    if (!draft?.trim()) return;
    if (await change([...comments, draft.trim()])) setDraft(null);
  }

  return (
    <Flex vertical gap={4} data-testid="extra-comments">
      <Typography.Text strong>Bình luận thêm</Typography.Text>
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        Page tự bình luận thêm các câu này dưới reel, theo thứ tự, ngay sau bình luận ghim (khi bài được tự bình luận
        hoặc bấm “Bình luận ngay”). Facebook không cho app gắn thẻ @ người theo dõi, nên @tên chỉ là chữ thường.
      </Typography.Text>
      {comments.map((text, index) => (
        <Flex key={`${index}-${comments.length}`} gap={4} align="flex-start">
          <div style={{ flex: 1, minWidth: 0 }}>
            <AutoSaveField
              label={`Bình luận ${index + 2}`}
              value={text}
              multiline
              save={(next) => save(comments.map((old, place) => (place === index ? next : old)))}
            />
          </div>
          <Tooltip title="Bỏ bình luận này">
            <Button
              type="text"
              size="small"
              danger
              icon={<DeleteOutlined />}
              aria-label={`Bỏ bình luận ${index + 2}`}
              disabled={busy || locked}
              style={{ marginTop: 26 }}
              onClick={() => void change(comments.filter((_, place) => place !== index))}
            />
          </Tooltip>
        </Flex>
      ))}
      {draft !== null ? (
        <Flex vertical gap={6} style={{ marginBottom: 8 }}>
          <Input.TextArea
            aria-label="Bình luận mới"
            autoFocus
            autoSize={{ minRows: 2, maxRows: 6 }}
            maxLength={5000}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
          />
          <Flex gap={8}>
            <Button type="primary" size="small" loading={busy} disabled={!draft.trim()} onClick={() => void add()}>
              Lưu bình luận
            </Button>
            <Button size="small" onClick={() => setDraft(null)}>
              Huỷ
            </Button>
          </Flex>
        </Flex>
      ) : (
        <Button
          icon={<PlusOutlined />}
          size="small"
          disabled={comments.length >= MAX || locked}
          style={{ alignSelf: "flex-start", marginBottom: 8 }}
          onClick={() => setDraft("")}
        >
          {comments.length >= MAX ? `Tối đa ${MAX} bình luận thêm` : "Thêm bình luận"}
        </Button>
      )}
    </Flex>
  );
}
