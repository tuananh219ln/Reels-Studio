"use client";

// antd compound components (Typography.Title) are undefined when rendered from a Server Component.
import { Card, Empty, Typography } from "antd";

export default function EmptyPage({ title, description }: { title: string; description: string }) {
  return (
    <>
      <Typography.Title level={2} style={{ marginTop: 0, fontWeight: 600 }}>
        {title}
      </Typography.Title>
      <Card>
        <Empty description={description} />
      </Card>
    </>
  );
}
