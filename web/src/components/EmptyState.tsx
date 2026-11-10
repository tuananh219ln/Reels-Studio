"use client";

import { Empty } from "antd";

/** Every empty list or panel looks the same: antd's small grey drawing, one line saying why it is empty, and the
 * action that fills it when there is one ("Tạo video"). A filtered list that is empty says the filter is why. */
export default function EmptyState({
  description,
  action,
  children,
}: {
  description: React.ReactNode;
  action?: React.ReactNode;
  children?: React.ReactNode;
}) {
  return (
    <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={description}>
      {action}
      {children}
    </Empty>
  );
}
