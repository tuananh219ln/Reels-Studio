import { Card, Flex, Typography } from "antd";
import Logo from "./Logo";

export default function CenteredCard({
  title,
  subtitle,
  footer,
  children,
}: {
  title: string;
  subtitle: string;
  footer?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <Flex justify="center" align="center" style={{ minHeight: "100vh", padding: "48px 16px", boxSizing: "border-box" }}>
      <Flex vertical gap={24} style={{ width: "100%", maxWidth: 400 }}>
        <Flex justify="center">
          <Logo size={20} />
        </Flex>
        <Card>
          <Typography.Title level={3} style={{ marginTop: 0, marginBottom: 4 }}>
            {title}
          </Typography.Title>
          <Typography.Paragraph type="secondary">{subtitle}</Typography.Paragraph>
          {children}
        </Card>
        {footer}
      </Flex>
    </Flex>
  );
}
