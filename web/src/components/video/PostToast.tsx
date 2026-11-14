"use client";

import { CheckOutlined, CloseOutlined } from "@ant-design/icons";
import { Button, Typography } from "antd";
import { useEffect, useLayoutEffect, useState } from "react";
import { PLATFORM_LABELS } from "@/lib/postResults";
import type { PostOutcome } from "./postRound";

// All out: it goes by itself after this long; with a failure it stays until closed.
const HIDE_MS = 7000;

/**
 * The note after "Đăng lên N nền tảng" ends, top right beside the side panel's tabs: its right edge on the header's
 * "Render" button, its bottom 8 px above the tabs' line, so it covers no word of either. A click on it opens the
 * "Đăng bài" tab's status card; "Thử lại" sends a failed platform again.
 */
export default function PostToast({
  outcomes,
  right,
  onOpen,
  onRetry,
  onClose,
}: {
  outcomes: PostOutcome[];
  /** The page's own right padding, where the header's buttons end. */
  right: number;
  onOpen: () => void;
  onRetry: (outcome: PostOutcome) => void;
  onClose: () => void;
}) {
  const failed = outcomes.filter((outcome) => !outcome.ok);
  const out = outcomes.filter((outcome) => outcome.ok);
  // Where the tabs' line is, read when the note shows and again on scroll and resize.
  const [line, setLine] = useState<number | null>(null);
  useLayoutEffect(() => {
    const measure = () => {
      const nav = document.querySelector(".side-panel .side-tabs > .ant-tabs-nav");
      const rect = nav?.getBoundingClientRect();
      setLine(rect && rect.height > 0 ? rect.bottom : null);
    };
    measure();
    window.addEventListener("resize", measure);
    window.addEventListener("scroll", measure, true);
    return () => {
      window.removeEventListener("resize", measure);
      window.removeEventListener("scroll", measure, true);
    };
  }, []);
  useEffect(() => {
    if (failed.length > 0) return;
    const timer = setTimeout(onClose, HIDE_MS);
    return () => clearTimeout(timer);
  }, [failed.length, onClose]);

  const names = (list: PostOutcome[]) => list.map((outcome) => PLATFORM_LABELS[outcome.platform]).join(", ");
  const scheduled = out.length > 0 && out.every((outcome) => outcome.scheduled);
  return (
    <div
      role="status"
      data-testid="post-toast"
      onClick={onOpen}
      style={{
        position: "fixed",
        right,
        // Without the tabs (the panel is a closed drawer), under the top of the window.
        ...(line !== null ? { top: line - 8, transform: "translateY(-100%)" } : { top: 72 }),
        zIndex: 1010,
        display: "flex",
        alignItems: "flex-start",
        gap: 10,
        maxWidth: "min(480px, calc(100vw - 32px))",
        padding: "7px 12px",
        background: "#fff",
        borderLeft: `4px solid ${failed.length && !out.length ? "#c2410c" : "#16a34a"}`,
        borderRadius: 10,
        boxShadow: "0 8px 24px rgba(0,0,0,.13)",
        cursor: "pointer",
      }}
    >
      <div style={{ minWidth: 0 }}>
        {out.length > 0 ? (
          <Typography.Text strong style={{ fontSize: 13, display: "block" }}>
            <CheckOutlined style={{ color: "#16a34a", marginRight: 6 }} />
            {scheduled ? "Đã hẹn giờ trên" : "Đã đăng lên"} {names(out)}
          </Typography.Text>
        ) : (
          <Typography.Text strong style={{ fontSize: 13, display: "block" }}>
            Chưa đăng được
          </Typography.Text>
        )}
        {failed.map((outcome) => (
          <div key={outcome.platform} style={{ fontSize: 12, color: "#c2410c" }} data-testid="post-toast-error">
            {PLATFORM_LABELS[outcome.platform]} lỗi: {outcome.error ?? "không rõ lý do"}
            {outcome.retryJobId !== null && (
              <>
                {" · "}
                <Button
                  type="link"
                  size="small"
                  style={{ padding: 0, height: "auto", fontSize: 12, color: "#c2410c", fontWeight: 600 }}
                  onClick={(event) => {
                    event.stopPropagation();
                    onRetry(outcome);
                  }}
                >
                  Thử lại
                </Button>
              </>
            )}
          </div>
        ))}
      </div>
      <Button
        type="text"
        size="small"
        aria-label="Đóng thông báo"
        icon={<CloseOutlined />}
        onClick={(event) => {
          event.stopPropagation();
          onClose();
        }}
      />
    </div>
  );
}
