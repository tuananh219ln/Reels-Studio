"use client";

import { theme } from "antd";
import type { CSSProperties, ReactNode } from "react";

/** What a status means, which sets its dot: nothing yet, a job running, done, out or waiting, needs a look, failed. */
export type StatusTone = "idle" | "active" | "done" | "success" | "waiting" | "warning" | "danger";

/** A status as a small dot and a word, the way every list in the app shows one, instead of a tinted tag. */
export default function StatusText({
  tone,
  children,
  style,
  ...rest
}: {
  tone: StatusTone;
  children: ReactNode;
  style?: CSSProperties;
  "data-testid"?: string;
  title?: string;
}) {
  const { token } = theme.useToken();
  const dot: Record<StatusTone, string> = {
    idle: token.colorTextQuaternary,
    active: token.colorInfo,
    done: token.colorTextSecondary,
    success: token.colorSuccess,
    waiting: token.colorWarning,
    warning: token.colorWarning,
    danger: token.colorError,
  };
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        whiteSpace: "nowrap",
        color: tone === "danger" ? token.colorErrorText : tone === "warning" ? token.colorWarningText : undefined,
        ...style,
      }}
      {...rest}
    >
      <span aria-hidden style={{ width: 7, height: 7, borderRadius: "50%", background: dot[tone], flex: "none" }} />
      {children}
    </span>
  );
}
