"use client";

import { Flex, Popover, Typography } from "antd";
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

/** How many checks still want a look: "2 mục cần sửa", or that the MP4 passes. */
export function QcBadge({ qc }: { qc: QcResult }) {
  const open = qc.checks.filter((check) => check.status !== "pass").length;
  return open === 0 ? (
    <StatusText tone="success" data-testid="qc-badge">
      Đạt chuẩn đăng
    </StatusText>
  ) : (
    <StatusText tone={TONE[qc.status]} data-testid="qc-badge">
      {open} mục cần sửa
    </StatusText>
  );
}

/**
 * The MP4's automatic QC (api qc.py) as a grid of tiles, worst first: each check's name and measure on a red, yellow
 * or green tile; pressing one shows the whole measure and what to do about it.
 */
export default function QcGrid({ qc }: { qc: QcResult }) {
  const checks = [...qc.checks].sort((a, b) => RANK[a.status] - RANK[b.status]);
  return (
    <div
      data-testid="qc-card"
      style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0, 1fr))", gap: 6 }}
      role="group"
      aria-label="Kiểm tra chất lượng"
    >
      {checks.map((check) => (
        <Popover
          key={check.id + check.label}
          trigger="click"
          title={check.label}
          content={
            <Flex vertical gap={4} style={{ maxWidth: 260 }}>
              <Typography.Text>{check.detail}</Typography.Text>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                {HINT[check.status]}
              </Typography.Text>
            </Flex>
          }
        >
          <button
            type="button"
            data-testid="qc-check"
            data-status={check.status}
            aria-label={`${check.label}: ${check.detail}`}
            style={{
              background: TILE[check.status].background,
              border: `1px solid ${TILE[check.status].border}`,
              borderRadius: 8,
              padding: "6px 8px",
              textAlign: "left",
              cursor: "pointer",
              minWidth: 0,
              font: "inherit",
            }}
          >
            <StatusText tone={TONE[check.status]} style={{ fontSize: 12, fontWeight: 600 }}>
              {check.label}
            </StatusText>
            <Typography.Text type="secondary" ellipsis style={{ display: "block", fontSize: 12, marginTop: 2 }}>
              {check.detail}
            </Typography.Text>
          </button>
        </Popover>
      ))}
    </div>
  );
}
