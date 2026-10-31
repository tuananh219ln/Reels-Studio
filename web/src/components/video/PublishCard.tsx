"use client";

import { SendOutlined } from "@ant-design/icons";
import { Alert, App, Button, Card, Flex, Input, Popconfirm, Radio, Select, Typography } from "antd";
import Link from "next/link";
import { useState } from "react";
import { api, errorMessage, type VideoDetail } from "@/lib/api";
import { useEditor } from "./AutoSaveField";

const time = (value: string) => new Date(value).toLocaleString("vi-VN", { dateStyle: "short", timeStyle: "short" });

/** Posts the current MP4 with the saved caption and hashtags to one of the team's Fanpages, once per video. */
export default function PublishCard({ video }: { video: VideoDetail }) {
  const { message } = App.useApp();
  const editor = useEditor();
  const [mode, setMode] = useState<"now" | "later">("now");
  const [when, setWhen] = useState("");
  const [picked, setPicked] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const posted = video.publication;
  const fanpage = picked ?? (video.fanpages.length === 1 ? video.fanpages[0].id : null);

  async function publish() {
    setBusy(true);
    try {
      // The post uses the saved caption: leave the field being typed in and wait until it is saved.
      await editor.flush();
      const scheduled_at = mode === "later" ? new Date(when).toISOString() : null;
      editor.onSaved(
        await api<VideoDetail>(`/videos/${video.id}/publish`, "POST", { fanpage_id: fanpage, scheduled_at }),
      );
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  if (posted?.status === "published") {
    return (
      <Card title="Đăng Facebook" size="small">
        <Typography.Text type="success" data-testid="publication-status">
          Đã đăng lên Facebook
        </Typography.Text>{" "}
        {posted.url && (
          <a href={posted.url} target="_blank" rel="noreferrer">
            Xem Reel
          </a>
        )}
        {posted.fanpage && (
          <Typography.Paragraph type="secondary" style={{ margin: 0 }}>
            {posted.fanpage}
          </Typography.Paragraph>
        )}
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

  if (video.fanpages.length === 0) {
    return (
      <Card title="Đăng Facebook" size="small">
        <Typography.Text>
          Chưa có Fanpage nào đang dùng. Vào <Link href="/fanpages">Kết nối Fanpage</Link> để thêm.
        </Typography.Text>
      </Card>
    );
  }

  const waiting = !fanpage || (mode === "later" && !when);
  return (
    <Card title="Đăng Facebook" size="small">
      <Flex vertical gap={8}>
        {video.mp4_outdated && <Alert type="warning" showIcon title="Hãy render lại trước khi đăng" />}
        <Select
          aria-label="Fanpage"
          value={fanpage}
          disabled={video.locked}
          placeholder="Chọn Fanpage"
          onChange={setPicked}
          style={{ maxWidth: 320 }}
          options={video.fanpages.map((page) => ({ value: page.id, label: page.name }))}
        />
        <Radio.Group
          value={mode}
          disabled={video.locked}
          onChange={(event) => setMode(event.target.value)}
          options={[
            { value: "now", label: "Đăng ngay" },
            { value: "later", label: "Hẹn giờ" },
          ]}
        />
        {mode === "later" && (
          <Input
            type="datetime-local"
            aria-label="Giờ đăng"
            value={when}
            style={{ maxWidth: 240 }}
            disabled={video.locked}
            onChange={(event) => setWhen(event.target.value)}
          />
        )}
        <Typography.Text type="secondary">
          Đăng MP4 hiện tại kèm caption và hashtag đã lưu. Bình luận ghim vẫn làm tay trên Facebook.
        </Typography.Text>
        <Popconfirm
          title="Đăng công khai lên Fanpage này?"
          okText="Đăng"
          cancelText="Huỷ"
          onConfirm={publish}
          disabled={video.locked || video.mp4_outdated || waiting || busy}
        >
          <Button
            type="primary"
            icon={<SendOutlined />}
            loading={busy}
            disabled={video.locked || video.mp4_outdated || waiting}
          >
            Đăng lên Facebook
          </Button>
        </Popconfirm>
      </Flex>
    </Card>
  );
}
