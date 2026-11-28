"use client";

import { api, errorMessage } from "@/lib/api";
import { CloseOutlined, DeleteOutlined } from "@ant-design/icons";
import { Alert, App, Button, Flex, Input, Modal, Spin, Typography } from "antd";
import { useCallback, useEffect, useRef, useState } from "react";

/** From this many videos actually deleted, the member types the number to confirm. */
export const TYPE_TO_CONFIRM = 20;
/** What the api takes at a time (api routes_video_bulk.MAX_IDS). */
const CHUNK = 500;

export type Skipped = { id: number; reason: string };
type Preview = { count: number; scheduled: number; published: number; rendering: number; forbidden: number };

const SKIPPED_WORDS: Record<string, string> = {
  published: "đã đăng",
  rendering: "đang render hoặc đang chạy job",
  forbidden: "không phải của bạn hoặc có bài/góp ý của người khác",
  missing: "đã bị xóa trước đó",
  error: "lỗi khi xóa",
};

function chunks<T>(items: T[]): T[][] {
  const out: T[][] = [];
  for (let at = 0; at < items.length; at += CHUNK) out.push(items.slice(at, at + CHUNK));
  return out;
}

/** The videos ticked on a list: one set of ids, kept across pages. `toggle` with `shift` ticks or unticks the whole
 * stretch from the one ticked before it to this one, in the order of `order`. */
export function useVideoSelection() {
  const [ids, setIds] = useState<Set<number>>(new Set());
  // "Chọn tất cả N video khớp bộ lọc" was pressed: deleting then asks to type the number.
  const [matchAll, setMatchAll] = useState(false);
  const last = useRef<number | null>(null);
  const clear = useCallback(() => {
    setIds(new Set());
    setMatchAll(false);
    last.current = null;
  }, []);
  const setMany = useCallback((rows: number[], checked: boolean) => {
    setIds((prev) => {
      const next = new Set(prev);
      for (const id of rows) {
        if (checked) next.add(id);
        else next.delete(id);
      }
      return next;
    });
  }, []);
  const toggle = useCallback(
    (id: number, checked: boolean, shift: boolean, order: number[]) => {
      const from = last.current === null ? -1 : order.indexOf(last.current);
      const to = order.indexOf(id);
      if (shift && from >= 0 && to >= 0) {
        setMany(order.slice(Math.min(from, to), Math.max(from, to) + 1), checked);
      } else {
        setMany([id], checked);
      }
      last.current = id;
    },
    [setMany],
  );
  const flip = useCallback((rows: number[]) => {
    setIds((prev) => {
      const next = new Set(prev);
      for (const id of rows) {
        if (!next.delete(id)) next.add(id);
      }
      return next;
    });
  }, []);
  const selectAll = useCallback((all: number[]) => {
    setIds(new Set(all));
    setMatchAll(true);
  }, []);
  return { ids, matchAll, clear, setMany, toggle, flip, selectAll };
}

/** The bar at the foot of the screen while videos are ticked; `actions` are its buttons, so other bulk actions can
 * be added later. Esc unticks everything. */
export function BulkActionBar({
  count,
  onClear,
  actions,
}: {
  count: number;
  onClear: () => void;
  actions: { key: string; label: string; icon?: React.ReactNode; danger?: boolean; onClick: () => void }[];
}) {
  return (
    <Flex
      data-testid="bulk-bar"
      align="center"
      gap={12}
      style={{
        position: "fixed",
        left: "50%",
        bottom: 20,
        transform: "translateX(-50%)",
        zIndex: 100,
        padding: "8px 8px 8px 16px",
        maxWidth: "calc(100vw - 32px)",
        borderRadius: 10,
        background: "var(--ant-color-bg-elevated, #fff)",
        border: "1px solid var(--ant-color-border, #d9d9d9)",
        boxShadow: "0 6px 20px rgba(0, 0, 0, 0.18)",
      }}
    >
      <Button type="text" size="small" icon={<CloseOutlined />} aria-label="Bỏ chọn" onClick={onClear} />
      <Typography.Text strong>Đã chọn {count} video</Typography.Text>
      <Button size="small" onClick={onClear}>
        Bỏ chọn
      </Button>
      {actions.map((action) => (
        <Button
          key={action.key}
          size="small"
          danger={action.danger}
          type={action.danger ? "primary" : "default"}
          icon={action.icon}
          onClick={action.onClick}
        >
          {action.label}
        </Button>
      ))}
    </Flex>
  );
}

/** "Xóa" in the bar: asks the api what would go, then deletes for good the videos that may. `ids` must keep its
 * identity while the selection does not change (useMemo), as a new array asks the api again. Mounted only while it is
 * open, so each opening starts fresh. */
export function BulkDeleteDialog({
  ids,
  matchAll,
  onClose,
  onDone,
}: {
  ids: number[];
  matchAll: boolean;
  onClose: () => void;
  onDone: (result: { deleted: number; skipped: Skipped[] }) => void;
}) {
  const { message } = App.useApp();
  const [preview, setPreview] = useState<Preview | null>(null);
  const [failed, setFailed] = useState(false);
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let current = true;
    (async () => {
      try {
        const sum: Preview = { count: 0, scheduled: 0, published: 0, rendering: 0, forbidden: 0 };
        for (const part of chunks(ids)) {
          const one = await api<Preview>("/video-bulk/delete/preview", "POST", { ids: part });
          for (const key of Object.keys(sum) as (keyof Preview)[]) sum[key] += one[key];
        }
        if (current) setPreview(sum);
      } catch (err) {
        if (current) {
          setFailed(true);
          message.error(errorMessage(err));
        }
      }
    })();
    return () => {
      current = false;
    };
  }, [ids, message]);

  async function remove() {
    setBusy(true);
    let deleted = 0;
    const skipped: Skipped[] = [];
    try {
      for (const part of chunks(ids)) {
        const done = await api<{ deleted: number; skipped: Skipped[] }>("/video-bulk/delete", "POST", { ids: part });
        deleted += done.deleted;
        skipped.push(...done.skipped);
      }
    } catch (err) {
      // What went before stays deleted; the list shows it, and the rest stays ticked to try again.
      message.error(errorMessage(err));
      if (deleted > 0 || skipped.length > 0) onDone({ deleted, skipped });
      setBusy(false);
      return;
    }
    setBusy(false);
    onDone({ deleted, skipped });
  }

  const count = preview?.count ?? 0;
  const skippedCount = preview ? preview.published + preview.rendering + preview.forbidden : 0;
  const needsTyping = count >= TYPE_TO_CONFIRM || (matchAll && count > 0);
  const typedRight = !needsTyping || typed.trim() === String(count);
  const skippedParts = preview
    ? [
        preview.published && `${preview.published} ${SKIPPED_WORDS.published} (giữ lại để làm báo cáo view)`,
        preview.rendering && `${preview.rendering} ${SKIPPED_WORDS.rendering}`,
        preview.forbidden && `${preview.forbidden} ${SKIPPED_WORDS.forbidden}`,
      ].filter(Boolean)
    : [];
  return (
    <Modal
      open
      title={preview && count === 0 ? "Không có video nào xóa được" : `Xóa ${preview ? count : "…"} video?`}
      onCancel={busy ? undefined : onClose}
      closable={!busy}
      maskClosable={!busy}
      keyboard={!busy}
      okText={`Xóa ${count} video`}
      cancelText="Huỷ"
      okButtonProps={{ danger: true, disabled: !preview || count === 0 || !typedRight, loading: busy }}
      cancelButtonProps={{ disabled: busy }}
      onOk={() => void remove()}
      destroyOnHidden
    >
      <div data-testid="bulk-delete-dialog">
        {!preview && !failed && <Spin />}
        {failed && <Typography.Text type="danger">Không kiểm tra được, hãy đóng và thử lại.</Typography.Text>}
        {preview && count > 0 && (
          <Typography.Paragraph>
            Xóa hẳn các video, cảnh, job và mọi file (ảnh, MP4, ảnh thu nhỏ). Không khôi phục được.
          </Typography.Paragraph>
        )}
        {preview && preview.scheduled > 0 && (
          <Alert
            type="warning"
            showIcon
            style={{ marginBottom: 8 }}
            message={`${preview.scheduled} video đã hẹn giờ đăng: lịch đăng sẽ bị hủy.`}
          />
        )}
        {skippedParts.length > 0 && (
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 8 }}
            message={`${skippedCount} video sẽ được bỏ qua: ${skippedParts.join(", ")}.`}
          />
        )}
        {preview && needsTyping && (
          <>
            <Typography.Paragraph style={{ marginBottom: 4 }}>
              Gõ số <strong>{count}</strong> để xác nhận:
            </Typography.Paragraph>
            <Input
              value={typed}
              onChange={(event) => setTyped(event.target.value)}
              disabled={busy}
              inputMode="numeric"
              aria-label="Gõ số video để xác nhận"
              onPressEnter={() => typedRight && count > 0 && void remove()}
            />
          </>
        )}
      </div>
    </Modal>
  );
}

/** "Đã xóa 25 video", and what was left (skipped) with why. */
export function reportBulkDelete(
  message: ReturnType<typeof App.useApp>["message"],
  result: { deleted: number; skipped: Skipped[] },
) {
  if (result.deleted > 0) message.success(`Đã xóa ${result.deleted} video`);
  if (result.skipped.length > 0) {
    const by = new Map<string, number>();
    for (const item of result.skipped) by.set(item.reason, (by.get(item.reason) ?? 0) + 1);
    const parts = [...by].map(([reason, count]) => `${count} ${SKIPPED_WORDS[reason] ?? reason}`);
    message.warning(`Không xóa được ${result.skipped.length} video (${parts.join(", ")})`);
  }
}

export const deleteAction = (onClick: () => void) => ({
  key: "delete",
  label: "Xóa",
  icon: <DeleteOutlined />,
  danger: true,
  onClick,
});
