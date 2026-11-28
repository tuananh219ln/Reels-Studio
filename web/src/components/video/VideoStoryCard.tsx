"use client";

import { CopyOutlined, ReloadOutlined, UndoOutlined } from "@ant-design/icons";
import { App, Button, Collapse, Descriptions, Empty, Flex, Spin, Tabs, Tag, Timeline, Typography } from "antd";
import { useCallback, useState } from "react";
import { COLORS } from "@/app/theme";
import { api, errorMessage, formatDateTime, type VideoDetail, type VideoEditEntry, type VideoStory } from "@/lib/api";
import { narration } from "@/lib/narration";

const SOURCE_COLORS: Record<string, string> = {
  VieNeu: "green",
  "MP3 tải lên": "purple",
  ElevenLabs: "blue",
  Gemini: "gold",
  Google: "cyan",
};

const TIMELINE_COLORS: Record<VideoStory["timeline"][number]["kind"], string> = {
  created: "green",
  job: "blue",
  review: "purple",
  edit: "gray",
};

function minutes(value: number | null): string {
  if (value === null) return "";
  return value >= 60 ? `${Math.floor(value / 60)} giờ ${value % 60} phút` : `${value} phút`;
}

function HistoryList({
  entries,
  undo,
  disabled,
}: {
  entries: VideoEditEntry[];
  undo: (entry: VideoEditEntry) => void;
  disabled: boolean;
}) {
  if (entries.length === 0) {
    return <Empty description="Chưa có lần sửa nào được ghi (lịch sử bắt đầu từ 26/11/2026)" />;
  }
  return (
    <Flex vertical gap={10} data-testid="video-history">
      {entries.map((entry) => (
        <div key={entry.id} style={{ borderBottom: "1px solid rgba(128,128,128,0.2)", paddingBottom: 8 }}>
          <Flex justify="space-between" align="center" gap={8} wrap>
            <Typography.Text style={{ fontSize: 13 }}>
              {entry.action === "restore" ? <Tag color="gold">Hoàn tác</Tag> : <Tag color="blue">Sửa</Tag>}
              {entry.by ?? "Thành viên đã xoá"} lúc {formatDateTime(entry.at)}
              {entry.source === "mcp" ? " (qua Claude)" : ""}
              {entry.undone && (
                <Tag style={{ marginLeft: 8 }} color="default">
                  đã hoàn tác
                </Tag>
              )}
            </Typography.Text>
            {entry.action === "update" && !entry.undone && entry.changes.some((change) => change.restorable) && (
              <Button size="small" icon={<UndoOutlined />} disabled={disabled} onClick={() => undo(entry)}>
                Hoàn tác
              </Button>
            )}
          </Flex>
          {entry.changes.map((change) => (
            <Typography.Paragraph key={change.key} type="secondary" style={{ margin: "4px 0 0", fontSize: 12 }}>
              {change.place} · {change.field}: <del>{change.old}</del> → {change.new}
            </Typography.Paragraph>
          ))}
        </div>
      ))}
    </Flex>
  );
}

/** The card's one line while closed, from what the page already has: who wrote it, its narration and its music. */
function summaryOf(video: VideoDetail): string {
  const { uploaded, service } = narration(video);
  const voices = [
    uploaded.length > 0 && `MP3 tải lên ${uploaded.length} cảnh`,
    service.length > 0 && `giọng dịch vụ ${service.length} cảnh`,
  ].filter(Boolean);
  return [
    video.script_by ?? (video.hand_written ? "Kịch bản tự viết" : null),
    voices.join(", ") || "không lời đọc",
    video.music ? `nhạc ${video.music.name ?? "tải lên"} ${video.music_volume}%` : "không nhạc",
  ]
    .filter(Boolean)
    .join(" · ");
}

/**
 * "Video này được làm như thế nào": who made the video and how, each scene's voice and its source, the music, how long
 * it took and one timeline of its jobs, review steps and edits; and "Lịch sử sửa" with "Hoàn tác" (api
 * routes_video_story.py). Read when opened, so the page's polling does not fetch it.
 */
export default function VideoStoryCard({
  video,
  locked,
  act,
}: {
  video: VideoDetail;
  locked: boolean;
  act: (action: () => Promise<VideoDetail>) => Promise<unknown>;
}) {
  const { message } = App.useApp();
  const videoId = video.id;
  const [open, setOpen] = useState(false);
  const [story, setStory] = useState<VideoStory | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setStory(await api<VideoStory>(`/video-story/${videoId}`));
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [videoId, message]);

  async function undo(entry: VideoEditEntry) {
    await act(async () => {
      const answer = await api<{ video: VideoDetail | null; story: VideoStory }>(
        `/video-story/${videoId}/undo/${entry.id}`,
        "POST",
      );
      setStory(answer.story);
      message.success("Đã hoàn tác lần sửa");
      return answer.video ?? (await api<VideoDetail>(`/videos/${videoId}`));
    });
  }

  async function copy() {
    if (!story) return;
    try {
      await navigator.clipboard.writeText(story.text);
      message.success("Đã sao chép hồ sơ video");
    } catch {
      message.error("Trình duyệt không cho sao chép, hãy chọn và sao chép tay");
    }
  }

  const body = story ? (
    <Tabs
      size="small"
      items={[
        {
          key: "how",
          label: "Cách làm",
          children: (
            <Flex vertical gap={12}>
              <Descriptions size="small" column={1} bordered>
                <Descriptions.Item label="Tạo bởi">
                  {story.made.by ?? "?"} lúc {formatDateTime(story.made.at)}, {story.made.via}
                  {story.made.free ? " (gói đăng ký, không tốn phí AI của nhóm)" : ""}
                </Descriptions.Item>
                <Descriptions.Item label="Nhóm">{story.made.group ?? "(không nhóm)"}</Descriptions.Item>
                {story.voices.length > 0 && (
                  <Descriptions.Item label="Giọng đọc">
                    <Flex vertical gap={4}>
                      <span>
                        {Object.entries(story.voice_sources)
                          .map(([source, count]) => `${source} ${count} cảnh`)
                          .join(", ") || "Không có lời đọc"}
                        {story.mixed_voices && (
                          <Tag color="orange" style={{ marginLeft: 8 }}>
                            Trộn nhiều nguồn giọng
                          </Tag>
                        )}
                      </span>
                      <Flex wrap gap={4} data-testid="story-voices">
                        {story.voices.map((row) => (
                          <Tag key={row.scene_id} color={SOURCE_COLORS[row.source]}>
                            {row.label}: {row.source}
                            {row.voice ? ` · ${row.voice}` : ""}
                          </Tag>
                        ))}
                      </Flex>
                    </Flex>
                  </Descriptions.Item>
                )}
                <Descriptions.Item label="Nhạc">
                  {story.music ? `${story.music.name ?? "Có nhạc"} (${story.music.volume}%)` : "Không có nhạc"}
                </Descriptions.Item>
                <Descriptions.Item label="Thời gian">
                  {story.times.rendered_at
                    ? `Render xong ${formatDateTime(story.times.rendered_at)}, ${minutes(story.times.minutes_to_render)} từ lúc tạo` +
                      (story.times.render_seconds !== null
                        ? `, render mất ${Math.round(story.times.render_seconds)} giây`
                        : "")
                    : "Chưa render"}
                  {story.times.last_edit_at &&
                    `. Sửa lần cuối ${formatDateTime(story.times.last_edit_at)}${story.times.last_edit_by ? ` (${story.times.last_edit_by})` : ""}`}
                </Descriptions.Item>
              </Descriptions>
              <Timeline
                items={story.timeline.map((row, index) => ({
                  key: index,
                  color: TIMELINE_COLORS[row.kind],
                  children: (
                    <Typography.Text style={{ fontSize: 13 }}>
                      <Typography.Text type="secondary">{formatDateTime(row.at)}</Typography.Text> {row.text}
                      {row.by ? ` (${row.by})` : ""}
                    </Typography.Text>
                  ),
                }))}
              />
            </Flex>
          ),
        },
        {
          key: "history",
          label: `Lịch sử sửa (${story.history.length})`,
          children: <HistoryList entries={story.history} undo={undo} disabled={locked} />,
        },
      ]}
    />
  ) : (
    <Spin spinning={loading}>
      <div style={{ minHeight: 40 }} />
    </Spin>
  );

  return (
    <Collapse
      size="small"
      style={{ marginBottom: 12, background: COLORS.surface }}
      data-testid="video-story"
      onChange={(keys) => {
        setOpen(keys.length > 0);
        if (keys.length > 0 && !story) void load();
      }}
      items={[
        {
          key: "story",
          label: (
            <Flex gap={10} align="baseline" wrap style={{ minWidth: 0 }}>
              <span>Video này được làm như thế nào</span>
              {!open && video.has_script && (
                <Typography.Text type="secondary" style={{ fontSize: 12 }} data-testid="story-summary">
                  {summaryOf(video)}
                </Typography.Text>
              )}
            </Flex>
          ),
          extra: story && (
            <Flex gap={4} onClick={(event) => event.stopPropagation()}>
              <Button size="small" icon={<ReloadOutlined />} loading={loading} onClick={() => void load()}>
                Tải lại
              </Button>
              <Button size="small" icon={<CopyOutlined />} onClick={() => void copy()}>
                Sao chép hồ sơ video
              </Button>
            </Flex>
          ),
          children: body,
        },
      ]}
    />
  );
}
