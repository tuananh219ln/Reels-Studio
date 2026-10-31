"use client";

import dayjsGenerateConfig from "@rc-component/picker/generate/dayjs";
import { App, Calendar, Card, Flex, Tag, Typography } from "antd";
import dayjs, { type Dayjs } from "dayjs";
import "dayjs/locale/vi";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { api, errorMessage, formatDateTime, type PostRow } from "@/lib/api";
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

  return (
    <>
      <Typography.Title level={2} style={{ marginTop: 0, fontWeight: 600 }}>
        Lịch đăng bài
      </Typography.Title>
      <Flex gap={4} style={{ marginBottom: 12 }}>
        {Object.values(POST_STATUS).map((status) => (
          <Tag key={status.label} color={status.color}>{status.label}</Tag>
        ))}
      </Flex>
      <Card styles={{ body: { overflowX: "auto" } }}>
        <div style={{ minWidth: 760 }}>
          <VietnamCalendar
            cellRender={(date, info) =>
              info.type !== "date" ? null : (
                <Flex vertical gap={2}>
                  {(days.get(date.format("DD/MM/YYYY")) ?? []).map(({ post, clock }) => (
                    <Link key={post.video_id} href={`/videos/${post.video_id}`}>
                      <Tag color={POST_STATUS[post.status].color} style={{ whiteSpace: "normal", margin: 0 }}>
                        {clock} {post.title}
                      </Tag>
                    </Link>
                  ))}
                </Flex>
              )
            }
          />
        </div>
      </Card>
    </>
  );
}
