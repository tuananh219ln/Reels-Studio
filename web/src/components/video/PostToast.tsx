"use client";

import { CheckOutlined, CloseOutlined } from "@ant-design/icons";
import { Button } from "antd";
import { useEffect } from "react";
import { COLORS } from "@/app/theme";
import { PLATFORM_LABELS } from "@/lib/postResults";
import type { PostOutcome } from "./postRound";

// All out: it goes by itself after this long; with a failure it stays until closed.
const HIDE_MS = 8000;

/**
 * The note after "Đăng lên N nền tảng" ends, fixed at the window's top right (docs/decisions/2026-11-14-publish-panel.md):
 * where it went, one line per failure with "Thử lại", and "Xem chi tiết →" to the "Đăng bài" tab's status card.
 */
export default function PostToast({
  outcomes,
  onOpen,
  onRetry,
  onClose,
}: {
  outcomes: PostOutcome[];
  onOpen: () => void;
  onRetry: (outcome: PostOutcome) => void;
  onClose: () => void;
}) {
  const failed = outcomes.filter((outcome) => !outcome.ok);
  const out = outcomes.filter((outcome) => outcome.ok);
  useEffect(() => {
    if (failed.length > 0) return;
    const timer = setTimeout(onClose, HIDE_MS);
    return () => clearTimeout(timer);
  }, [failed.length, onClose]);

  const names = (list: PostOutcome[]) => list.map((outcome) => PLATFORM_LABELS[outcome.platform]).join(", ");
  const scheduled = out.length > 0 && out.every((outcome) => outcome.scheduled);
  const link = { padding: 0, height: "auto", fontSize: 13, color: COLORS.primary } as const;
  return (
    <div
      role={failed.length > 0 ? "alert" : "status"}
      data-testid="post-toast"
      style={{
        position: "fixed",
        top: 16,
        right: 16,
        zIndex: 1010,
        width: 380,
        maxWidth: "calc(100vw - 32px)",
        display: "flex",
        alignItems: "flex-start",
        gap: 10,
        padding: "12px 16px 12px 14px",
        background: "#fff",
        borderLeft: `4px solid ${out.length > 0 ? "#16A34A" : "#E5484D"}`,
        borderRadius: 12,
        boxShadow: "0 4px 16px rgba(0,0,0,.08)",
      }}
    >
      <div style={{ minWidth: 0, flex: 1, display: "flex", flexDirection: "column", gap: 4 }}>
        <div style={{ fontSize: 14, fontWeight: 600, lineHeight: "20px", color: COLORS.text }}>
          {out.length > 0 ? (
            <>
              <CheckOutlined style={{ color: "#16A34A", marginRight: 6 }} />
              {scheduled ? "Đã hẹn giờ trên" : "Đã đăng lên"} {names(out)}
            </>
          ) : (
            "Chưa đăng được"
          )}
        </div>
        {failed.map((outcome) => (
          <div
            key={outcome.platform}
            style={{ fontSize: 13, lineHeight: "18px", color: COLORS.primary }}
            data-testid="post-toast-error"
          >
            {PLATFORM_LABELS[outcome.platform]} lỗi: {outcome.error ?? "không rõ lý do"}
            {outcome.retryJobId !== null && (
              <>
                {" · "}
                <Button
                  type="link"
                  size="small"
                  style={{ ...link, textDecoration: "underline" }}
                  onClick={() => onRetry(outcome)}
                >
                  Thử lại
                </Button>
              </>
            )}
          </div>
        ))}
        <Button type="link" size="small" style={{ ...link, alignSelf: "flex-start" }} onClick={onOpen}>
          Xem chi tiết →
        </Button>
      </div>
      <Button
        type="text"
        size="small"
        aria-label="Đóng"
        icon={<CloseOutlined style={{ fontSize: 12, color: COLORS.textSecondary }} />}
        onClick={onClose}
        style={{ width: 16, height: 16, minWidth: 16, padding: 0 }}
      />
    </div>
  );
}
