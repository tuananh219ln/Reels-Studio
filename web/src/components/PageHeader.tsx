import { Flex, Typography } from "antd";
import type { ReactNode } from "react";

/**
 * The top of every page behind the login, laid out one way: the title with the page's main action on its right,
 * a line saying what the page is for, then the page's own search and filters.
 */
export default function PageHeader({
  title,
  description,
  actions,
  children,
}: {
  title: ReactNode;
  description?: ReactNode;
  /** The page's main action (for example "Tạo video"), at the right of the title. */
  actions?: ReactNode;
  /** Search, filters or a legend, on their own row under the title. */
  children?: ReactNode;
}) {
  return (
    <div style={{ marginBottom: 20 }}>
      <Flex wrap gap={12} justify="space-between" align="center">
        <Typography.Title level={3} style={{ margin: 0, fontWeight: 600 }}>
          {title}
        </Typography.Title>
        {actions && (
          <Flex wrap gap={8}>
            {actions}
          </Flex>
        )}
      </Flex>
      {description && (
        <Typography.Paragraph type="secondary" style={{ margin: "6px 0 0", maxWidth: 820 }}>
          {description}
        </Typography.Paragraph>
      )}
      {children && (
        <Flex wrap gap={12} align="center" style={{ marginTop: 16 }}>
          {children}
        </Flex>
      )}
    </div>
  );
}
