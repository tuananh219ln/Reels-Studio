"use client";

import { CopyOutlined, DeleteOutlined, DownloadOutlined } from "@ant-design/icons";
import { App, Button, Flex, Input, Popconfirm, Typography } from "antd";
import { useState } from "react";
import { api, errorMessage, formatDateTime, type VideoDetail } from "@/lib/api";
import { useEditor } from "./AutoSaveField";
import { useMe } from "@/components/MeContext";

export type ManualPlatform = "youtube" | "instagram";

const NAMES: Record<ManualPlatform, { label: string; placeholder: string; app: string }> = {
  youtube: { label: "YouTube Shorts", placeholder: "https://youtube.com/shorts/…", app: "YouTube" },
  instagram: { label: "Instagram Reels", placeholder: "https://www.instagram.com/reel/…", app: "Instagram" },
};

/**
 * A platform the app has no connection to (YouTube Shorts, Instagram Reels): the member downloads the MP4, copies the
 * caption, posts in the platform's own app, then records the post here with its link ("Đã đăng tay").
 */
export default function ManualPostCard({ video, platform }: { video: VideoDetail; platform: ManualPlatform }) {
  const { message } = App.useApp();
  const { onSaved } = useEditor();
  const { me } = useMe();
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const names = NAMES[platform];
  const posts = video.manual_posts.filter((post) => post.platform === platform);

  async function copy(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      message.success("Đã chép caption + hashtag");
    } catch {
      message.error("Trình duyệt không cho chép, hãy chép tay ở thẻ Nội dung đăng");
    }
  }

  async function record() {
    setBusy(true);
    try {
      onSaved(await api<VideoDetail>(`/manual-posts/videos/${video.id}`, "POST", { platform, url }));
      setUrl("");
      message.success(`Đã ghi bài ${names.label}`);
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function remove(postId: number) {
    try {
      onSaved(await api<VideoDetail>(`/manual-posts/${postId}`, "DELETE"));
    } catch (err) {
      message.error(errorMessage(err));
    }
  }

  return (
    <Flex vertical gap={12} data-testid={`manual-post-${platform}`}>
      <Typography.Text type="secondary">
        App chưa kết nối {names.app}: tải MP4 về, chép caption rồi đăng trong app {names.app}. Đăng xong dán link bài
        vào đây để cả nhóm biết video đã lên {names.label}.
      </Typography.Text>
      <Flex wrap gap={8}>
        {video.mp4 && (
          <Button icon={<DownloadOutlined />} href={video.mp4.download_url}>
            Tải MP4
          </Button>
        )}
        <Button icon={<CopyOutlined />} onClick={() => void copy(video.post_text)}>
          Copy caption + hashtag
        </Button>
      </Flex>
      <div>
        <Typography.Text strong>Đã đăng tay</Typography.Text>
        <Flex wrap gap={8} style={{ marginTop: 4 }}>
          <Input
            aria-label={`Link bài ${names.label}`}
            placeholder={names.placeholder}
            value={url}
            onChange={(event) => setUrl(event.target.value)}
            style={{ maxWidth: 360 }}
          />
          <Button loading={busy} disabled={!url.trim() || !video.mp4} onClick={() => void record()}>
            Ghi bài đã đăng
          </Button>
        </Flex>
      </div>
      {posts.length > 0 && (
        <Flex vertical gap={6}>
          {posts.map((post) => (
            <Flex key={post.id} gap={8} align="center" wrap data-testid="manual-post">
              <a href={post.url ?? undefined} target="_blank" rel="noreferrer">
                Xem bài {names.label}
              </a>
              <Typography.Text type="secondary">
                {post.created_by}, {formatDateTime(post.at)}
              </Typography.Text>
              {post.created_by_id === me.id && (
                <Popconfirm
                  title="Xoá bài này khỏi app?"
                  description={`Bài trên ${names.app} không bị xoá.`}
                  okText="Xoá"
                  cancelText="Huỷ"
                  onConfirm={() => void remove(post.id)}
                >
                  <Button size="small" type="text" danger icon={<DeleteOutlined />} aria-label="Xoá bài khỏi app" />
                </Popconfirm>
              )}
            </Flex>
          ))}
        </Flex>
      )}
    </Flex>
  );
}
