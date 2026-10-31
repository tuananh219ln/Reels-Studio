"use client";

import { SendOutlined } from "@ant-design/icons";
import { Alert, App, Button, Card, Flex, Input, Popconfirm, Radio, Typography } from "antd";
import Link from "next/link";
import { useState } from "react";
import { api, errorMessage, type VideoDetail } from "@/lib/api";
import { useEditor } from "./AutoSaveField";

const time = (value: string) =>
  new Date(value).toLocaleString("vi-VN", { dateStyle: "short", timeStyle: "short" });

/** Posts the current MP4 with the saved caption and hashtags to the team's Facebook Page, once per video. */
export default function PublishCard({ video }: { video: VideoDetail }) {
  const { message } = App.useApp();
  const editor = useEditor();
  const [mode, setMode] = useState<"now" | "later">("now");
  const [when, setWhen] = useState("");
  const [busy, setBusy] = useState(false);
  const posted = video.publication;

  async function publish() {
    setBusy(true);
    try {
      // The post uses the saved caption: leave the field being typed in and wait until it is saved.
      await editor.flush();
      const scheduled_at = mode === "later" ? new Date(when).toISOString() : null;
      editor.onSaved(await api<VideoDetail>(`/videos/${video.id}/publish`, "POST", { scheduled_at }));
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  if (posted?.status === "published") {
    return (
      <Card title="Đăng Facebook" size="small">
        <Typography.Text type="success" data-testid="publication-status">Đã đăng lên Facebook</Typography.Text>{" "}
        {posted.url && <a href={posted.url} target="_blank" rel="noreferrer">Xem Reel</a>}
      </Card>
    );
  }
  if (posted?.status === "scheduled") {
    return (
      <Card title="Đăng Facebook" size="small">
        <Typography.Text data-testid="publication-status">
          {posted.scheduled_at ? `Đã hẹn đăng lúc ${time(posted.scheduled_at)}` : "Đã hẹn đăng trên Facebook"}
        </Typography.Text>
        <Typography.Paragraph type="secondary" style={{ margin: "4px 0 0" }}>
          Muốn đổi giờ hoặc huỷ, hãy làm trong Meta Business Suite.
        </Typography.Paragraph>
      </Card>
    );
  }

  if (!video.facebook_ready) {
    return (
      <Card title="Đăng Facebook" size="small">
        <Typography.Text>
          Chưa kết nối Facebook Page. <Link href="/settings">Vào Cài đặt</Link> để nhập Page ID và token.
        </Typography.Text>
      </Card>
    );
  }

  const waiting = mode === "later" && !when;
  return (
    <Card title="Đăng Facebook" size="small">
      <Flex vertical gap={8}>
        {video.mp4_outdated && <Alert type="warning" showIcon title="Hãy render lại trước khi đăng" />}
        <Radio.Group value={mode} disabled={video.locked} onChange={(event) => setMode(event.target.value)}
          options={[{ value: "now", label: "Đăng ngay" }, { value: "later", label: "Hẹn giờ" }]} />
        {mode === "later" && (
          <Input type="datetime-local" aria-label="Giờ đăng" value={when} style={{ maxWidth: 240 }}
            disabled={video.locked} onChange={(event) => setWhen(event.target.value)} />
        )}
        <Typography.Text type="secondary">
          Đăng MP4 hiện tại kèm caption và hashtag đã lưu. Bình luận ghim vẫn làm tay trên Facebook.
        </Typography.Text>
        <Popconfirm title="Đăng công khai lên Facebook Page?" okText="Đăng" cancelText="Huỷ" onConfirm={publish}
          disabled={video.locked || video.mp4_outdated || waiting || busy}>
          <Button type="primary" icon={<SendOutlined />} loading={busy}
            disabled={video.locked || video.mp4_outdated || waiting}>
            Đăng lên Facebook
          </Button>
        </Popconfirm>
      </Flex>
    </Card>
  );
}
