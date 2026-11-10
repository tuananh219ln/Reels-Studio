"use client";

import { HistoryOutlined } from "@ant-design/icons";
import { App, Button, ConfigProvider, Drawer, Empty, Flex, Modal, Spin, Tag, theme, Typography } from "antd";
import { useState } from "react";
import { api, errorMessage, formatDateTime, type EditLogEntry } from "@/lib/api";
import { diffCounts, lineDiff } from "@/lib/lineDiff";

export type { EditLogEntry };

const ACTIONS: Record<EditLogEntry["action"], { label: string; color: string }> = {
  create: { label: "Tạo", color: "green" },
  update: { label: "Sửa", color: "blue" },
  delete: { label: "Xoá", color: "red" },
  restore: { label: "Khôi phục", color: "gold" },
};

const SOURCES: Record<string, string> = { mcp: "qua Claude", auto: "tự động" };

const VERBS: Record<EditLogEntry["action"], string> = {
  create: "tạo",
  update: "sửa",
  delete: "xoá",
  restore: "khôi phục",
};

/** "Khoaho sửa Từ cấm lúc 09/11/2026 14:32", the line under a thing's name; the time is Vietnam time. */
export function lastEditText(entry: EditLogEntry, fieldLabels: Record<string, string> = {}): string {
  const who = entry.user?.name ?? "Thành viên đã xoá";
  const parts = entry.action === "create" ? [] : Object.keys(entry.changes).map((name) => fieldLabels[name] ?? name);
  const what = parts.length ? ` ${parts.slice(0, 2).join(", ")}${parts.length > 2 ? "…" : ""}` : "";
  const source = SOURCES[entry.source] ? ` (${SOURCES[entry.source]})` : "";
  return `${who} ${VERBS[entry.action]}${what} lúc ${formatDateTime(entry.created_at)}${source}`;
}

type Kind =
  /** Long text (a prompt): "+12 −3 dòng", "Xem khác biệt". */
  | "text"
  /** A list of words: the words added and removed. */
  | "words"
  /** A short value: "old → new". */
  | "value"
  /** A whole thing's history: which parts each entry changed. */
  | "fields"
  /** Shared settings: each change on a line of its own, as `describe` words it (a key only by its last characters). */
  | "settings";

type Props = {
  entityType: string;
  entityId?: number;
  /** Only the entries that changed this field; none for a whole thing's history (`kind` "fields"). */
  field?: string;
  title: string;
  kind: Kind;
  /** The value as shown; "" may stand for the app's default ("Mặc định"). */
  show?: (value: unknown) => string;
  /** What is in use now, as shown: a version equal to it cannot be put back. */
  current?: string;
  /** "Bản mặc định của app" as a version of its own (a prompt), as shown. */
  defaultText?: string;
  /** Versions can be put back ("Khôi phục bản này"). */
  restorable?: boolean;
  onRestored?: () => void | Promise<void>;
  /** The names of the fields, for `kind` "fields" and "value" lists. */
  fieldLabels?: Record<string, string>;
  /** For `kind` "settings": one change as a line, e.g. "Khoá Pexels: đã đổi khoá …k3P1". */
  describe?: (field: string, change: { old: unknown; new: unknown }) => string;
  /** Replaces the "Lịch sử" button, e.g. the "Sửa lần cuối" line. */
  trigger?: (open: () => void) => React.ReactNode;
};

/** "Lịch sử": who changed this, when, and what it was before and after; any version can be put back when
 * `restorable`. The drawer reads the history each time it opens. */
export default function EditHistory(props: Props) {
  const { entityType, entityId, field, title, kind, trigger } = props;
  const { message } = App.useApp();
  const [open, setOpen] = useState(false);
  const [entries, setEntries] = useState<EditLogEntry[] | null>(null);

  async function load() {
    const params = new URLSearchParams({ entity_type: entityType });
    if (entityId !== undefined) params.set("entity_id", String(entityId));
    if (field) params.set("field", field);
    try {
      setEntries((await api<{ entries: EditLogEntry[] }>(`/edit-logs?${params}`)).entries);
    } catch (err) {
      message.error(errorMessage(err));
    }
  }

  function show() {
    setOpen(true);
    setEntries(null);
    void load();
  }

  return (
    <>
      {trigger ? (
        trigger(show)
      ) : (
        // Reading the history stays open where the cards around it are read-only; putting a version back does not.
        <ConfigProvider componentDisabled={false}>
          <Button size="small" icon={<HistoryOutlined />} onClick={show}>
            Lịch sử
          </Button>
        </ConfigProvider>
      )}
      <Drawer title={`Lịch sử: ${title}`} open={open} onClose={() => setOpen(false)} width={480} destroyOnHidden>
        {entries === null ? (
          <Flex justify="center" style={{ padding: 24 }}>
            <Spin />
          </Flex>
        ) : (
          <EntryList {...props} kind={kind} entries={entries} onChanged={load} />
        )}
      </Drawer>
    </>
  );
}

function EntryList({
  entries,
  onChanged,
  ...props
}: Props & { entries: EditLogEntry[]; onChanged: () => Promise<void> }) {
  const { field, kind, defaultText, restorable } = props;
  const oldest = entries.at(-1);
  // The version from before the history began, from its first entry (the text the first save replaced).
  const before = field && oldest && oldest.action !== "create" ? oldest.changes[field]?.old : undefined;
  if (entries.length === 0 && defaultText === undefined) {
    return <Empty description="Chưa có thay đổi nào được ghi lại" />;
  }
  return (
    <Flex vertical gap={0} data-testid="edit-history">
      {entries.map((entry, index) => (
        <EntryRow key={entry.id} {...props} entry={entry} later={index} onChanged={onChanged} />
      ))}
      {restorable && before !== undefined && before !== null && field && oldest && (
        <VersionRow
          {...props}
          heading="Bản trước khi có lịch sử"
          note={`Đang dùng tới ${formatDateTime(oldest.created_at)}`}
          value={before}
          later={entries.length}
          restore={{ log_id: oldest.id, side: "old" }}
          onChanged={onChanged}
        />
      )}
      {defaultText !== undefined && kind === "text" && (
        <VersionRow
          {...props}
          heading="Bản mặc định của app"
          note="Bản app có sẵn"
          value={defaultText}
          later={0}
          restore={{ log_id: null, side: "new" }}
          onChanged={onChanged}
        />
      )}
    </Flex>
  );
}

const rowStyle = (token: ReturnType<typeof theme.useToken>["token"]): React.CSSProperties => ({
  padding: "12px 0",
  borderTop: `1px solid ${token.colorBorderSecondary}`,
});

function EntryRow({
  entry,
  later,
  onChanged,
  ...props
}: Props & { entry: EditLogEntry; later: number; onChanged: () => Promise<void> }) {
  const { token } = theme.useToken();
  const { field, kind, fieldLabels } = props;
  const action = ACTIONS[entry.action];
  const change = field ? entry.changes[field] : undefined;
  return (
    <Flex vertical gap={6} style={rowStyle(token)} data-testid="edit-history-entry">
      <Flex gap={8} align="center" wrap>
        <Tag color={action.color} style={{ marginInlineEnd: 0 }}>
          {action.label}
        </Tag>
        <Typography.Text strong>{entry.user?.name ?? "Thành viên đã xoá"}</Typography.Text>
        <Typography.Text type="secondary">{formatDateTime(entry.created_at)}</Typography.Text>
        {SOURCES[entry.source] && <Tag color="purple">{SOURCES[entry.source]}</Tag>}
        {kind === "fields" || kind === "settings" || !field ? null : later === 0 ? <Tag>Đang dùng</Tag> : null}
      </Flex>
      {kind === "settings" ? (
        <Flex vertical gap={2}>
          {entry.label && <Typography.Text type="secondary">{entry.label}</Typography.Text>}
          {Object.entries(entry.changes).map(([name, value]) => (
            <Typography.Text key={name}>{props.describe?.(name, value) ?? name}</Typography.Text>
          ))}
        </Flex>
      ) : kind === "fields" ? (
        <Typography.Text type="secondary">
          {Object.keys(entry.changes)
            .map((name) => fieldLabels?.[name] ?? name)
            .join(", ")}
        </Typography.Text>
      ) : change ? (
        <ChangeSummary {...props} entry={entry} later={later} change={change} onChanged={onChanged} />
      ) : null}
    </Flex>
  );
}

function ChangeSummary({
  entry,
  change,
  later,
  onChanged,
  ...props
}: Props & {
  entry: EditLogEntry;
  change: { old: unknown; new: unknown };
  later: number;
  onChanged: () => Promise<void>;
}) {
  const { kind, show = String } = props;
  if (kind === "words") {
    const before = new Set((change.old as string[] | null) ?? []);
    const after = new Set((change.new as string[] | null) ?? []);
    const added = [...after].filter((word) => !before.has(word));
    const removed = [...before].filter((word) => !after.has(word));
    return (
      <Flex vertical gap={6}>
        <Flex gap={4} wrap>
          {added.map((word) => (
            <Tag key={`+${word}`} color="green">
              + {word}
            </Tag>
          ))}
          {removed.map((word) => (
            <Tag key={`-${word}`} color="red">
              − {word}
            </Tag>
          ))}
          {added.length + removed.length === 0 && <Typography.Text type="secondary">Đổi thứ tự</Typography.Text>}
        </Flex>
        {entry.action !== "delete" && (
          <VersionActions
            {...props}
            value={change.new}
            later={later}
            restore={{ log_id: entry.id, side: "new" }}
            onChanged={onChanged}
          />
        )}
      </Flex>
    );
  }
  if (kind === "value") {
    const name = (value: unknown) => (value === null || value === undefined ? "" : show(value) || "(trống)");
    const text =
      entry.action === "create"
        ? `“${name(change.new)}”`
        : entry.action === "delete"
          ? `“${name(change.old)}”`
          : `${name(change.old)} → ${name(change.new)}`;
    return (
      <Flex vertical gap={6}>
        <Typography.Text>{text}</Typography.Text>
        {entry.action !== "delete" && entry.action !== "create" && (
          <VersionActions
            {...props}
            value={change.new}
            later={later}
            restore={{ log_id: entry.id, side: "new" }}
            onChanged={onChanged}
          />
        )}
      </Flex>
    );
  }
  const counts = diffCounts(lineDiff(show(change.old ?? ""), show(change.new ?? "")));
  return (
    <Flex vertical gap={6}>
      <Typography.Text type="secondary">
        <Typography.Text type="success">+{counts.added}</Typography.Text>{" "}
        <Typography.Text type="danger">−{counts.removed}</Typography.Text> dòng
      </Typography.Text>
      <VersionActions
        {...props}
        value={change.new}
        compareTo={change.old}
        later={later}
        restore={{ log_id: entry.id, side: "new" }}
        onChanged={onChanged}
      />
    </Flex>
  );
}

type Restore = { log_id: number | null; side: "old" | "new" };

function VersionRow({
  heading,
  note,
  later,
  onChanged,
  ...props
}: Props & {
  heading: string;
  note: string;
  value: unknown;
  later: number;
  restore: Restore;
  onChanged: () => Promise<void>;
}) {
  const { token } = theme.useToken();
  return (
    <Flex vertical gap={6} style={rowStyle(token)} data-testid="edit-history-version">
      <Typography.Text strong>{heading}</Typography.Text>
      <Typography.Text type="secondary">{note}</Typography.Text>
      <VersionActions {...props} later={later} onChanged={onChanged} />
    </Flex>
  );
}

/** "Xem khác biệt" (a text, against what is in use or against the version before) and "Khôi phục bản này". */
function VersionActions({
  entityType,
  entityId,
  field,
  title,
  kind,
  show = String,
  current,
  restorable,
  onRestored,
  value,
  compareTo,
  later,
  restore,
  onChanged,
}: Props & {
  value: unknown;
  compareTo?: unknown;
  later: number;
  restore: Restore;
  onChanged?: () => Promise<void>;
}) {
  const { message, modal } = App.useApp();
  const [diff, setDiff] = useState<{ before: string; after: string; heading: string } | null>(null);
  const shown = value === null || value === undefined ? "" : show(value);
  const inUse = current !== undefined && shown === current;

  function confirmRestore() {
    modal.confirm({
      title: "Khôi phục bản này?",
      content:
        later > 0
          ? `Có ${later} lần sửa sau bản này. Nội dung đang dùng sẽ được thay; bản hiện tại vẫn còn trong lịch sử.`
          : "Nội dung đang dùng sẽ được thay; bản hiện tại vẫn còn trong lịch sử.",
      okText: "Khôi phục",
      cancelText: "Huỷ",
      onOk: async () => {
        try {
          await api("/edit-logs/restore", "POST", { entity_type: entityType, entity_id: entityId, field, ...restore });
          message.success(`Đã khôi phục ${title.toLowerCase()}`);
          await onRestored?.();
          await onChanged?.();
        } catch (err) {
          message.error(errorMessage(err));
        }
      },
    });
  }

  return (
    <Flex gap={4} wrap>
      {kind === "text" && (
        <Button
          size="small"
          type="link"
          style={{ paddingInline: 0, marginInlineEnd: 12 }}
          onClick={() =>
            compareTo === undefined
              ? setDiff({ before: current ?? "", after: shown, heading: "Đang dùng → bản này" })
              : setDiff({ before: show(compareTo ?? ""), after: shown, heading: "Bản trước → bản này" })
          }
        >
          Xem khác biệt
        </Button>
      )}
      {restorable && !inUse && (
        <Button size="small" type="link" style={{ paddingInline: 0 }} onClick={confirmRestore}>
          Khôi phục bản này
        </Button>
      )}
      {diff && <DiffModal {...diff} title={title} onClose={() => setDiff(null)} />}
    </Flex>
  );
}

function DiffModal({
  before,
  after,
  heading,
  title,
  onClose,
}: {
  before: string;
  after: string;
  heading: string;
  title: string;
  onClose: () => void;
}) {
  const { token } = theme.useToken();
  const lines = lineDiff(before, after);
  const colors = {
    same: { background: "transparent", color: token.colorText },
    removed: { background: token.colorErrorBg, color: token.colorErrorText },
    added: { background: token.colorSuccessBg, color: token.colorSuccessText },
  };
  return (
    <Modal open title={`${title}: ${heading}`} onCancel={onClose} footer={null} width={880}>
      <div
        data-testid="edit-history-diff"
        style={{
          fontFamily: token.fontFamilyCode,
          fontSize: 12,
          maxHeight: "65vh",
          overflow: "auto",
          border: `1px solid ${token.colorBorderSecondary}`,
          borderRadius: token.borderRadius,
        }}
      >
        {lines.map((line, index) => (
          <div
            key={index}
            style={{ ...colors[line.kind], padding: "1px 8px", whiteSpace: "pre-wrap", wordBreak: "break-word" }}
          >
            {line.kind === "added" ? "+ " : line.kind === "removed" ? "− " : "  "}
            {line.text || " "}
          </div>
        ))}
      </div>
    </Modal>
  );
}
