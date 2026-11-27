"use client";

import { App, Button, Flex, Input, Modal, Popconfirm, Typography } from "antd";
import { useState } from "react";
import { COLORS } from "@/app/theme";
import { api, errorMessage, formatDateTime, type VideoDetail } from "@/lib/api";
import { useEditor } from "./AutoSaveField";

const MAX_NOTE = 1000;

/**
 * "Claim YouTube" under the platform rows (docs/decisions/2026-11-26-youtube-claimed-music.md): the app cannot read
 * Content ID, so a claim found in YouTube Studio is noted here by hand and the YouTube row shows "Bị chặn" until it is
 * cleared with "Đã xử lý claim". Shown once the video has a YouTube post, or while a claim is noted.
 */
export default function YouTubeClaimLine({ video }: { video: VideoDetail }) {
  const { message } = App.useApp();
  const editor = useEditor();
  const [noting, setNoting] = useState(false);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const claim = video.youtube_claim?.active ?? null;
  const onYouTube = video.manual_posts.some((post) => post.platform === "youtube" && post.status !== "pending");
  if (!claim && !onYouTube) return null;

  async function send(path: string, body: { note: string }) {
    setBusy(true);
    try {
      editor.onSaved(await api<VideoDetail>(`/youtube/videos/${video.id}/${path}`, "POST", body));
      setNoting(false);
      setNote("");
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ fontSize: 13, lineHeight: "18px" }} data-testid="youtube-claim">
      {claim ? (
        <Flex vertical gap={4}>
          <span>
            <span style={{ color: COLORS.danger, fontWeight: 600 }}>Claim YouTube: </span>
            <span style={{ whiteSpace: "pre-wrap" }}>{claim.note}</span>
          </span>
          <Flex wrap align="center" gap="0 8px" style={{ color: COLORS.textSecondary }}>
            <span>
              Ghi {claim.by ? `bởi ${claim.by}, ` : ""}
              {formatDateTime(claim.at)}
            </span>
            <Popconfirm
              title="Claim đã xử lý xong?"
              description="Ví dụ: đã xoá bài hát trong YouTube Studio, kháng nghị thắng, hoặc đã thay video."
              okText="Đã xử lý"
              cancelText="Không"
              onConfirm={() => void send("claim/clear", { note: "" })}
            >
              <Button type="link" size="small" loading={busy} style={{ padding: 0, height: "auto", fontSize: 13 }}>
                Đã xử lý claim
              </Button>
            </Popconfirm>
          </Flex>
        </Flex>
      ) : (
        <Typography.Text type="secondary" style={{ fontSize: 13 }}>
          YouTube Studio báo claim Content ID?{" "}
          <Button
            type="link"
            size="small"
            onClick={() => setNoting(true)}
            style={{ padding: 0, height: "auto", fontSize: 13 }}
          >
            Ghi claim YouTube
          </Button>
        </Typography.Text>
      )}
      <Modal
        title="Ghi claim YouTube"
        open={noting}
        okText="Ghi claim"
        cancelText="Huỷ"
        confirmLoading={busy}
        okButtonProps={{ disabled: !note.trim() }}
        onOk={() => void send("claim", { note })}
        onCancel={() => setNoting(false)}
        destroyOnHidden
      >
        <Flex vertical gap={8}>
          <Typography.Text type="secondary">
            Chỉ ghi lại trong app, không gửi gì lên YouTube. Hàng YouTube của video sẽ hiện “Bị chặn” tới khi bấm “Đã xử
            lý claim”. Nhạc bị claim thì đánh dấu thêm bài đó ở Thư viện nhạc để không video nào chọn lại.
          </Typography.Text>
          <Input.TextArea
            aria-label="Ghi chú claim"
            value={note}
            maxLength={MAX_NOTE}
            autoSize={{ minRows: 3, maxRows: 6 }}
            placeholder="Bài/nhạc bị claim, ai claim, ngày. Ví dụ: nhạc nền, HAAWK Publishing, chặn toàn cầu 26/11."
            onChange={(event) => setNote(event.target.value)}
          />
        </Flex>
      </Modal>
    </div>
  );
}
