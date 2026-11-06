"use client";

import { Card, Flex, Typography } from "antd";
import StatusText, { type StatusTone } from "@/components/StatusText";
import type { QcResult } from "@/lib/api";

const TONE: Record<QcResult["status"], StatusTone> = { pass: "success", warn: "warning", fail: "danger" };
const SUMMARY: Record<QcResult["status"], string> = {
  pass: "Đạt chuẩn đăng",
  warn: "Đăng được, nên xem lại",
  fail: "Chưa đạt, nên sửa rồi render lại",
};

/** The MP4's automatic QC (api qc.py): each check with its measure, the worst one first in the title. */
export default function QcCard({ qc }: { qc: QcResult | null }) {
  if (!qc) return null;
  const rank = { fail: 0, warn: 1, pass: 2 } as const;
  const checks = [...qc.checks].sort((a, b) => rank[a.status] - rank[b.status]);
  return (
    <Card
      size="small"
      data-testid="qc-card"
      title={
        <Flex gap={8} align="center" wrap>
          <span>Kiểm tra chất lượng</span>
          <StatusText tone={TONE[qc.status]}>{SUMMARY[qc.status]}</StatusText>
        </Flex>
      }
    >
      <Flex vertical gap={6}>
        {checks.map((check) => (
          <Flex key={check.id + check.label} gap={8} align="baseline" wrap>
            <StatusText tone={TONE[check.status]}>{check.label}</StatusText>
            <Typography.Text type="secondary">{check.detail}</Typography.Text>
          </Flex>
        ))}
      </Flex>
    </Card>
  );
}
