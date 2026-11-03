"use client";

import {
  ArrowDownOutlined,
  ArrowUpOutlined,
  EyeOutlined,
  FieldTimeOutlined,
  InfoCircleOutlined,
  ShareAltOutlined,
} from "@ant-design/icons";
import { Card, Col, Flex, Progress, Row, theme, Tooltip, Typography } from "antd";
import { useEffect, useState, type ReactNode } from "react";
import { api, formatDateTime, type PostKpis as Kpis, type PostRow, type WeekKpis } from "@/lib/api";
import { formatCount, formatRate } from "@/components/PostMetrics";
import { COLORS } from "@/app/theme";

const HOUR_MS = 60 * 60 * 1000;

/** "02/11", the Monday a week starts on (already a Vietnam date from the api). */
function dayMonth(iso: string): string {
  const [, month, day] = iso.split("-");
  return `${day}/${month}`;
}

function goalLine(week: WeekKpis): string {
  return week.share_goal_rate === null ? "—" : `${week.share_goal_met} bài (${formatRate(week.share_goal_rate)})`;
}

/** This week's live posts that have no 48-hour numbers yet, and when the first of them reaches 48 hours. */
function waiting(posts: PostRow[], weekStart: string): { count: number; first: string | null } {
  const from = new Date(`${weekStart}T00:00:00+07:00`).getTime();
  const due = posts
    .filter((post) => post.status === "published" && !post.metrics.at_48h && new Date(post.at).getTime() >= from)
    .map((post) => new Date(post.at).getTime() + 48 * HOUR_MS)
    .filter((time) => time > Date.now())
    .sort((a, b) => a - b);
  return { count: due.length, first: due.length > 0 ? formatDateTime(new Date(due[0]).toISOString()) : null };
}

/** How many measured posts each Page has towards a median worth comparing with, Pages still short first. */
function pageSamples(posts: PostRow[]): { page: string; samples: number }[] {
  const byPage = new Map<string, number>();
  for (const post of posts) {
    if (!post.fanpage) continue;
    byPage.set(post.fanpage, Math.max(byPage.get(post.fanpage) ?? 0, post.metrics.analysis.samples));
  }
  return [...byPage.entries()].map(([page, samples]) => ({ page, samples })).sort((a, b) => a.samples - b.samples);
}

/** The KPI strip of "Bài đăng": this week against last, Monday to Sunday in Vietnam time, from the posts' 48-hour
 * numbers, each figure explained on its card, and what each Page still needs before posts can be compared. `posts`
 * (every post, not the filtered ones) changes when the list was reloaded, so the strip reads its numbers again. A
 * failure leaves the strip out: the list below it still works. */
export default function PostKpis({ posts }: { posts: PostRow[] | null }) {
  const [kpis, setKpis] = useState<Kpis | null>(null);

  useEffect(() => {
    api<Kpis>("/posts/kpis")
      .then(setKpis)
      .catch(() => setKpis(null));
  }, [posts]);

  if (!kpis || !posts) return null;
  const { this_week: week, last_week: last, rules } = kpis;
  const pending = waiting(posts, week.start);
  // Why a figure is "—": nothing has reached 48 hours yet, or some posts are on their way.
  const empty =
    pending.count > 0
      ? `${pending.count} bài đang chờ đủ 48 giờ, sớm nhất ${pending.first}`
      : "Chưa có bài nào đủ 48 giờ";
  const items: Item[] = [
    {
      title: "Bài đã đủ 48 giờ",
      help: "Số bài đăng tuần này đã có số view ở mốc 48 giờ",
      icon: <FieldTimeOutlined />,
      value: String(week.measured),
      note: pending.count > 0 ? `Thêm ${pending.count} bài đang chờ, sớm nhất ${pending.first}` : undefined,
      last: String(last.measured),
      now: week.measured,
      before: last.measured,
    },
    {
      title: "View phổ biến / bài",
      help: "Một bài bình thường đạt khoảng chừng này view sau 48 giờ (trung vị)",
      icon: <EyeOutlined />,
      value: formatCount(week.median_views),
      note: week.median_views === null ? empty : undefined,
      last: formatCount(last.median_views),
      now: week.median_views,
      before: last.median_views,
    },
    {
      title: "Bài được chia sẻ tốt",
      help: `Số bài có ≥ ${rules.share_goal * 1000} share trên 1.000 view (mục tiêu ${formatRate(rules.share_goal)})`,
      icon: <ShareAltOutlined />,
      value: week.share_goal_rate === null ? "—" : `${week.share_goal_met} bài`,
      sub: week.share_goal_rate === null ? undefined : `${formatRate(week.share_goal_rate)} số bài`,
      note: week.share_goal_rate === null ? empty : undefined,
      last: goalLine(last),
      now: week.share_goal_rate,
      before: last.share_goal_rate,
    },
  ];

  return (
    <div style={{ marginBottom: 16 }} data-testid="post-kpis">
      <Flex align="center" gap={6} style={{ marginBottom: 8 }}>
        <Typography.Text strong>Hiệu quả tuần này (từ T2 {dayMonth(week.start)})</Typography.Text>
        <Tooltip title="Mọi số đều lấy ở mốc 48 giờ sau khi đăng, để các bài được so cùng độ tuổi. Tuần tính từ thứ Hai, giờ Việt Nam.">
          <InfoCircleOutlined aria-label="Cách tính" style={{ color: COLORS.textSecondary }} />
        </Tooltip>
      </Flex>
      <Row gutter={[12, 12]}>
        {items.map((item) => (
          <Col key={item.title} xs={24} sm={8} style={{ display: "flex" }}>
            <KpiCard item={item} />
          </Col>
        ))}
      </Row>
      <Unlock posts={posts} kpis={kpis} />
    </div>
  );
}

type Item = {
  title: string;
  /** What the figure means, in a grey line under the name. */
  help: string;
  icon: ReactNode;
  value: string;
  /** A grey note beside the figure. */
  sub?: string;
  /** Why the figure is empty or what is still to come. */
  note?: string;
  last: string;
  /** The raw figures, to show whether this week is up or down. */
  now: number | null;
  before: number | null;
};

/** One figure on its own card: an icon, the name and what it means, the figure large, and last week's under it
 * with the change. */
function KpiCard({ item }: { item: Item }) {
  const { token } = theme.useToken();
  return (
    <Card
      size="small"
      data-testid="kpi-card"
      style={{ flex: 1, boxShadow: token.boxShadowTertiary, borderColor: COLORS.border }}
      styles={{ body: { padding: 16, height: "100%" } }}
    >
      <Flex vertical gap={6} style={{ height: "100%" }}>
        <Flex align="flex-start" gap={8}>
          <Flex
            align="center"
            justify="center"
            style={{
              width: 28,
              height: 28,
              borderRadius: 8,
              background: COLORS.primaryBg,
              color: COLORS.primary,
              flex: "none",
            }}
          >
            {item.icon}
          </Flex>
          <Flex vertical style={{ minWidth: 0 }}>
            <Typography.Text strong>{item.title}</Typography.Text>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {item.help}
            </Typography.Text>
          </Flex>
        </Flex>
        <Flex align="baseline" gap={8} wrap>
          <Typography.Text strong style={{ fontSize: 28, lineHeight: 1.2 }}>
            {item.value}
          </Typography.Text>
          {item.sub && (
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {item.sub}
            </Typography.Text>
          )}
        </Flex>
        {item.note && (
          <Typography.Text style={{ fontSize: 12, color: COLORS.primary }} data-testid="kpi-note">
            {item.note}
          </Typography.Text>
        )}
        <Flex align="center" gap={6} wrap style={{ marginTop: "auto" }}>
          <Change now={item.now} before={item.before} />
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            Tuần trước: {item.last}
          </Typography.Text>
        </Flex>
      </Flex>
    </Card>
  );
}

/** ↑ green when this week is above last, ↓ red when below; nothing when equal or either is missing. */
function Change({ now, before }: { now: number | null; before: number | null }) {
  if (now === null || before === null || now === before) return null;
  const up = now > before;
  return (
    <Typography.Text type={up ? "success" : "danger"} style={{ fontSize: 12 }} aria-label={up ? "Tăng" : "Giảm"}>
      {up ? <ArrowUpOutlined /> : <ArrowDownOutlined />}
    </Typography.Text>
  );
}

/** Each Page short of the measured posts its median needs before a post can be compared with it ("Gấp N× trung vị
 * Page"), with how far it is; nothing once every Page has them. */
function Unlock({ posts, kpis }: { posts: PostRow[]; kpis: Kpis }) {
  const { rules } = kpis;
  const short = pageSamples(posts).filter((item) => item.samples < rules.min_samples);
  if (short.length === 0) return null;
  return (
    <Flex wrap align="center" gap="4px 20px" style={{ marginTop: 10 }} data-testid="kpi-unlock">
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        Để so mỗi bài với mức view thường của Page, Page cần {rules.min_samples} bài đã đo trong {rules.median_days}{" "}
        ngày:
      </Typography.Text>
      {short.map((item) => (
        <Flex key={item.page} align="center" gap={8}>
          <Typography.Text style={{ fontSize: 12 }}>{item.page}</Typography.Text>
          <Progress
            steps={rules.min_samples}
            size="small"
            percent={(item.samples / rules.min_samples) * 100}
            format={() => `${item.samples}/${rules.min_samples} bài`}
          />
        </Flex>
      ))}
    </Flex>
  );
}
