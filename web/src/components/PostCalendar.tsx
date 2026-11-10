"use client";

import EmptyState from "@/components/EmptyState";
import dayjsGenerateConfig from "@rc-component/picker/generate/dayjs";
import { EyeOutlined, LeftOutlined, RightOutlined } from "@ant-design/icons";
import { Badge, Button, Calendar, Card, Drawer, Flex, Grid, Segmented, Typography, theme } from "antd";
import dayjs, { type Dayjs } from "dayjs";
import "dayjs/locale/vi";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { formatDateTime, type PostRow } from "@/lib/api";
import { POST_STATUS } from "@/lib/postStatus";
import StatusText from "@/components/StatusText";
import VideoThumbnail from "@/components/VideoThumbnail";

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
  for (const post of [...posts].sort((a, b) => Date.parse(a.at) - Date.parse(b.at))) {
    const [day, clock] = formatDateTime(post.at).split(" ");
    days.set(day, [...(days.get(day) ?? []), { post, clock }]);
  }
  return days;
}

const MODE_KEY = "reels-studio.calendar-mode";
const HOUR_PX = 88;
/** The week opens scrolled to this hour, as most posts go out from the morning on. */
const FIRST_HOUR = 6;
const WEEKDAYS = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"];

type Entry = { post: PostRow; clock: string };
type Mode = "day" | "week" | "month";

function capitalize(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function monday(date: Dayjs): Dayjs {
  return date.subtract((date.day() + 6) % 7, "day").startOf("day");
}

/** "2–8 tháng 11, 2026", or across months "30 tháng 11–6 tháng 12, 2026". */
function weekTitle(start: Dayjs): string {
  const end = start.add(6, "day");
  const left = start.month() === end.month() ? `${start.date()}` : `${start.date()} tháng ${start.month() + 1}`;
  const year = start.year() === end.year() ? "" : `, ${start.year()}`;
  return `${left}${year}–${end.date()} tháng ${end.month() + 1}, ${end.year()}`;
}

/**
 * "Lịch" on "Bài đăng": the scheduled and posted reels by their time in Vietnam. On a wide screen a week of hour
 * rows, each reel a small cover with its views ("+N bài khác" when an hour holds more), or a month; on a phone the
 * compact month with a dot a post. Choosing a reel, an hour or a day opens those posts in a drawer, each with its
 * video one click away.
 */
export default function PostCalendar({ posts }: { posts: PostRow[] }) {
  const { token } = theme.useToken();
  const days = useMemo(
    () => byDay(posts.filter((post) => post.status === "scheduled" || post.status === "published")),
    [posts],
  );
  const wide = Grid.useBreakpoint().md ?? true;
  const today = vietnamToday();
  const [cursor, setCursor] = useState<Dayjs>(today);
  const [mode, setMode] = useState<Mode>(() => {
    try {
      const kept = window.localStorage.getItem(MODE_KEY);
      return kept === "day" || kept === "month" ? kept : "week";
    } catch {
      return "week";
    }
  });
  // The drawer's posts: a day, or one hour of it.
  const [shown, setShown] = useState<{ day: Dayjs; hour: number | null } | null>(null);

  function chooseMode(next: Mode) {
    setMode(next);
    try {
      window.localStorage.setItem(MODE_KEY, next);
    } catch {
      // A browser that refuses storage just forgets the choice.
    }
  }

  const of = (day: Dayjs) => days.get(day.format("DD/MM/YYYY")) ?? [];
  const drawerPosts = shown
    ? of(shown.day).filter(({ clock }) => shown.hour === null || Number(clock.slice(0, 2)) === shown.hour)
    : [];

  function choose(date: Dayjs, source: string) {
    setCursor(date);
    // Changing the month or year in the header picks a date too; only a day itself opens the drawer.
    if (source === "date") {
      setShown({ day: date, hour: null });
    }
  }

  const legend = (
    <Flex gap={16}>
      {(["scheduled", "published"] as const).map((status) => (
        <StatusText key={status} tone={POST_STATUS[status].tone} style={{ fontSize: 13 }}>
          {POST_STATUS[status].label}
        </StatusText>
      ))}
    </Flex>
  );

  const drawer = (
    <Drawer
      open={shown !== null}
      onClose={() => setShown(null)}
      title={
        shown
          ? `Bài đăng ngày ${shown.day.format("DD/MM/YYYY")}${
              shown.hour !== null
                ? `, ${String(shown.hour).padStart(2, "0")}:00–${String(shown.hour + 1).padStart(2, "0")}:00`
                : ""
            }`
          : ""
      }
      size={420}
      data-testid="calendar-drawer"
    >
      {drawerPosts.length === 0 ? (
        <EmptyState description="Không có bài đăng nào" />
      ) : (
        <Flex vertical gap={16}>
          {drawerPosts.map(({ post, clock }) => {
            const views = post.metrics.latest?.views;
            return (
              <Flex key={post.id} gap={12} data-testid="calendar-drawer-post">
                <VideoThumbnail name={post.title} url={post.thumbnail_url} width={56} />
                <Flex vertical gap={2} style={{ minWidth: 0, flex: 1 }}>
                  <Typography.Text strong ellipsis={{ tooltip: post.title }}>
                    {post.title}
                  </Typography.Text>
                  <Typography.Text type="secondary" style={{ fontSize: 13 }}>
                    {clock}
                    {post.fanpage ? `, ${post.fanpage}` : ""}
                  </Typography.Text>
                  <Flex gap={12} align="center" style={{ fontSize: 13 }}>
                    <StatusText tone={POST_STATUS[post.status].tone}>{POST_STATUS[post.status].label}</StatusText>
                    {views != null && (
                      <Typography.Text type="secondary" style={{ fontSize: 13 }}>
                        <EyeOutlined /> {views.toLocaleString("vi-VN")}
                      </Typography.Text>
                    )}
                  </Flex>
                  <Flex gap={12} style={{ marginTop: 4 }}>
                    <Link prefetch={false} href={`/videos/${post.video_id}`}>
                      Mở video
                    </Link>
                    {post.url && (
                      <a href={post.url} target="_blank" rel="noreferrer">
                        Xem Reel
                      </a>
                    )}
                  </Flex>
                </Flex>
              </Flex>
            );
          })}
        </Flex>
      )}
    </Drawer>
  );

  if (!wide) {
    return (
      <Card styles={{ body: { padding: 8 } }}>
        <div style={{ marginBottom: 12 }}>{legend}</div>
        <VietnamCalendar
          fullscreen={false}
          value={cursor}
          onSelect={(date, info) => choose(date, info.source)}
          cellRender={(date, info) => {
            const day = info.type === "date" ? of(date) : [];
            return day.length === 0 ? null : (
              <Flex justify="center" gap={2} data-testid="calendar-dot">
                {day.slice(0, 3).map(({ post }) => (
                  <Badge key={post.id} status={post.status === "published" ? "success" : "warning"} />
                ))}
              </Flex>
            );
          }}
        />
        {drawer}
      </Card>
    );
  }

  const start = monday(cursor);
  const step = mode;
  const toolbar = (
    <Flex justify="space-between" align="center" wrap gap={12} style={{ marginBottom: 16 }}>
      <div>
        <Typography.Title level={4} style={{ margin: 0 }} data-testid="calendar-title">
          {mode === "day"
            ? `${capitalize(cursor.locale("vi").format("dddd"))}, ${cursor.date()} tháng ${cursor.month() + 1}, ${cursor.year()}`
            : mode === "week"
              ? weekTitle(start)
              : `Tháng ${cursor.month() + 1}, ${cursor.year()}`}
        </Typography.Title>
        <Flex gap={16} align="center" style={{ marginTop: 4 }}>
          <Typography.Text type="secondary" style={{ fontSize: 13 }}>
            Giờ Việt Nam
          </Typography.Text>
          {legend}
        </Flex>
      </div>
      <Flex gap={8} align="center">
        <Button icon={<LeftOutlined />} aria-label="Trước" onClick={() => setCursor(cursor.subtract(1, step))} />
        <Button onClick={() => setCursor(today)}>Hôm nay</Button>
        <Button icon={<RightOutlined />} aria-label="Sau" onClick={() => setCursor(cursor.add(1, step))} />
        <Segmented<Mode>
          aria-label="Kiểu lịch"
          value={mode}
          onChange={chooseMode}
          options={[
            { value: "day", label: "Ngày" },
            { value: "week", label: "Tuần" },
            { value: "month", label: "Tháng" },
          ]}
        />
      </Flex>
    </Flex>
  );

  return (
    <Card>
      {toolbar}
      {mode !== "month" ? (
        <WeekGrid
          days={
            mode === "day" ? [cursor.startOf("day")] : Array.from({ length: 7 }, (_, index) => start.add(index, "day"))
          }
          today={today}
          of={of}
          onOpen={(day, hour) => setShown({ day, hour })}
        />
      ) : (
        <div style={{ overflowX: "auto" }}>
          <div style={{ minWidth: 760 }} className="post-month">
            <VietnamCalendar
              value={cursor}
              headerRender={() => null}
              onSelect={(date, info) => choose(date, info.source)}
              cellRender={(date, info) =>
                info.type !== "date" ? null : (
                  // The day's reels open the drawer themselves: a click in a cell that scrolls does not always
                  // reach the calendar's own select.
                  <Flex vertical gap={4} onClick={() => choose(date, "date")} style={{ cursor: "pointer" }}>
                    {of(date)
                      .slice(0, 2)
                      .map((item) => (
                        <MonthChip key={item.post.id} entry={item} />
                      ))}
                    {of(date).length > 2 && <MoreChip entries={of(date).slice(2)} />}
                  </Flex>
                )
              }
            />
          </div>
        </div>
      )}
      {drawer}
      {/* A month's day grows with its two reels and "+N bài khác" instead of scrolling inside a fixed height. */}
      <style>{`.week-slot:hover { background: ${token.colorFillQuaternary}; }
.post-month .ant-picker-calendar-date-content { height: auto !important; min-height: 92px; overflow: visible !important; }`}</style>
    </Card>
  );
}

/** Seven day columns under an hour ruler; each hour shows its first reel as a cover and "+N bài khác" for the rest. */
function WeekGrid({
  days: week,
  today,
  of,
  onOpen,
}: {
  /** Seven days for "Tuần", one for "Ngày". */
  days: Dayjs[];
  today: Dayjs;
  of: (day: Dayjs) => Entry[];
  onOpen: (day: Dayjs, hour: number) => void;
}) {
  const { token } = theme.useToken();
  const scroller = useRef<HTMLDivElement>(null);
  const single = week.length === 1;
  const hours = Array.from({ length: 24 }, (_, hour) => hour);
  useEffect(() => {
    scroller.current?.scrollTo({ top: FIRST_HOUR * HOUR_PX });
  }, []);
  const columns = `52px repeat(${week.length}, minmax(0, 1fr))`;
  return (
    <div style={{ overflowX: "auto" }}>
      <div style={{ minWidth: single ? 0 : 760 }}>
        <div role="row" style={{ display: "grid", gridTemplateColumns: columns, paddingBottom: 8 }}>
          <span />
          {week.map((day, index) => {
            const isToday = day.isSame(today, "day");
            return (
              <div
                key={index}
                role="columnheader"
                title={day.format("YYYY-MM-DD")}
                data-testid={isToday ? "week-today" : undefined}
                style={{
                  textAlign: "center",
                  fontSize: 13,
                  fontWeight: isToday ? 600 : 400,
                  color: isToday ? token.colorPrimary : token.colorTextSecondary,
                }}
              >
                {WEEKDAYS[(day.day() + 6) % 7]} {day.format("DD/MM")}
              </div>
            );
          })}
        </div>
        <div
          ref={scroller}
          style={{ maxHeight: 640, overflowY: "auto", borderTop: `1px solid ${token.colorBorderSecondary}` }}
        >
          {hours.map((hour) => (
            <div key={hour} style={{ display: "grid", gridTemplateColumns: columns, height: HOUR_PX }}>
              <span
                style={{
                  fontSize: 12,
                  color: token.colorTextTertiary,
                  paddingTop: 4,
                  fontVariantNumeric: "tabular-nums",
                }}
              >
                {String(hour).padStart(2, "0")}:00
              </span>
              {week.map((day, index) => {
                const slot = of(day).filter(({ clock }) => Number(clock.slice(0, 2)) === hour);
                return (
                  <div
                    key={index}
                    className={slot.length ? "week-slot" : undefined}
                    onClick={slot.length ? () => onOpen(day, hour) : undefined}
                    style={{
                      borderLeft: `1px solid ${token.colorBorderSecondary}`,
                      borderBottom: `1px solid ${token.colorBorderSecondary}`,
                      background: day.isSame(today, "day") ? token.colorFillQuaternary : undefined,
                      padding: 4,
                      cursor: slot.length ? "pointer" : undefined,
                      minWidth: 0,
                    }}
                  >
                    {/* A single day has room for every reel of the hour side by side. */}
                    {slot.length > 0 &&
                      (single ? (
                        <Flex gap={6} style={{ height: "100%" }}>
                          {slot.map((item) => (
                            <div key={item.post.id} style={{ width: 160, flex: "none" }}>
                              <SlotCard first={item} more={0} />
                            </div>
                          ))}
                        </Flex>
                      ) : (
                        <SlotCard first={slot[0]} more={slot.length - 1} />
                      ))}
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/** An hour's first reel: its cover with the time and views on it, and how many more the hour holds. */
function SlotCard({ first, more }: { first: Entry; more: number }) {
  const { token } = theme.useToken();
  const { post, clock } = first;
  const views = post.metrics.latest?.views;
  const badge = {
    position: "absolute",
    padding: "0 5px",
    borderRadius: 4,
    background: "rgba(0, 0, 0, 0.72)",
    color: "#fff",
    fontSize: 11,
    fontWeight: 600,
    lineHeight: "16px",
    whiteSpace: "nowrap",
  } as const;
  return (
    <div
      data-testid="week-post"
      title={`${clock} ${post.title}`}
      style={{
        position: "relative",
        height: "100%",
        borderRadius: 6,
        overflow: "hidden",
        background: post.thumbnail_url
          ? `center / cover no-repeat url("${post.thumbnail_url}")`
          : token.colorFillSecondary,
        border: `1px solid ${token.colorBorderSecondary}`,
      }}
    >
      {!post.thumbnail_url && (
        <Typography.Text style={{ display: "block", padding: "24px 6px 0", fontSize: 11, lineHeight: "14px" }} ellipsis>
          {post.title}
        </Typography.Text>
      )}
      <span style={{ ...badge, top: 4, left: 4 }}>
        <StatusText tone={POST_STATUS[post.status].tone} style={{ color: "#fff", gap: 4 }}>
          {clock}
        </StatusText>
      </span>
      {views != null && (
        <span style={{ ...badge, bottom: 4, left: 4 }}>
          <EyeOutlined /> {views.toLocaleString("vi-VN")}
        </span>
      )}
      {more > 0 && <span style={{ ...badge, bottom: 4, right: 4 }}>+{more} bài khác</span>}
    </div>
  );
}

/** A reel in a month's day: its small cover and its views, or its time while it waits. */
function MonthChip({ entry }: { entry: Entry }) {
  const { token } = theme.useToken();
  const { post, clock } = entry;
  const views = post.metrics.latest?.views;
  return (
    <Flex
      align="center"
      gap={6}
      data-testid="calendar-post"
      title={`${clock} ${post.title}`}
      style={{
        padding: "3px 6px 3px 3px",
        border: `1px solid ${token.colorBorderSecondary}`,
        borderRadius: 6,
        background: token.colorBgContainer,
        fontSize: 12,
        minWidth: 0,
      }}
    >
      <Cover post={post} size={22} />
      <span style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
        {post.status === "scheduled"
          ? `Hẹn ${clock}`
          : views != null
            ? `${views.toLocaleString("vi-VN")} lượt xem`
            : clock}
      </span>
    </Flex>
  );
}

/** "+N bài khác" after a day's first two reels, with their covers overlapping. */
function MoreChip({ entries }: { entries: Entry[] }) {
  const { token } = theme.useToken();
  return (
    <Flex align="center" gap={6} style={{ padding: "2px 4px", fontSize: 12, color: token.colorTextSecondary }}>
      <Flex>
        {entries.slice(0, 2).map(({ post }, index) => (
          <span
            key={post.id}
            style={{ marginLeft: index ? -8 : 0, borderRadius: 5, outline: `2px solid ${token.colorBgContainer}` }}
          >
            <Cover post={post} size={20} />
          </span>
        ))}
      </Flex>
      +{entries.length} bài khác
    </Flex>
  );
}

/** A reel's square cover, cut from its thumbnail, or a grey square. */
function Cover({ post, size }: { post: PostRow; size: number }) {
  const { token } = theme.useToken();
  return (
    <span
      aria-hidden
      style={{
        display: "inline-block",
        width: size,
        height: size,
        flex: "none",
        borderRadius: 4,
        background: post.thumbnail_url
          ? `center / cover no-repeat url("${post.thumbnail_url}")`
          : token.colorFillSecondary,
      }}
    />
  );
}
