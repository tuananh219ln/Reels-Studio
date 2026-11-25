"use client";

import { api, type PageGate as Gate } from "@/lib/api";
import { Alert, Card, Flex, Progress, Statistic, Typography } from "antd";
import Link from "next/link";
import { useEffect, useState } from "react";

const count = (value: number | null) => (value == null ? "—" : value.toLocaleString("vi-VN"));
const percent = (value: number | null) =>
  value == null
    ? "—"
    : `${(value * 100).toLocaleString("vi-VN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`;

const ALERT: Record<Gate["state"], "info" | "success" | "warning" | "error"> = {
  measuring: "info",
  pass: "success",
  hold: "warning",
  change: "error",
};

/** "Cửa đo 48h" on Quản lý kênh: what a Page's first videos are judged by. Every number is the tool's own reading at
 * 48 hours (the same `48h` readings "list_post_stats" gives), never Facebook's 28-day totals of the cards above. */
export default function PageGate({ pageId }: { pageId: number }) {
  const [gate, setGate] = useState<Gate | null>(null);
  useEffect(() => {
    api<Gate>(`/fanpages/${pageId}/gate`).then(setGate, () => setGate(null));
  }, [pageId]);
  if (!gate) return null;

  return (
    <Card
      size="small"
      title="Cửa đo 48h"
      data-testid="page-gate"
      extra={<Typography.Text type="secondary">Nguồn: tool, đo lúc 48 giờ</Typography.Text>}
    >
      <Flex vertical gap={12}>
        <Alert showIcon type={ALERT[gate.state]} message={gate.state_label} data-testid="gate-state" />
        <Flex wrap gap={32}>
          <Statistic
            title="Trung vị view (tool, 48h)"
            value={count(gate.median_views)}
            suffix={gate.samples ? `/ ${gate.samples} video, 60 ngày` : undefined}
          />
          <Statistic title="Trung vị share/view (tool, 48h)" value={percent(gate.median_share_rate)} />
          <Statistic title="View 48h cao nhất (tool)" value={count(gate.top_views)} />
          <div data-testid="gate-progress">
            <Typography.Text type="secondary">Đã đo đủ 48h</Typography.Text>
            <div>
              <Typography.Text strong style={{ fontSize: 24 }}>
                {gate.measured}
              </Typography.Text>
              <Typography.Text type="secondary">
                {" "}
                / {gate.first} / {gate.last} video
              </Typography.Text>
            </div>
            <Progress
              percent={Math.min(100, Math.round((gate.measured / gate.last) * 100))}
              steps={gate.last / 2}
              size="small"
              showInfo={false}
            />
          </div>
        </Flex>
        <Flex vertical>
          <Typography.Text type="secondary">{gate.rules.pass}.</Typography.Text>
          <Typography.Text type="secondary">{gate.rules.change}.</Typography.Text>
          <Typography.Text type="secondary">{gate.rules.winner}.</Typography.Text>
        </Flex>
        <div data-testid="gate-winners">
          <Typography.Text strong>Video winner</Typography.Text>
          {gate.winners.length === 0 ? (
            <div>
              <Typography.Text type="secondary">Chưa có video nào.</Typography.Text>
            </div>
          ) : (
            gate.winners.map((winner) => (
              <div key={winner.post_id}>
                <Link prefetch={false} href={`/videos/${winner.video.id}`}>
                  {winner.video.title}
                </Link>{" "}
                <Typography.Text type="secondary">
                  {count(winner.views_48h)} view 48h, gấp {winner.times_median}× trung vị
                </Typography.Text>
              </div>
            ))
          )}
        </div>
      </Flex>
    </Card>
  );
}
