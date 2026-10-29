"use client";

import { CopyOutlined } from "@ant-design/icons";
import { App, Alert, Button, Card, Flex, Typography } from "antd";
import { api, type VideoDetail } from "@/lib/api";
import AutoSaveField from "./AutoSaveField";

type PostFields = Pick<VideoDetail, "caption" | "hashtags" | "affiliates" | "pinned_comment" | "music_suggestions">;

const lines = (text: string) => text.split("\n").map((line) => line.trim()).filter(Boolean);
const words = (text: string) => text.split(/\s+/).filter(Boolean);

export default function PostContent({ video }: { video: VideoDetail }) {
  const { message } = App.useApp();
  const patch = (body: Partial<PostFields>) => api<VideoDetail>(`/videos/${video.id}`, "PATCH", body);
  const warningsFor = (field: string) =>
    video.video_warnings.filter((warning) => warning.field === field).map((warning) => warning.message);

  async function copy(text: string, what: string) {
    try {
      await navigator.clipboard.writeText(text);
      message.success(`Đã copy ${what}`);
    } catch {
      message.error("Trình duyệt không cho copy, hãy chọn chữ rồi copy tay");
    }
  }

  return (
    <Card title="Nội dung đăng" size="small">
      <Flex vertical gap={4}>
        <AutoSaveField label="Caption" value={video.caption} multiline rows={5} save={(caption) => patch({ caption })} />
        <Warnings messages={warningsFor("caption")} />
        <AutoSaveField
          label="Hashtag"
          value={video.hashtags.join(" ")}
          placeholder="#xuongkhop #duongsinh"
          save={(text) => patch({ hashtags: words(text) })}
        />
        <AutoSaveField
          label="Sản phẩm affiliate"
          value={video.affiliates.join("\n")}
          multiline
          hint="Mỗi dòng một sản phẩm"
          save={(text) => patch({ affiliates: lines(text) })}
        />
        <AutoSaveField
          label="Bình luận ghim"
          value={video.pinned_comment}
          multiline
          save={(pinned_comment) => patch({ pinned_comment })}
        />
        <Warnings messages={warningsFor("pinned_comment")} />
        <AutoSaveField
          label="Gợi ý nhạc"
          value={video.music_suggestions.join("\n")}
          multiline
          hint="Tìm tên nhạc này trong TikTok hoặc Facebook khi đăng; mỗi dòng một bản"
          save={(text) => patch({ music_suggestions: lines(text) })}
        />
        <Flex wrap gap={8} style={{ marginBottom: 12 }}>
          <Button icon={<CopyOutlined />}
            onClick={() => copy(`${video.caption}\n\n${video.hashtags.join(" ")}`, "caption + hashtag")}>
            Copy caption + hashtag
          </Button>
          <Button icon={<CopyOutlined />} onClick={() => copy(video.pinned_comment, "bình luận ghim")}>
            Copy bình luận ghim
          </Button>
          <Button icon={<CopyOutlined />} onClick={() => copy(video.music_suggestions.join("\n"), "gợi ý nhạc")}>
            Copy gợi ý nhạc
          </Button>
        </Flex>
        <Typography.Text strong>Tự rà soát an toàn của Claude</Typography.Text>
        {video.self_review.length ? (
          <ul style={{ margin: "4px 0 0", paddingLeft: 20 }} data-testid="self-review">
            {video.self_review.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        ) : (
          <Typography.Text type="secondary">Không có câu nào phải sửa</Typography.Text>
        )}
      </Flex>
    </Card>
  );
}

function Warnings({ messages }: { messages: string[] }) {
  return messages.map((text) => <Alert key={text} type="warning" showIcon title={text} style={{ marginBottom: 8 }} />);
}
