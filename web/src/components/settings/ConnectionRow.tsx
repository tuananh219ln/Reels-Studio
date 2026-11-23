"use client";

import { COLORS } from "@/app/theme";
import { Flex, Tag, Typography } from "antd";
import type { ReactNode } from "react";

/** One connection (a Shopee account, a TikTok account, a YouTube channel) as a row, the same wherever the app lists
 * them: the platform as a tag, the name with an optional link out, grey lines under it, a status on the right and the
 * row's actions. Shopee, TikTok and YouTube all use it, so none of them looks like a different kind of thing. */
export default function ConnectionRow({
  platform,
  color,
  title,
  link,
  lines = [],
  status,
  actions,
  testId,
  children,
}: {
  platform: string;
  color?: string;
  title: ReactNode;
  link?: { href: string; label: string };
  lines?: ReactNode[];
  status?: ReactNode;
  actions?: ReactNode;
  testId?: string;
  /** Anything that needs its own line, such as a banner. */
  children?: ReactNode;
}) {
  return (
    <Flex
      vertical
      gap={6}
      data-testid={testId}
      style={{ padding: "12px 16px", borderTop: `1px solid ${COLORS.border}` }}
    >
      <Flex gap={12} align="flex-start" wrap>
        <Flex vertical gap={2} style={{ minWidth: 0, flex: "1 1 280px" }}>
          <Flex gap={8} align="center" wrap>
            <Tag color={color} style={{ margin: 0 }}>
              {platform}
            </Tag>
            <Typography.Text strong>{title}</Typography.Text>
            {link && (
              <a href={link.href} target="_blank" rel="noreferrer">
                {link.label}
              </a>
            )}
          </Flex>
          {lines.map((line, index) => (
            <Typography.Text key={index} type="secondary" style={{ fontSize: 12 }}>
              {line}
            </Typography.Text>
          ))}
        </Flex>
        {status && <div style={{ flex: "none", paddingTop: 2 }}>{status}</div>}
        {actions && (
          <Flex gap={8} wrap align="center" style={{ flex: "none" }}>
            {actions}
          </Flex>
        )}
      </Flex>
      {children}
    </Flex>
  );
}
