"use client";

import { Flex, Typography } from "antd";
import type { ReactNode } from "react";

/** The top of every "Cấu hình" tab: its name, a line on what it sets, and its main actions on the right. */
export function SettingsHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <Flex wrap gap={12} justify="space-between" align="flex-start" style={{ marginBottom: 20 }}>
      <Flex vertical gap={4} style={{ minWidth: 0, flex: "1 1 360px" }}>
        <Typography.Title level={4} style={{ margin: 0 }}>
          {title}
        </Typography.Title>
        <Typography.Text type="secondary" style={{ maxWidth: 760 }}>
          {description}
        </Typography.Text>
      </Flex>
      {actions && (
        <Flex wrap gap={8} align="center">
          {actions}
        </Flex>
      )}
    </Flex>
  );
}

/** One group inside a tab: a heading, a line on what it is for, then its cards. */
export function SettingsSection({
  title,
  description,
  children,
}: {
  title: string;
  description?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section>
      <Typography.Title level={5} style={{ margin: 0 }}>
        {title}
      </Typography.Title>
      {description && (
        <Typography.Paragraph type="secondary" style={{ margin: "2px 0 0", maxWidth: 760 }}>
          {description}
        </Typography.Paragraph>
      )}
      <div style={{ marginTop: 12 }}>{children}</div>
    </section>
  );
}
