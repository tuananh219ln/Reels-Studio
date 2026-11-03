"use client";

import { Card, Col, Row, Statistic, Typography } from "antd";
import { useEffect, useState } from "react";
import { api, type PostKpis as Kpis, type WeekKpis } from "@/lib/api";
import { formatCount, formatRate } from "@/components/PostMetrics";

/** "02/11", the Monday a week starts on (already a Vietnam date from the api). */
function dayMonth(iso: string): string {
  const [, month, day] = iso.split("-");
  return `${day}/${month}`;
}

function goalLine(week: WeekKpis): string {
  return week.share_goal_rate === null ? "—" : `${week.share_goal_met} bài (${formatRate(week.share_goal_rate)})`;
}

/** The KPI strip of "Bài đăng": this week against last, Monday to Sunday in Vietnam time, from the posts' 48-hour
 * numbers. `version` changes when the posts were reloaded, so the strip reads its numbers again. A failure leaves
 * the strip out: the list below it still works. */
export default function PostKpis({ version }: { version: unknown }) {
  const [kpis, setKpis] = useState<Kpis | null>(null);

  useEffect(() => {
    api<Kpis>("/posts/kpis")
      .then(setKpis)
      .catch(() => setKpis(null));
  }, [version]);

  if (!kpis) return null;
  const { this_week: week, last_week: last, rules } = kpis;
  const before = (text: string) => (
    <Typography.Text type="secondary" style={{ fontSize: 12 }}>
      Tuần trước: {text}
    </Typography.Text>
  );
  const items = [
    { title: "Video đã đo", value: String(week.measured), last: String(last.measured) },
    { title: "View trung vị", value: formatCount(week.median_views), last: formatCount(last.median_views) },
    { title: "Video thắng", value: String(week.winners), last: String(last.winners) },
    {
      title: `Share/view ≥ ${formatRate(rules.share_goal)}`,
      value: goalLine(week),
      last: goalLine(last),
    },
  ];

  return (
    <Card size="small" style={{ marginBottom: 16 }} data-testid="post-kpis">
      <Typography.Text strong>KPI tuần này (từ {dayMonth(week.start)}, số đo ở mốc 48 giờ)</Typography.Text>
      <Row gutter={[16, 12]} style={{ marginTop: 8 }}>
        {items.map((item) => (
          <Col key={item.title} xs={12} md={6}>
            <Statistic title={item.title} value={item.value} styles={{ content: { fontSize: 20 } }} />
            {before(item.last)}
          </Col>
        ))}
      </Row>
      <Typography.Paragraph type="secondary" style={{ margin: "8px 0 0", fontSize: 12 }}>
        {kpis.enough_data
          ? `Video thắng: view ở mốc 48 giờ gấp ${rules.winner_factor}× trung vị của Page (các bài ${rules.median_days} ngày gần nhất).`
          : `Chưa đủ dữ liệu để so trung vị: mỗi Page cần ít nhất ${rules.min_samples} bài đã đo ở mốc 48 giờ.`}
      </Typography.Paragraph>
    </Card>
  );
}
