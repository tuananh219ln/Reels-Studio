"use client";

import { Typography } from "antd";
import type { CSSProperties, ReactNode } from "react";

/** A note that is neither an error nor a warning: plain grey text, never a banner (the guideline keeps alerts for what
 * blocks something). */
export default function Hint({ children, style }: { children: ReactNode; style?: CSSProperties }) {
  return (
    <Typography.Text type="secondary" style={{ fontSize: 13, ...style }}>
      {children}
    </Typography.Text>
  );
}
