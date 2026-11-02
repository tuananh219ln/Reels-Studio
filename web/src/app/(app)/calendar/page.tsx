"use client";

import dayjsGenerateConfig from "@rc-component/picker/generate/dayjs";
import { UnorderedListOutlined } from "@ant-design/icons";
import { App, Badge, Button, Calendar, Card, Empty, Flex, Grid, Tag } from "antd";
import dayjs, { type Dayjs } from "dayjs";
import "dayjs/locale/vi";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { api, errorMessage, formatDateTime, type PostRow } from "@/lib/api";
import { POST_STATUS } from "@/lib/postStatus";
import PageHeader from "@/components/PageHeader";

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

/** A month of reels by their posting time; view only, a reel opens its video. */
export default function CalendarPage() {
  const { message } = App.useApp();
  const [posts, setPosts] = useState<PostRow[]>([]);

  useEffect(() => {
    api<PostRow[]>("/posts")
      .then(setPosts)
      .catch((err) => message.error(errorMessage(err)));
  }, [message]);

  const days = useMemo(() => byDay(posts), [posts]);
  // Seven full-size day columns need about 760 px; a phone gets the compact month and the chosen day's list.
  const wide = Grid.useBreakpoint().md ?? true;
  const [chosen, setChosen] = useState<Dayjs>(vietnamToday);
  const chosenPosts = days.get(chosen.format("DD/MM/YYYY")) ?? [];

  const postTag = ({ post, clock }: { post: PostRow; clock: string }) => (
    <Link prefetch={false} key={post.video_id} href={`/videos/${post.video_id}`}>
      <Tag color={POST_STATUS[post.status].color} style={{ whiteSpace: "normal", margin: 0 }}>
        {clock} {post.title}
      </Tag>
    </Link>
  );

  return (
    <>
      <PageHeader
        title="Lịch đăng bài"
        actions={
          <Link prefetch={false} href="/posts">
            <Button icon={<UnorderedListOutlined />}>Xem dạng danh sách</Button>
          </Link>
        }
      >
        <Flex gap={4}>
          {Object.values(POST_STATUS).map((status) => (
            <Tag key={status.label} color={status.color}>
              {status.label}
            </Tag>
          ))}
        </Flex>
      </PageHeader>
      {wide ? (
        <Card styles={{ body: { overflowX: "auto" } }}>
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
            <VietnamCalendar
              fullscreen={false}
              value={chosen}
              onSelect={setChosen}
              cellRender={(date, info) => {
                const day = info.type === "date" ? (days.get(date.format("DD/MM/YYYY")) ?? []) : [];
                return day.length === 0 ? null : (
                  <Flex justify="center" gap={2} data-testid="calendar-dot">
                    {day.slice(0, 3).map(({ post }) => (
                      <Badge key={post.video_id} status={post.status === "published" ? "success" : "processing"} />
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
      )}
    </>
  );
}
