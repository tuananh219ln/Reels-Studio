"use client";

import EmptyState from "@/components/EmptyState";
import { api, errorMessage, type QueueOverview } from "@/lib/api";
import { App, Button, Flex, Spin, Typography } from "antd";
import Link from "next/link";
import { useEffect, useState } from "react";

/** "Lịch đăng" in Kho kiến thức: only a link. The one calendar of what is out and what is set to go is the Page's
 * "Lịch đăng" tab on Quản lý kênh (docs/decisions/2026-11-24-winner-gate-docs.md), so two copies can never differ;
 * this tab names the Pages that post the group and opens it. */
export default function TopicSchedule({
  topicId,
  fanpageId,
  visible,
}: {
  topicId: number;
  /** Only this Page's link (a group several Pages post, with one of them chosen). */
  fanpageId?: number;
  visible: boolean;
}) {
  const { message } = App.useApp();
  const [pages, setPages] = useState<QueueOverview["pages"] | null>(null);

  useEffect(() => {
    if (!visible) return;
    api<QueueOverview>("/queue")
      .then((overview) =>
        setPages(overview.pages.filter((page) => page.topic?.id === topicId && (!fanpageId || page.id === fanpageId))),
      )
      .catch((err) => message.error(errorMessage(err)));
  }, [topicId, fanpageId, visible, message]);

  if (pages === null) {
    return (
      <Flex justify="center" style={{ padding: 32 }}>
        <Spin />
      </Flex>
    );
  }
  if (pages.length === 0) {
    return (
      <EmptyState description="Chưa có Page nào đăng nhóm này. Chọn nhóm cho Page ở Quản lý kênh, tab Lịch đăng." />
    );
  }
  return (
    <Flex vertical gap={12} data-testid="topic-schedule-links">
      <Typography.Text type="secondary">
        Lịch đăng (bài đã đăng, đã hẹn giờ, khung trống) chỉ có một bản, ở Quản lý kênh của từng Page.
      </Typography.Text>
      <Flex wrap gap={8}>
        {pages.map((page) => (
          <Link key={page.id} prefetch={false} href={`/fanpages/${page.id}?tab=schedule`}>
            <Button>Mở lịch đăng của {page.name}</Button>
          </Link>
        ))}
      </Flex>
    </Flex>
  );
}
