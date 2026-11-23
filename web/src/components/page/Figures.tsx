"use client";

import { countFormat, decimalFormat, percentFormat } from "@/lib/format";
import { ArrowDownOutlined, ArrowUpOutlined, InfoCircleOutlined } from "@ant-design/icons";
import { Card, Flex, Tooltip, Typography, theme } from "antd";
import type { ReactNode } from "react";
import type { DashboardFigure } from "@/lib/api";

const count = countFormat;
const percent = percentFormat;
const decimal = decimalFormat;

export function formatNumber(value: number | null): string {
  return value === null ? "—" : count.format(value);
}

export function formatSeconds(value: number | null): string {
  return value === null ? "—" : `${decimal.format(value)} giây`;
}

/** "↑ 25%" or "↓ 4%" against the period before, with an arrow so the direction is never colour alone; nothing to
 * compare says so. */
export function Change({ change, days }: { change: number | null; days: number }) {
  const { token } = theme.useToken();
  if (change === null) {
    return (
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        Chưa có {days} ngày trước để so
      </Typography.Text>
    );
  }
  const up = change > 0;
  const flat = change === 0;
  return (
    <Typography.Text
      style={{
        fontSize: 12,
        color: flat ? token.colorTextSecondary : up ? token.colorSuccessText : token.colorErrorText,
      }}
      data-testid="figure-change"
    >
      {!flat && (up ? <ArrowUpOutlined /> : <ArrowDownOutlined />)} {percent.format(Math.abs(change))}{" "}
      <span style={{ color: token.colorTextSecondary }}>so với {days} ngày trước</span>
    </Typography.Text>
  );
}

/** A KPI tile: its name (with a tip when the number needs one), the value and its change. */
export function FigureTile({
  title,
  figure,
  days,
  format = formatNumber,
  tip,
  note,
}: {
  title: string;
  figure: DashboardFigure;
  days: number;
  format?: (value: number | null) => string;
  tip?: ReactNode;
  note?: ReactNode;
}) {
  return (
    <Card size="small" data-testid="figure-tile" style={{ height: "100%" }}>
      <Flex vertical gap={2}>
        <Typography.Text type="secondary" style={{ fontSize: 13 }}>
          {title}
          {tip && (
            <Tooltip title={tip}>
              <InfoCircleOutlined style={{ marginLeft: 6 }} aria-label={`Giải thích ${title}`} />
            </Tooltip>
          )}
        </Typography.Text>
        <Typography.Text strong style={{ fontSize: 24, lineHeight: "32px" }}>
          {format(figure.value)}
        </Typography.Text>
        <Change change={figure.change} days={days} />
        {note && (
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {note}
          </Typography.Text>
        )}
      </Flex>
    </Card>
  );
}

/** Tiles side by side, as many per row as fit. */
export function TileRow({ children }: { children: ReactNode }) {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 200px), 1fr))",
        gap: 12,
      }}
    >
      {children}
    </div>
  );
}

/** One number of a Page card, small: the value over its label, with an optional note after the value. */
export function MiniFigure({ label, value, note }: { label: string; value: string; note?: ReactNode }) {
  return (
    <Flex vertical gap={0} style={{ minWidth: 0 }}>
      <Typography.Text strong style={{ fontSize: 15, lineHeight: "22px" }}>
        {value}
        {note}
      </Typography.Text>
      <Typography.Text type="secondary" style={{ fontSize: 12 }} ellipsis>
        {label}
      </Typography.Text>
    </Flex>
  );
}

/** "+12" after the followers, this week's gain; nothing until there is a number from last week. */
export function FollowerGain({ gain }: { gain: number | null }) {
  if (!gain) return null;
  return (
    <Typography.Text type={gain > 0 ? "success" : "secondary"} style={{ fontSize: 12, fontWeight: 400, marginLeft: 4 }}>
      {gain > 0 ? "+" : ""}
      {countFormat.format(gain)}
    </Typography.Text>
  );
}
