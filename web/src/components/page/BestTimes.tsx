"use client";

import { formatNumber } from "@/components/page/Figures";
import { api, type BestHours, type BestTimes as Best } from "@/lib/api";
import { Card, Flex, Typography } from "antd";
import { useEffect, useState } from "react";

const hourText = (hour: number) => `${String(hour).padStart(2, "0")}:00`;

function Hours({ title, best, min }: { title: string; best: BestHours; min: number }) {
  return (
    <Flex vertical gap={2}>
      <Typography.Text strong>{title}</Typography.Text>
      {best.enough && best.hours.length > 0 ? (
        best.hours.map((row) => (
          <Typography.Text key={row.hour} style={{ fontSize: 13 }}>
            {hourText(row.hour)}: trung bình {formatNumber(row.average_views)} lượt xem ({row.posts} bài)
          </Typography.Text>
        ))
      ) : (
        <Typography.Text type="secondary" style={{ fontSize: 13 }}>
          {best.enough
            ? "Chưa có khung giờ nào có từ 2 bài để so."
            : `Mới có ${best.posts} bài đã đo, cần từ ${min} bài mới gợi ý được.`}
        </Typography.Text>
      )}
    </Flex>
  );
}

/** "Giờ đăng hiệu quả": the hours (Vietnam time) the Page's posts of the last 90 days were watched most on each
 * platform, to help choose its posting times. A hint from the Page's own posts, not a rule. */
export default function BestTimes({ pageId }: { pageId: number }) {
  const [best, setBest] = useState<Best | null>(null);
  useEffect(() => {
    api<Best>(`/fanpages/${pageId}/best-times`).then(setBest, () => undefined);
  }, [pageId]);
  if (best === null) return null;
  return (
    <Card size="small" title="Giờ đăng hiệu quả, 90 ngày gần nhất" data-testid="best-times">
      <Flex gap={32} wrap>
        <Hours title="Facebook" best={best.facebook} min={best.min_posts} />
        {best.instagram && <Hours title="Instagram" best={best.instagram} min={best.min_posts} />}
      </Flex>
      <Typography.Text type="secondary" style={{ display: "block", marginTop: 8, fontSize: 12 }}>
        Tính từ lượt xem mới nhất của các bài app đăng, theo giờ Việt Nam lúc bài lên. Gợi ý để chọn giờ đăng của Page,
        vài bài trên một khung giờ chưa phải kết luận.
      </Typography.Text>
    </Card>
  );
}
