"use client";

import { formatNumber } from "@/components/page/Figures";
import { api, errorMessage, type BestHours, type BestTimes as Best } from "@/lib/api";
import { zoneName } from "@/lib/scheduleZone";
import { App, Button, Card, Flex, Typography } from "antd";
import { useEffect, useState } from "react";

const hourText = (hour: number) => `${String(hour).padStart(2, "0")}:00`;

function Hours({
  title,
  best,
  min,
  taken,
  onApply,
}: {
  title: string;
  best: BestHours;
  min: number;
  taken: string[];
  onApply: (hour: number) => void;
}) {
  return (
    <Flex vertical gap={2}>
      <Typography.Text strong>{title}</Typography.Text>
      {best.enough && best.hours.length > 0 ? (
        best.hours.map((row) => (
          <Typography.Text key={row.hour} style={{ fontSize: 13 }}>
            {hourText(row.hour)}: trung bình {formatNumber(row.average_views)} lượt xem ({row.posts} bài){" "}
            {taken.includes(hourText(row.hour)) ? (
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                đã có trong giờ đăng
              </Typography.Text>
            ) : (
              <Button size="small" type="link" onClick={() => onApply(row.hour)}>
                Thêm vào giờ đăng
              </Button>
            )}
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

/** "Giờ đăng hiệu quả": the hours (in the Page's schedule zone) the Page's posts of the last 90 days were watched most on each
 * platform, to help choose its posting times. A hint from the Page's own posts, not a rule. */
export default function BestTimes({ pageId }: { pageId: number }) {
  const { message } = App.useApp();
  const [best, setBest] = useState<Best | null>(null);
  useEffect(() => {
    api<Best>(`/fanpages/${pageId}/best-times`).then(setBest, () => undefined);
  }, [pageId]);
  if (best === null) return null;
  const zone = best.timezone;

  /** Adds the hour to the Page's own times, in the zone the hours are read in; only the Page's owner can. */
  async function apply(hour: number) {
    if (best === null) return;
    try {
      await api(`/queue/pages/${pageId}`, "PATCH", {
        post_times: [...best.post_times, hourText(hour)],
        schedule_timezone: zone,
      });
      setBest({ ...best, post_times: [...best.post_times, hourText(hour)].sort() });
      message.success(`Đã thêm ${hourText(hour)} (${zoneName(zone)}) vào giờ đăng`);
    } catch (err) {
      message.error(errorMessage(err));
    }
  }
  return (
    <Card size="small" title={`Giờ đăng hiệu quả, 90 ngày gần nhất (${zoneName(zone)})`} data-testid="best-times">
      <Flex gap={32} wrap>
        <Hours title="Facebook" best={best.facebook} min={best.min_posts} taken={best.post_times} onApply={apply} />
        {best.instagram && (
          <Hours title="Instagram" best={best.instagram} min={best.min_posts} taken={best.post_times} onApply={apply} />
        )}
      </Flex>
      <Typography.Text type="secondary" style={{ display: "block", marginTop: 8, fontSize: 12 }}>
        Tính từ lượt xem mới nhất của các bài app đăng, theo {zoneName(zone)} lúc bài lên (cùng một giờ tường vẫn gom
        chung khi Mỹ đổi giờ). Gợi ý để chọn giờ đăng của Page, vài bài trên một khung giờ chưa phải kết luận.
      </Typography.Text>
    </Card>
  );
}
