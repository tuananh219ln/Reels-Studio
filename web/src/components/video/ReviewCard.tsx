"use client";

import { App, Button, Card, Flex, Typography } from "antd";
import { useState } from "react";
import StatusText from "@/components/StatusText";
import { api, errorMessage, formatDateTime, type ReviewItem, type VideoDetail } from "@/lib/api";
import { useEditor } from "./AutoSaveField";

const VIA: Record<string, string> = {
  web: "trên web",
  muse_chat: "trong chat với Muse",
  telegram: "trên Telegram",
  auto: "tự động (Tự duyệt)",
  legacy: "trước khi có bước duyệt",
};

/**
 * The review gate on a video's "Đăng bài" tab (docs/decisions/2026-11-26-review-gate.md): nothing is scheduled or
 * posted until a member approves the MP4. Shows where the review stands and what stops or warns about approving;
 * "Duyệt" asks first when warnings are left ("Vẫn duyệt"), "Bỏ video" and "Khôi phục" move it out of and back into
 * the waiting list. A new render always goes back to "Chờ duyệt".
 */
export default function ReviewCard({ video }: { video: VideoDetail }) {
  const { modal, message } = App.useApp();
  const editor = useEditor();
  const [busy, setBusy] = useState(false);
  const review = video.review;
  if (!review || !review.enabled || !video.mp4) return null;

  const blockers = review.qc.items.filter((item) => item.level === "blocker");
  const warnings = review.qc.items.filter((item) => item.level === "warn");
  const rendering = video.active_job?.kind === "render";
  const status = review.status;

  async function send(action: "approve" | "reject" | "restore", body: object = {}) {
    setBusy(true);
    try {
      editor.onSaved(await api<VideoDetail>(`/review/${video.id}/${action}`, "POST", body));
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  function approve() {
    if (warnings.length === 0) {
      void send("approve", { acknowledge_qc: true });
      return;
    }
    modal.confirm({
      title: `Còn ${warnings.length} mục chưa đạt`,
      content: <ItemList items={warnings} />,
      okText: "Vẫn duyệt",
      cancelText: "Huỷ",
      onOk: () => send("approve", { acknowledge_qc: true }),
    });
  }

  function reject() {
    modal.confirm({
      title: "Bỏ video này?",
      content: "Video không được đăng. Có thể khôi phục lại sau.",
      okText: "Bỏ video",
      okButtonProps: { danger: true },
      cancelText: "Huỷ",
      onOk: () => send("reject"),
    });
  }

  const tone = status === "approved" ? "success" : status === "rejected" ? "idle" : "warning";
  const label = status === "approved" ? "Đã duyệt" : status === "rejected" ? "Đã bỏ" : "Chờ duyệt";
  const posted = video.post_stage === "scheduled" || video.post_stage === "posted";

  return (
    <Card
      size="small"
      data-testid="review-card"
      data-status={status}
      style={{ borderRadius: 12 }}
      styles={{ body: { padding: 16 } }}
    >
      <Flex vertical gap={10}>
        <Flex align="center" gap={8} wrap>
          <StatusText tone={tone} data-testid="review-status" style={{ fontWeight: 600, fontSize: 15 }}>
            {label}
          </StatusText>
          {status === "approved" && review.approved_at && (
            <Typography.Text type="secondary" style={{ fontSize: 13 }}>
              {review.approved_by ? `${review.approved_by} · ` : ""}
              {formatDateTime(review.approved_at)}
              {review.approved_via ? ` · ${VIA[review.approved_via] ?? review.approved_via}` : ""}
            </Typography.Text>
          )}
        </Flex>
        {status === "pending_review" && (
          <Typography.Text type="secondary" style={{ fontSize: 13 }}>
            Chưa ai duyệt bản MP4 này nên chưa đăng hay hẹn giờ được. Xem video, rồi duyệt hoặc bỏ.
          </Typography.Text>
        )}
        {status === "approved" && !review.can_post && (
          <Typography.Text type="warning" style={{ fontSize: 13 }}>
            Bản MP4 đã đổi sau lần duyệt, hãy render lại rồi duyệt lại.
          </Typography.Text>
        )}
        {status !== "rejected" && review.qc.items.length > 0 && <ItemList items={[...blockers, ...warnings]} />}
        <Flex gap={8} wrap>
          {status === "pending_review" && (
            <>
              <Button
                type="primary"
                loading={busy}
                disabled={blockers.length > 0 || video.locked || rendering}
                onClick={approve}
                data-testid="review-approve"
              >
                ✓ Duyệt
              </Button>
              <Button danger disabled={busy || video.locked} onClick={reject} data-testid="review-reject">
                Bỏ video
              </Button>
            </>
          )}
          {status === "approved" && !posted && (
            <Button disabled={busy || video.locked} onClick={reject}>
              Bỏ video
            </Button>
          )}
          {status === "rejected" && (
            <Button loading={busy} onClick={() => send("restore")} data-testid="review-restore">
              Khôi phục
            </Button>
          )}
        </Flex>
      </Flex>
    </Card>
  );
}

function ItemList({ items }: { items: ReviewItem[] }) {
  return (
    <Flex vertical gap={2} data-testid="review-items">
      {items.map((item, index) => (
        <Typography.Text
          key={`${item.code}-${index}`}
          type={item.level === "blocker" ? "danger" : "warning"}
          style={{ fontSize: 12.5 }}
        >
          {item.level === "blocker" ? "Chặn: " : "Cảnh báo: "}
          {item.message}
        </Typography.Text>
      ))}
    </Flex>
  );
}
