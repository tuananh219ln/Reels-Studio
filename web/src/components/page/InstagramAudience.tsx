"use client";

import { COLORS } from "@/app/theme";
import { formatNumber } from "@/components/page/Figures";
import type { InstagramDashboard } from "@/lib/api";
import { Card, Flex, Typography } from "antd";

const GENDER: Record<string, string> = { F: "Nữ", M: "Nam", U: "Không rõ" };
const percent = new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 1 });

/** The share of followers by one dimension as bars, the biggest first. */
function Shares({
  title,
  rows,
  label = (key) => key,
}: {
  title: string;
  rows: { key: string; share: number }[];
  label?: (key: string) => string;
}) {
  return (
    <Card size="small" title={title} style={{ height: "100%" }}>
      <Flex vertical gap={6}>
        {rows.map((row) => (
          <Flex key={row.key} align="center" gap={8}>
            <Typography.Text style={{ width: 120, flex: "none", fontSize: 13 }} ellipsis={{ tooltip: label(row.key) }}>
              {label(row.key)}
            </Typography.Text>
            <div style={{ flex: 1, height: 8, borderRadius: 4, background: COLORS.selected }}>
              <div
                style={{
                  width: `${Math.min(row.share, 100)}%`,
                  height: "100%",
                  borderRadius: 4,
                  background: COLORS.primary,
                }}
              />
            </div>
            <Typography.Text style={{ width: 48, textAlign: "right", fontSize: 13 }}>
              {percent.format(row.share)}%
            </Typography.Text>
          </Flex>
        ))}
      </Flex>
    </Card>
  );
}

/** The Instagram "Đối tượng": the followers now and who they are (gender, age, city), read at each Page check. Instagram
 * gives the audience only to an account with 100 followers or more, and says so when it is not there. */
export default function InstagramAudience({ data }: { data: InstagramDashboard }) {
  const audience = data.audience;
  return (
    <Flex vertical gap={12} data-testid="instagram-audience">
      <Card size="small">
        <Flex vertical gap={2}>
          <Typography.Text type="secondary" style={{ fontSize: 13 }}>
            Người theo dõi hiện có
          </Typography.Text>
          <Typography.Text strong style={{ fontSize: 24, lineHeight: "32px" }}>
            {formatNumber(data.followers)}
          </Typography.Text>
        </Flex>
      </Card>
      {audience ? (
        <div
          style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 300px), 1fr))", gap: 12 }}
        >
          {audience.gender && <Shares title="Giới tính" rows={audience.gender} label={(key) => GENDER[key] ?? key} />}
          {audience.age && <Shares title="Độ tuổi" rows={audience.age} />}
          {audience.city && (
            <Shares
              title="Thành phố hàng đầu"
              rows={audience.city.slice(0, 8)}
              label={(key) => key.replace(", Vietnam", "")}
            />
          )}
        </div>
      ) : (
        <Typography.Text type="secondary" data-testid="audience-missing">
          {data.audience_error ?? "Chưa đọc được đối tượng: tool đọc ở mỗi lần kiểm tra token"}
        </Typography.Text>
      )}
      {audience && (
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          Tỉ lệ tính trên số người theo dõi Instagram cho xem; thành phố chỉ gồm các thành phố đứng đầu.
        </Typography.Text>
      )}
    </Flex>
  );
}
