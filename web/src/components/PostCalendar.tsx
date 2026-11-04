"use client";

import dayjsGenerateConfig from "@rc-component/picker/generate/dayjs";
import { Badge, Calendar, Card, Empty, Flex, Grid, Tag } from "antd";
import dayjs, { type Dayjs } from "dayjs";
import "dayjs/locale/vi";
import Link from "next/link";
import { useMemo, useState } from "react";
import { formatDateTime, type PostRow } from "@/lib/api";
import { POST_STATUS } from "@/lib/postStatus";

dayjs.locale("vi");

/** Today's date in Vietnam as a plain local date, because the calendar's cells have no time zone. */
function vietnamToday(): Dayjs {
  const [day, month, year] = formatDateTime(new Date().toISOString()).split(" ")[0].split("/");
  return dayjs(`${year}-${month}-${day}`);
}

// Antd takes "now" from the browser's clock; this one opens on Vietnam's month and marks Vietnam's today.
const VietnamCalendar = Calendar.generateCalendar<Dayjs>({ ...dayjsGenerateConfig, getNow: vietnamToday });

/** Oldest first, under their day in Vietnam time, keyed dd/mm/yyyy as `formatDateTime` writes it. */
function byDay(posts: PostRow[]): Map<string, { post: PostRow; clock: string }[]> {
  const days = new Map<string, { post: PostRow; clock: string }[]>();
  for (const post of [...posts].reverse()) {
    const [day, clock] = formatDateTime(post.at).split(" ");
    days.set(day, [...(days.get(day) ?? []), { post, clock }]);
  }
  return days;
}

/** "Lịch" on "Bài đăng": a month of the scheduled and posted reels by their time; view only, a reel opens its video. */
export default function PostCalendar({ posts }: { posts: PostRow[] }) {
  const days = useMemo(
    () => byDay(posts.filter((post) => post.status === "scheduled" || post.status === "published")),
    [posts],
  );
  // Seven full-size day columns need about 760 px; a phone gets the compact month and the chosen day's list.
  const wide = Grid.useBreakpoint().md ?? true;
  const [chosen, setChosen] = useState<Dayjs>(vietnamToday);
  const chosenPosts = days.get(chosen.format("DD/MM/YYYY")) ?? [];

  const postTag = ({ post, clock }: { post: PostRow; clock: string }) => (
    <Link prefetch={false} key={post.id} href={`/videos/${post.video_id}`}>
      <Tag color={POST_STATUS[post.status].color} style={{ whiteSpace: "normal", margin: 0 }}>
        {clock} {post.title}
      </Tag>
    </Link>
  );

  const legend = (
    <Flex gap={4} style={{ marginBottom: 12 }}>
      {(["scheduled", "published"] as const).map((status) => (
        <Tag key={status} color={POST_STATUS[status].color}>
          {POST_STATUS[status].label}
        </Tag>
      ))}
    </Flex>
  );

  return wide ? (
    <Card styles={{ body: { overflowX: "auto" } }}>
      {legend}
      <div style={{ minWidth: 760 }}>
        <VietnamCalendar
          cellRender={(date, info) =>
            info.type !== "date" ? null : (
              <Flex vertical gap={2}>
                {(days.get(date.format("DD/MM/YYYY")) ?? []).map(postTag)}
              </Flex>
            )
          }
        />
      </div>
    </Card>
  ) : (
    <Flex vertical gap={12}>
      <Card styles={{ body: { padding: 8 } }}>
        {legend}
        <VietnamCalendar
          fullscreen={false}
          value={chosen}
          onSelect={setChosen}
          cellRender={(date, info) => {
            const day = info.type === "date" ? (days.get(date.format("DD/MM/YYYY")) ?? []) : [];
            return day.length === 0 ? null : (
              <Flex justify="center" gap={2} data-testid="calendar-dot">
                {day.slice(0, 3).map(({ post }) => (
                  <Badge key={post.id} status={post.status === "published" ? "success" : "processing"} />
                ))}
              </Flex>
            );
          }}
        />
      </Card>
      <Card size="small" title={`Ngày ${chosen.format("DD/MM/YYYY")}`}>
        {chosenPosts.length === 0 ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Không có bài đăng nào" />
        ) : (
          <Flex vertical gap={6}>
            {chosenPosts.map(postTag)}
          </Flex>
        )}
      </Card>
    </Flex>
  );
}
