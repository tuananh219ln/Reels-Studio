"use client";

import { DownOutlined } from "@ant-design/icons";
import { Flex, Typography } from "antd";
import { useState } from "react";
import { ContentTypeField, PostedPlatforms, VideoKindTags } from "@/components/VideoKind";
import { formatDateTime, type VideoDetail } from "@/lib/api";

/**
 * What the video is about, in one card under the header: its topic, group, maker, "Loại nội dung", how it was made and
 * where it is out. A video made from a plan idea sums the idea up in one line instead, and "Chi tiết" opens the rest.
 */
export default function VideoContext({
  video,
  onContentType,
}: {
  video: VideoDetail;
  onContentType: (contentType: string) => Promise<unknown>;
}) {
  const idea = video.plan_idea;
  const [open, setOpen] = useState(false);
  const details = (
    <Flex
      wrap
      align="center"
      gap="4px 12px"
      className="video-context__details"
      // Kept mounted while closed, so a "Loại nội dung" being typed keeps its text.
      style={{ display: idea && !open ? "none" : undefined }}
      data-testid="video-kind-line"
    >
      <Typography.Text type="secondary" style={{ fontSize: 13 }}>
        Chủ đề {video.topic}
        {video.knowledge_topic ? `, nhóm ${video.knowledge_topic}` : ""}, tạo bởi {video.created_by} lúc{" "}
        <span data-testid="video-created-at">{formatDateTime(video.created_at)}</span>
      </Typography.Text>
      <ContentTypeField
        key={video.content_type}
        value={video.content_type}
        disabled={video.locked}
        onSave={onContentType}
      />
      {/* The type is in the field already; the tags say how the video was made. */}
      <VideoKindTags video={{ ...video, content_type: "" }} />
      <PostedPlatforms postedOn={video.posted_on ?? []} links={video.posted_links} states={video.posted_states} />
    </Flex>
  );
  return (
    <div className="video-context">
      {idea && (
        <div className="video-context__idea" data-testid="plan-idea-card">
          <span className="video-context__day">
            Theo kế hoạch 30 ngày, {idea.day === null ? "Backlog" : `ngày ${idea.day}`}
            {idea.pain_group ? `, ${idea.pain_group}` : ""}
          </span>
          <span className="video-context__text">
            {idea.hook && <span>Hook: {idea.hook}</span>}
            {idea.pain && <span>Nỗi đau: {idea.pain}</span>}
          </span>
          <button
            type="button"
            className="video-context__toggle"
            aria-expanded={open}
            onClick={() => setOpen((value) => !value)}
          >
            {open ? "Thu gọn" : "Chi tiết"} <DownOutlined rotate={open ? 180 : 0} aria-hidden />
          </button>
        </div>
      )}
      {details}
    </div>
  );
}
