"use client";

import { FacebookFilled, InstagramFilled, TikTokFilled, YoutubeFilled } from "@ant-design/icons";
import { AutoComplete, Flex, Tag, Tooltip, theme } from "antd";
import { useEffect, useRef, useState } from "react";
import { api, type VideoMadeVia, type VideoRow } from "@/lib/api";

const MADE_VIA: Record<VideoMadeVia, { label: string; hint: string }> = {
  ai: { label: "AI viết", hint: "Kịch bản do AI của nhóm viết" },
  manual: { label: "Tự viết", hint: "Kịch bản do thành viên tự viết, chưa được AI rà soát an toàn" },
  sample: { label: "Từ video mẫu", hint: "Kịch bản học từ một video mẫu" },
  clone: { label: "Nhân bản", hint: "Nhân bản từ một video khác" },
  // Named by the assistant itself below (ChatGPT, Claude, Muse...); "Trợ lý AI" for videos made before it was kept.
  assistant: { label: "Trợ lý AI (MCP)", hint: "Kịch bản do trợ lý AI của thành viên viết qua kết nối MCP" },
};

/** What kind of video it is, as small tags: its "Loại nội dung" first, "Bản TikTok" for a TikTok version, how its
 * script came, "Xuyên suốt" for a
 * backdrop video, and its products. Used on every list of videos, cards and rows alike. */
export function VideoKindTags({
  video,
}: {
  video: Pick<VideoRow, "made_via" | "assistant_app" | "mode" | "content_type" | "product_count" | "platform">;
}) {
  const made =
    video.made_via === "assistant" && video.assistant_app
      ? {
          label: `${video.assistant_app} (MCP)`,
          hint: `Kịch bản do ${video.assistant_app} của thành viên viết qua kết nối MCP`,
        }
      : (MADE_VIA[video.made_via] ?? MADE_VIA.ai);
  const tag = { marginInlineEnd: 0, fontSize: 12, lineHeight: "18px", paddingInline: 6 };
  return (
    <Flex wrap gap={4} data-testid="video-kind">
      {video.content_type && (
        <Tag color="blue" style={tag} data-testid="video-content-type">
          {video.content_type}
        </Tag>
      )}
      {video.platform === "tiktok" && (
        // A TikTok version is its own video; a Facebook one, the default, needs no tag.
        <Tooltip title="Bản làm riêng cho TikTok">
          <Tag color="default" style={tag} data-testid="video-platform">
            Bản TikTok
          </Tag>
        </Tooltip>
      )}
      <Tooltip title={made.hint}>
        <Tag style={tag}>{made.label}</Tag>
      </Tooltip>
      {video.mode === "single" && (
        <Tooltip title="Một ảnh hoặc clip chạy suốt video">
          <Tag style={tag}>Xuyên suốt</Tag>
        </Tooltip>
      )}
      {(video.product_count ?? 0) > 0 && (
        <Tooltip title="Có gắn sản phẩm affiliate">
          <Tag color="green" style={tag}>
            Sản phẩm{(video.product_count ?? 0) > 1 ? ` (${video.product_count})` : ""}
          </Tag>
        </Tooltip>
      )}
    </Flex>
  );
}

const PLATFORMS = [
  { key: "facebook", name: "Facebook", Icon: FacebookFilled, color: "#1877F2" },
  { key: "tiktok", name: "TikTok", Icon: TikTokFilled, color: "#111111" },
  { key: "youtube", name: "YouTube", Icon: YoutubeFilled, color: "#FF0000" },
  { key: "instagram", name: "Instagram", Icon: InstagramFilled, color: "#E1306C" },
] as const;

/** "Đã đăng": one icon per platform, in its colour where the video is out, grey where it is not. */
export function PostedPlatforms({ postedOn, size = 16 }: { postedOn: VideoRow["posted_on"]; size?: number }) {
  const { token } = theme.useToken();
  const out = new Set(postedOn);
  return (
    <Flex
      gap={6}
      align="center"
      data-testid="posted-platforms"
      aria-label={
        out.size
          ? `Đã đăng: ${PLATFORMS.filter((platform) => out.has(platform.key))
              .map((platform) => platform.name)
              .join(", ")}`
          : "Chưa đăng nền tảng nào"
      }
    >
      {PLATFORMS.map(({ key, name, Icon, color }) => (
        <Tooltip key={key} title={out.has(key) ? `Đã đăng ${name}` : `Chưa đăng ${name}`}>
          <Icon
            data-platform={key}
            data-posted={out.has(key) ? "true" : "false"}
            style={{ fontSize: size, color: out.has(key) ? color : token.colorTextQuaternary }}
          />
        </Tooltip>
      ))}
    </Flex>
  );
}

/** "Loại nội dung" on a video's page: typed freely or picked from the types the team's videos already use, saved when
 * the field is left or a type is picked. */
export function ContentTypeField({
  value,
  disabled,
  onSave,
}: {
  value: string;
  disabled?: boolean;
  onSave: (contentType: string) => Promise<unknown>;
}) {
  const [text, setText] = useState(value);
  const [used, setUsed] = useState<string[]>([]);
  // What was last sent, so picking a type and then leaving the field saves it once.
  const sent = useRef(value);

  useEffect(() => {
    api<string[]>("/video-content-types")
      .then(setUsed)
      // Only suggestions: without them the field still takes any type.
      .catch(() => setUsed([]));
  }, []);

  function save(next: string) {
    const clean = next.trim().replace(/\s+/g, " ");
    if (clean !== sent.current) {
      sent.current = clean;
      void onSave(clean).catch(() => {
        sent.current = value;
        setText(value);
      });
    }
  }

  const wanted = text.trim().toLowerCase();
  return (
    <AutoComplete
      aria-label="Loại nội dung"
      placeholder="+ Loại nội dung"
      size="small"
      allowClear
      variant="filled"
      maxLength={40}
      disabled={disabled}
      style={{ width: 200 }}
      value={text}
      options={used
        .filter((kind) => !wanted || kind.toLowerCase().includes(wanted))
        .map((kind) => ({ value: kind, label: kind }))}
      onChange={(next) => setText(next ?? "")}
      onSelect={(next: string) => {
        setText(next);
        save(next);
      }}
      onClear={() => save("")}
      onBlur={() => save(text)}
      onKeyDown={(event) => {
        if (event.key === "Enter") {
          save(text);
        }
      }}
    />
  );
}
