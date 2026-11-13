"use client";

import EmptyState from "@/components/EmptyState";
import PostCalendar from "@/components/PostCalendar";
import { api, errorMessage, type PostRow } from "@/lib/api";
import { App, Flex, Spin, Typography } from "antd";
import { useEffect, useState } from "react";

/** "Lịch đăng" in Kho kiến thức: the calendar of the posts of one topic group, those on Facebook and those waiting for
 * their time, the ones a member scheduled and the ones a Page's queue scheduled by itself. The queue schedules a video
 * only when its Page's slot is within the next 48 hours, so a queued video appears here a day or two before it goes. */
export default function TopicSchedule({ topicId, visible }: { topicId: number; visible: boolean }) {
  const { message } = App.useApp();
  const [posts, setPosts] = useState<PostRow[] | null>(null);

  useEffect(() => {
    if (!visible) return;
    api<PostRow[]>("/posts")
      .then((rows) => setPosts(rows.filter((post) => post.knowledge_topic_id === topicId)))
      .catch((err) => message.error(errorMessage(err)));
  }, [topicId, visible, message]);

  if (posts === null) {
    return (
      <Flex justify="center" style={{ padding: 32 }}>
        <Spin />
      </Flex>
    );
  }
  if (!posts.some((post) => post.status === "scheduled" || post.status === "published")) {
    return <EmptyState description="Nhóm này chưa có bài nào đã đăng hoặc hẹn giờ." />;
  }
  return (
    <Flex vertical gap={8}>
      <Typography.Text type="secondary">
        Bài đã đăng và đã hẹn giờ của nhóm, giờ Việt Nam. Video trong hàng chờ của Page lên lịch trước giờ đăng khoảng
        48 giờ, nên chỉ hiện ở đây khi đã được hẹn.
      </Typography.Text>
      <PostCalendar posts={posts} />
    </Flex>
  );
}
