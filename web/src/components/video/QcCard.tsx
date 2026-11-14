"use client";

import { Button, Flex, Popover, Typography } from "antd";
import StatusText, { type StatusTone } from "@/components/StatusText";
import type { QcResult } from "@/lib/api";

type QcStatus = QcResult["status"];

const TONE: Record<QcStatus, StatusTone> = { pass: "success", warn: "warning", fail: "danger" };
// Light fills and borders a step apart, so red, yellow and green read at a glance; the text stays dark on all three.
const TILE: Record<QcStatus, { background: string; border: string }> = {
  fail: { background: "#FFF1F0", border: "#FFA39E" },
  warn: { background: "#FFFBE6", border: "#FFE58F" },
  pass: { background: "#F6FFED", border: "#B7EB8F" },
};
const HINT: Record<QcStatus, string> = {
  fail: "Nên sửa rồi render lại trước khi đăng.",
  warn: "Đăng được, nhưng nên xem lại.",
  pass: "Đạt.",
};
const RANK = { fail: 0, warn: 1, pass: 2 } as const;

/** The QC in the page's header: red or yellow while checks still want a look, green when the MP4 passes; pressing it
 * opens a small list of the checks (worst first), each with its measure and, when it is not green, what to do. The
 * list is only for reading: there is no block of tiles in the side panel. */
export function QcChip({ qc }: { qc: QcResult }) {
  const open = qc.checks.filter((check) => check.status !== "pass").length;
  const checks = [...qc.checks].sort((a, b) => RANK[a.status] - RANK[b.status]);
  return (
    <Popover
      trigger="click"
      placement="bottomLeft"
      title="Kiểm tra MP4"
      content={
        <Flex
          vertical
          gap={6}
          style={{ width: 280 }}
          data-testid="qc-card"
          role="group"
          aria-label="Kiểm tra chất lượng"
        >
          {checks.map((check) => (
            <Flex
              key={check.id + check.label}
              vertical
              data-testid="qc-check"
              data-status={check.status}
              aria-label={`${check.label}: ${check.detail}`}
            >
              <StatusText tone={TONE[check.status]} style={{ fontWeight: 600 }}>
                {check.label}
              </StatusText>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                {check.detail}
                {check.status !== "pass" && ` ${HINT[check.status]}`}
              </Typography.Text>
            </Flex>
          ))}
        </Flex>
      }
    >
      <Button
        size="small"
        type="text"
        data-testid="qc-chip"
        style={{ background: TILE[qc.status].background, border: `1px solid ${TILE[qc.status].border}`, fontSize: 13 }}
      >
        <StatusText tone={TONE[qc.status]}>{open === 0 ? "QC: đạt" : `QC: ${open} mục chưa đạt`}</StatusText>
      </Button>
    </Popover>
  );
}
