"use client";

import { CopyOutlined } from "@ant-design/icons";
import { App, Button, Card, Flex, Input, Typography } from "antd";
import { api, errorMessage, type VideoDetail } from "@/lib/api";
import { useEditor } from "./AutoSaveField";

/**
 * "Tiêu đề & caption" on the "Đăng bài" tab of a video Muse wrote with beats (its left column has no title row any
 * more): the title is the title scene's text, saved when the field is left; "Copy caption + hashtag" copies what a post
 * sends. The caption and hashtags are edited just below, in "Nội dung đăng".
 */
export default function TitleCaptionCard({ video }: { video: VideoDetail }) {
  const { message } = App.useApp();
  const editor = useEditor();
  const scene = video.title_scene;
  if (!scene) return null;
  const empty = scene.text.trim() === "";

  async function saveTitle(text: string) {
    if (!scene || text === scene.text) return;
    const request = api<VideoDetail>(`/scenes/${scene.id}`, "PATCH", { text });
    editor.track(request);
    try {
      editor.onSaved(await request);
      editor.reportFailed("title", false);
    } catch (err) {
      editor.reportFailed("title", true);
      message.error(errorMessage(err));
    }
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(video.post_text);
      message.success("Đã chép caption và hashtag");
    } catch {
      message.error("Không chép được, hãy chép tay ở “Nội dung đăng”");
    }
  }

  return (
    <Card size="small" title="Tiêu đề & caption" data-testid="title-caption-card" style={{ borderRadius: 12 }}>
      <Flex vertical gap={8}>
        <Input
          key={scene.text}
          aria-label="Tiêu đề video"
          defaultValue={scene.text}
          status={empty ? "error" : undefined}
          placeholder="Chưa có tiêu đề"
          disabled={editor.locked || editor.readOnly}
          onBlur={(event) => void saveTitle(event.target.value)}
        />
        {empty && (
          <Typography.Text type="danger" style={{ fontSize: 12.5 }}>
            Chưa có tiêu đề thì chưa duyệt được.
          </Typography.Text>
        )}
        <Typography.Text
          type="secondary"
          style={{ fontSize: 12.5, whiteSpace: "pre-wrap" }}
          data-testid="caption-preview"
        >
          {video.post_text || "Chưa có caption."}
        </Typography.Text>
        <Button size="small" icon={<CopyOutlined />} onClick={() => void copy()} style={{ alignSelf: "flex-start" }}>
          Copy caption + hashtag
        </Button>
      </Flex>
    </Card>
  );
}
