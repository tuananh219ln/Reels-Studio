"use client";

import { EditOutlined } from "@ant-design/icons";
import { Typography } from "antd";
import { useCallback, useEffect, useState } from "react";
import EditHistory, { type EditLogEntry } from "@/components/EditHistory";
import { api, formatDateTime } from "@/lib/api";

/** The history of a page of the team's shared settings (api edit_log.py): Mô hình AI, Nguồn tư liệu, Mẫu dựng and
 * Máy render. A card is a number within its page; a saved template is its id. */
export type SharedSettings = "settings_ai" | "settings_sources" | "render_settings" | "edit_template";

/** Names of the changed fields, by their last part ("openai.model" → "Model"); the first part is named by `owners`. */
const FIELD_NAMES: Record<string, string> = {
  active: "AI viết kịch bản đang dùng",
  base_url: "Base URL",
  model: "Model",
  // A stock source's switch ("pexels.enabled"); Máy render's own switch is "enabled" alone.
  "source:enabled": "Hiện trong hộp chọn",
  enabled: "Render trên máy render",
  ai_provider: "Nguồn ảnh AI mặc định",
  ai_style: "Phong cách ảnh AI",
  auto_photos: "Tự tìm ảnh sau khi viết kịch bản",
  machine: "Máy render",
  name: "Tên mẫu",
};
const VALUES: Record<string, string> = { gemini: "Gemini", cloudflare: "Cloudflare" };

function shown(value: unknown): string {
  if (value === null || value === undefined || value === "") return "(trống)";
  if (typeof value === "boolean") return value ? "Bật" : "Tắt";
  return VALUES[String(value)] ?? String(value);
}

/** One change as a line. A key is only ever its last characters ("…k3P1"), as the api logs it. */
export function describeChange(
  field: string,
  change: { old: unknown; new: unknown },
  owners: Record<string, string> = {},
): string {
  const [owner, part] = field.includes(".") ? field.split(".", 2) : ["", field];
  const who = owner ? `${owners[owner] ?? owner} · ` : "";
  if (part === "key") {
    const what = change.new === null ? "đã xoá khoá" : change.old === null ? "đã thêm khoá" : "đã đổi khoá";
    return `${who}Khoá: ${what}${change.new === null ? "" : ` ${String(change.new)}`}`;
  }
  const name = `${who}${FIELD_NAMES[owner && part === "enabled" ? "source:enabled" : part] ?? part}`;
  if (change.old === null && change.new !== null && (part === "machine" || part === "name")) {
    return `${name}: thêm “${shown(change.new)}”`;
  }
  if (change.new === null && change.old !== null && (part === "machine" || part === "name")) {
    return `${name}: xoá “${shown(change.old)}”`;
  }
  return `${name}: ${shown(change.old)} → ${shown(change.new)}`;
}

/** Each card's latest entry (GET /api/edit-logs/latest), read again whenever `version` changes (after a save). */
export function useLatestEdits(entityType: SharedSettings, version: unknown): Record<string, EditLogEntry> {
  const [latest, setLatest] = useState<Record<string, EditLogEntry>>({});
  const load = useCallback(() => {
    api<{ latest: Record<string, EditLogEntry> }>(`/edit-logs/latest?entity_type=${entityType}`)
      .then((answer) => setLatest(answer.latest))
      // Only a line under the cards: without it the page works as before.
      .catch(() => undefined);
  }, [entityType]);
  useEffect(() => {
    load();
  }, [load, version]);
  return latest;
}

type HistoryProps = { entityType: SharedSettings; title: string; owners?: Record<string, string> };

/** "Lịch sử" of the whole page, for the page's header. */
export function PageHistory({ entityType, title, owners }: HistoryProps) {
  return (
    <EditHistory
      entityType={entityType}
      title={title}
      kind="settings"
      describe={(field, change) => describeChange(field, change, owners)}
    />
  );
}

/** "Sửa lần cuối bởi <tên>, <giờ VN>" under a card; a click opens that card's history. Nothing before a first edit. */
export function LastEdit({
  entry,
  entityType,
  entityId,
  title,
  owners,
}: HistoryProps & { entry: EditLogEntry | undefined; entityId?: number }) {
  if (!entry) return null;
  return (
    <EditHistory
      entityType={entityType}
      entityId={entityId}
      title={title}
      kind="settings"
      describe={(field, change) => describeChange(field, change, owners)}
      trigger={(open) => (
        <Typography.Link
          type="secondary"
          data-testid="last-edit"
          onClick={open}
          style={{ display: "inline-block", marginTop: 8, fontSize: 12 }}
        >
          <EditOutlined /> Sửa lần cuối bởi {entry.user?.name ?? "Thành viên đã xoá"},{" "}
          {formatDateTime(entry.created_at)}
        </Typography.Link>
      )}
    />
  );
}
