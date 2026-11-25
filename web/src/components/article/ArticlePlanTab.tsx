"use client";

import Hint from "@/components/Hint";
import StatusText, { toneOf } from "@/components/StatusText";
import FormDrawer from "@/components/FormDrawer";
import {
  api,
  errorMessage,
  formatDateTime,
  upload,
  type Article,
  type ArticleKind,
  type ArticlePlanView,
  type Knowledge,
  type PlanImportPreview,
  type PlanImportRow,
  type PlanSlot,
} from "@/lib/api";
import { useUrlId } from "@/lib/urlState";
import { DeleteOutlined, MessageOutlined, PlusOutlined, SettingOutlined, UploadOutlined } from "@ant-design/icons";
import {
  Alert,
  App,
  Button,
  Card,
  Checkbox,
  Empty,
  Flex,
  Input,
  InputNumber,
  Modal,
  Progress,
  Segmented,
  Select,
  Spin,
  Table,
  Tag,
  Typography,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

const STATUS_COLORS: Record<PlanSlot["status"], string> = {
  unused: "default",
  used: "blue",
  scheduled: "orange",
  posted: "green",
  skipped: "default",
};
const CHECK_TAGS: Record<PlanImportRow["check"], { color: string; label: string }> = {
  ok: { color: "green", label: "Hợp lệ" },
  warning: { color: "orange", label: "Cảnh báo" },
  error: { color: "red", label: "Lỗi" },
};
const ACTION_LABELS: Record<PlanImportRow["action"], string> = {
  add: "Thêm mới",
  skip_posted: "Bỏ qua (đã đăng)",
  skip_used: "Bỏ qua (đã tạo bài)",
  skip: "Bỏ qua",
};
const WEEKDAYS = ["CN", "T2", "T3", "T4", "T5", "T6", "T7"];

type PlanPage = { id: number; name: string; mine: boolean; has_plan: boolean };

/** "dd/mm" and the weekday of a plan's day, from its start date (a plain date, no time zone). */
function dayDate(start: string | null, day: number): string | null {
  if (!start) return null;
  const [year, month, date] = start.split("-").map(Number);
  const on = new Date(Date.UTC(year, month - 1, date + day - 1));
  return `${WEEKDAYS[on.getUTCDay()]} ${String(on.getUTCDate()).padStart(2, "0")}/${String(on.getUTCMonth() + 1).padStart(2, "0")}`;
}

function showDate(iso: string | null): string {
  if (!iso) return "—";
  const [year, month, date] = iso.split("-");
  return `${date}/${month}/${year}`;
}

/** The rows that cannot be saved, as a CSV to fix and import again ("Tải N dòng lỗi"). */
function errorsCsv(rows: PlanImportRow[]): string {
  const quote = (value: unknown) => `"${String(value ?? "").replaceAll('"', '""')}"`;
  const lines = [["row", "day", "slot", "hook", "body", "cta", "hashtags", "image_brief", "errors"].join(",")];
  for (const row of rows.filter((item) => item.check === "error")) {
    lines.push(
      [
        row.row,
        row.day ?? "",
        row.slot ?? "",
        row.hook,
        row.body,
        row.cta,
        row.hashtags.join(" "),
        row.image_brief,
        row.errors.join("; "),
      ]
        .map(quote)
        .join(","),
    );
  }
  return "﻿" + lines.join("\n");
}

function download(name: string, text: string, type: string) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  URL.revokeObjectURL(url);
}

/**
 * "Kế hoạch 30 ngày" of Bài viết: a Page's 30 days × its posting slots of article scripts, with the Backlog under it
 * (decisions 2026-11-15, "article plan"). Everyone reads it; the Page's owner sets it up, imports a file (previewed
 * before it is saved), edits, drags between slots and the Backlog, deletes, and makes an article from a script.
 */
export default function ArticlePlanTab() {
  const { message, modal } = App.useApp();
  const router = useRouter();
  const [pages, setPages] = useState<PlanPage[] | null>(null);
  const [chosen, setChosen] = useUrlId("fanpage");
  const fanpageId = chosen ?? pages?.find((page) => page.mine)?.id ?? pages?.[0]?.id ?? null;
  const [view, setView] = useState<ArticlePlanView | null>(null);
  const [groups, setGroups] = useState<Knowledge["topics"]>([]);
  const [settingUp, setSettingUp] = useState(false);
  const [importing, setImporting] = useState(false);
  const [commenting, setCommenting] = useState(false);
  const [queuedTotal, setQueuedTotal] = useState(0);
  const [editing, setEditing] = useState<{ slot: PlanSlot | null; day: number | null; number: number | null } | null>(
    null,
  );
  const [selecting, setSelecting] = useState(false);
  const [selected, setSelected] = useState<number[]>([]);
  const [busy, setBusy] = useState(false);
  const dragged = useRef<number | null>(null);

  useEffect(() => {
    api<PlanPage[]>("/article-plans/pages")
      .then(setPages)
      .catch((err) => message.error(errorMessage(err)));
    api<Knowledge>("/knowledge")
      .then((data) => setGroups(data.topics))
      .catch(() => undefined);
  }, [message]);

  const load = useCallback(async () => {
    if (fanpageId === null) return;
    try {
      const loaded = await api<ArticlePlanView>(`/article-plans/${fanpageId}`);
      setView(loaded);
      if (!loaded.plan && loaded.can_edit) setSettingUp(true);
    } catch (err) {
      message.error(errorMessage(err));
    }
  }, [fanpageId, message]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- loads the chosen Page's plan; state is set only after the request answers
    void load();
  }, [load]);

  const pending = view?.plan?.comments_pending ?? 0;
  useEffect(() => {
    // The "Tạo bình luận ghim" jobs run in the worker: read the plan again until none is left.
    if (pending === 0) return;
    const timer = setInterval(() => void load(), 4000);
    return () => clearInterval(timer);
  }, [pending, load]);

  async function change(call: () => Promise<ArticlePlanView>, done?: string) {
    setBusy(true);
    try {
      const saved = await call();
      setView(saved);
      if (done) message.success(done);
      return saved;
    } catch (err) {
      message.error(errorMessage(err));
      return null;
    } finally {
      setBusy(false);
    }
  }

  function moveTo(slotId: number, day: number | null, number: number | null) {
    void change(() => api<ArticlePlanView>(`/article-plans/slots/${slotId}`, "PATCH", { day, slot: number }));
  }

  /** "Tạo bài từ ô này": the article filled from the script, its photo links added, then its page. */
  async function makeArticle(slot: PlanSlot) {
    setBusy(true);
    try {
      const article = await api<Article>("/articles", "POST", { plan_slot_id: slot.id });
      let failed = 0;
      for (const url of slot.image_urls) {
        await api(`/articles/${article.id}/images/from-url`, "POST", { url }).catch(() => (failed += 1));
      }
      if (failed) message.warning(`${failed} link ảnh không lấy được, hãy chọn ảnh khác`);
      router.push(`/articles/${article.id}`);
    } catch (err) {
      message.error(errorMessage(err));
      setBusy(false);
    }
  }

  const plan = view?.plan ?? null;
  const editable = view?.can_edit ?? false;
  const byCell = useMemo(() => {
    const cells = new Map<string, PlanSlot>();
    for (const slot of view?.slots ?? []) cells.set(`${slot.day}:${slot.slot}`, slot);
    return cells;
  }, [view]);

  /** "BL 5/5": grey with none, orange short of five, green when full. */
  function commentsTag(slot: PlanSlot) {
    const color = slot.comments_count === 0 ? "default" : slot.comments_count < 5 ? "orange" : "green";
    return (
      <Tag color={color} data-testid="comments-tag" style={{ marginInlineEnd: 0, fontSize: 11 }}>
        BL {slot.comments_count > 0 ? `${slot.comments_count}/5` : "—"}
      </Tag>
    );
  }

  function cell(slot: PlanSlot | undefined, day: number, number: number) {
    const today = plan?.today_day === day;
    const drop = {
      onDragOver: (event: React.DragEvent) => editable && event.preventDefault(),
      onDrop: () => {
        if (dragged.current !== null) moveTo(dragged.current, day, number);
        dragged.current = null;
      },
    };
    if (!slot) {
      return (
        <div
          {...drop}
          role={editable ? "button" : undefined}
          tabIndex={editable ? 0 : undefined}
          aria-label={`Thêm kịch bản ngày ${day} khung ${number}`}
          onClick={() => editable && setEditing({ slot: null, day, number })}
          style={{
            minHeight: 54,
            borderRadius: 6,
            border: "1px dashed var(--ant-color-border)",
            background: today ? "var(--ant-color-primary-bg)" : undefined,
            cursor: editable ? "pointer" : "default",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          {editable && <Typography.Text type="secondary">+ Thêm</Typography.Text>}
        </div>
      );
    }
    return (
      <div
        {...drop}
        draggable={editable && !selecting}
        onDragStart={() => (dragged.current = slot.id)}
        role="button"
        tabIndex={0}
        aria-label={`Ngày ${day} khung ${number}: ${slot.hook}`}
        data-testid="plan-cell"
        onClick={() =>
          selecting
            ? setSelected((ids) => (ids.includes(slot.id) ? ids.filter((id) => id !== slot.id) : [...ids, slot.id]))
            : setEditing({ slot, day, number })
        }
        style={{
          minHeight: 54,
          padding: "4px 6px",
          borderRadius: 6,
          border: "1px solid var(--ant-color-border-secondary)",
          background: today ? "var(--ant-color-primary-bg)" : "var(--ant-color-bg-container)",
          opacity: slot.status === "skipped" ? 0.55 : 1,
          cursor: "pointer",
        }}
      >
        <Flex justify="space-between" align="center" gap={4}>
          {selecting ? (
            <Checkbox checked={selected.includes(slot.id)} disabled={slot.article_id !== null} />
          ) : (
            <Tag color={STATUS_COLORS[slot.status]} style={{ marginInlineEnd: 0, fontSize: 11 }}>
              {slot.status_label}
            </Tag>
          )}
          <Typography.Text type="secondary" style={{ fontSize: 11 }} ellipsis>
            {slot.kind_label ?? ""}
          </Typography.Text>
        </Flex>
        <Typography.Paragraph ellipsis={{ rows: 2 }} style={{ margin: "2px 0 0", fontSize: 13 }}>
          {slot.hook}
        </Typography.Paragraph>
        {commentsTag(slot)}
      </div>
    );
  }

  const columns: ColumnsType<{ day: number }> = plan
    ? [
        {
          title: "Ngày",
          key: "day",
          width: 90,
          fixed: "left",
          render: (_, row) => (
            <Flex vertical>
              <Typography.Text strong>Ngày {row.day}</Typography.Text>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                {dayDate(plan.start_date, row.day)}
              </Typography.Text>
            </Flex>
          ),
        },
        ...plan.post_times.map((time, index) => ({
          title: `Khung ${index + 1} · ${time}`,
          key: `slot-${index + 1}`,
          width: 220,
          render: (_: unknown, row: { day: number }) => cell(byCell.get(`${row.day}:${index + 1}`), row.day, index + 1),
        })),
      ]
    : [];

  if (pages === null) return <Spin />;
  if (pages.length === 0) return <Empty description="Chưa có Page nào đang dùng: kết nối Page ở Quản lý kênh trước" />;

  return (
    <Flex vertical gap={12} data-testid="article-plan">
      <Flex gap={12} align="center" wrap>
        <Select
          aria-label="Page của kế hoạch"
          style={{ minWidth: 240 }}
          value={fanpageId ?? undefined}
          options={pages.map((page) => ({
            value: page.id,
            label: `${page.name}${page.mine ? "" : " (của đồng đội)"}${page.has_plan ? "" : " · chưa có kế hoạch"}`,
          }))}
          onChange={(value: number) => {
            setView(null);
            setSettingUp(false);
            setSelecting(false);
            setSelected([]);
            setChosen(value);
          }}
        />
        {plan?.start_date && (
          <Typography.Text type="secondary">
            {showDate(plan.start_date)} – {showDate(plan.end_date)}
          </Typography.Text>
        )}
      </Flex>

      {view === null ? (
        <Spin />
      ) : (
        <>
          <Card size="small">
            <Flex vertical gap={8}>
              {plan ? (
                <>
                  <Typography.Text type="secondary">
                    Bắt đầu {showDate(plan.start_date)} ·{" "}
                    {plan.today_day ? `hôm nay là Ngày ${plan.today_day}` : "hôm nay ngoài 30 ngày"} · {plan.per_day}{" "}
                    bài/ngày: {plan.post_times.join(" · ")}
                  </Typography.Text>
                  <Typography.Text strong data-testid="plan-summary">
                    Đã làm {plan.used}/{plan.total}, đã lên lịch {plan.scheduled}, ngày còn trống {plan.empty_days} ·
                    Backlog {plan.backlog}
                  </Typography.Text>
                  <Typography.Text data-testid="comments-summary">
                    Bình luận: {plan.comments.full}/{plan.comments.total} kịch bản đủ 5/5
                    {plan.comments_pending > 0 ? ` · đang tạo ${plan.comments_pending} kịch bản…` : ""}
                  </Typography.Text>
                  {plan.comments_pending > 0 && (
                    <Progress
                      size="small"
                      style={{ maxWidth: 480 }}
                      percent={Math.round(
                        ((Math.max(queuedTotal, plan.comments_pending) - plan.comments_pending) /
                          Math.max(queuedTotal, plan.comments_pending)) *
                          100,
                      )}
                      format={() => `Tạo bình luận: còn ${plan.comments_pending}`}
                      data-testid="comments-progress"
                    />
                  )}
                  <Progress
                    percent={Math.round((plan.used / Math.max(plan.total, 1)) * 100)}
                    format={() => `Đã dùng ${plan.used}/${plan.total} kịch bản`}
                    size="small"
                    style={{ maxWidth: 480 }}
                  />
                </>
              ) : (
                <Typography.Text type="secondary">
                  {editable
                    ? "Chọn ngày bắt đầu để app biết hôm nay là ngày mấy của kế hoạch."
                    : "Page này chưa có kế hoạch; chủ Page thiết lập."}
                </Typography.Text>
              )}
              {editable && (
                <Flex gap={8} wrap>
                  <Button icon={<SettingOutlined />} onClick={() => setSettingUp(!settingUp)}>
                    Thiết lập
                  </Button>
                  <Button icon={<UploadOutlined />} disabled={!plan} onClick={() => setImporting(true)}>
                    Nhập file JSON/CSV
                  </Button>
                  <Button
                    icon={<PlusOutlined />}
                    disabled={!plan}
                    onClick={() => setEditing({ slot: null, day: null, number: null })}
                  >
                    Thêm vào Backlog
                  </Button>
                  <Button icon={<MessageOutlined />} disabled={!plan} onClick={() => setCommenting(true)}>
                    Tạo bình luận ghim
                  </Button>
                  {selecting ? (
                    <>
                      <Button
                        danger
                        icon={<DeleteOutlined />}
                        disabled={selected.length === 0}
                        loading={busy}
                        onClick={() =>
                          modal.confirm({
                            title: `Xoá ${selected.length} kịch bản?`,
                            content: "Kịch bản đã có bài viết sẽ được giữ lại.",
                            okText: "Xoá",
                            okButtonProps: { danger: true },
                            cancelText: "Huỷ",
                            onOk: async () => {
                              const saved = await change(() =>
                                api<ArticlePlanView & { deleted: number; kept: number }>(
                                  `/article-plans/${fanpageId}/slots/delete`,
                                  "POST",
                                  { ids: selected },
                                ),
                              );
                              if (saved) {
                                const result = saved as ArticlePlanView & { deleted: number; kept: number };
                                message.success(
                                  `Đã xoá ${result.deleted} kịch bản${result.kept ? `, giữ ${result.kept} đã có bài` : ""}`,
                                );
                                setSelected([]);
                                setSelecting(false);
                              }
                            },
                          })
                        }
                      >
                        Xoá {selected.length} kịch bản
                      </Button>
                      <Button
                        onClick={() => {
                          setSelecting(false);
                          setSelected([]);
                        }}
                      >
                        Huỷ chọn
                      </Button>
                    </>
                  ) : (
                    <Button icon={<DeleteOutlined />} disabled={!plan} onClick={() => setSelecting(true)}>
                      Xóa nhiều kịch bản
                    </Button>
                  )}
                </Flex>
              )}
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                File nhập hiện bảng xem trước; kế hoạch chỉ đổi khi bấm “Lưu kế hoạch”, Backlog vẫn giữ. Kéo một kịch
                bản sang ô khác để đổi chỗ, hoặc thả xuống Backlog.
              </Typography.Text>
              {settingUp && fanpageId !== null && (
                <PlanSettings
                  view={view}
                  groups={groups}
                  onCancel={() => setSettingUp(false)}
                  onSave={async (body) => {
                    const saved = await change(
                      () => api<ArticlePlanView>(`/article-plans/${fanpageId}/settings`, "PUT", body),
                      "Đã lưu thiết lập",
                    );
                    if (saved) {
                      const moved = (saved as ArticlePlanView & { moved_to_backlog?: number }).moved_to_backlog;
                      if (moved) message.info(`${moved} kịch bản ở khung bị bỏ đã chuyển vào Backlog`);
                      setSettingUp(false);
                      setPages((list) =>
                        (list ?? []).map((page) => (page.id === fanpageId ? { ...page, has_plan: true } : page)),
                      );
                    }
                  }}
                />
              )}
            </Flex>
          </Card>

          {plan && (
            <Card size="small" styles={{ body: { padding: 0 } }}>
              <Table<{ day: number }>
                rowKey="day"
                size="small"
                columns={columns}
                dataSource={Array.from({ length: 30 }, (_, index) => ({ day: index + 1 }))}
                pagination={false}
                scroll={{ x: 90 + 220 * plan.per_day, y: 640 }}
                data-testid="plan-grid"
              />
            </Card>
          )}

          {plan && (
            <Card
              size="small"
              title={`Backlog (${view.backlog.length})`}
              onDragOver={(event) => editable && event.preventDefault()}
              onDrop={() => {
                if (dragged.current !== null) moveTo(dragged.current, null, null);
                dragged.current = null;
              }}
              data-testid="plan-backlog"
            >
              {view.backlog.length === 0 ? (
                <Typography.Text type="secondary">
                  Kịch bản chưa xếp ngày nằm ở đây; kéo vào ô trống để xếp lịch.
                </Typography.Text>
              ) : (
                <Flex gap={8} wrap>
                  {view.backlog.map((slot) => (
                    <div
                      key={slot.id}
                      draggable={editable && !selecting}
                      onDragStart={() => (dragged.current = slot.id)}
                      role="button"
                      tabIndex={0}
                      onClick={() =>
                        selecting
                          ? setSelected((ids) =>
                              ids.includes(slot.id) ? ids.filter((id) => id !== slot.id) : [...ids, slot.id],
                            )
                          : setEditing({ slot, day: null, number: null })
                      }
                      style={{
                        width: 220,
                        padding: "6px 8px",
                        borderRadius: 6,
                        border: "1px solid var(--ant-color-border-secondary)",
                        cursor: "pointer",
                      }}
                    >
                      <Flex justify="space-between" gap={4}>
                        {selecting ? (
                          <Checkbox checked={selected.includes(slot.id)} disabled={slot.article_id !== null} />
                        ) : (
                          <Tag color={STATUS_COLORS[slot.status]} style={{ fontSize: 11 }}>
                            {slot.status_label}
                          </Tag>
                        )}
                        <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                          {slot.kind_label ?? ""}
                        </Typography.Text>
                      </Flex>
                      <Typography.Paragraph ellipsis={{ rows: 2 }} style={{ margin: 0, fontSize: 13 }}>
                        {slot.hook}
                      </Typography.Paragraph>
                      {commentsTag(slot)}
                    </div>
                  ))}
                </Flex>
              )}
            </Card>
          )}
        </>
      )}

      {editing && view && fanpageId !== null && (
        <SlotDrawer
          key={editing.slot?.id ?? `new-${editing.day}-${editing.number}`}
          editing={editing}
          view={view}
          groups={groups}
          busy={busy}
          onClose={() => setEditing(null)}
          onSave={async (body) => {
            const saved = await change(() =>
              editing.slot
                ? api<ArticlePlanView>(`/article-plans/slots/${editing.slot.id}`, "PATCH", body)
                : api<ArticlePlanView>(`/article-plans/${fanpageId}/slots`, "POST", {
                    ...body,
                    day: editing.day,
                    slot: editing.number,
                  }),
            );
            if (saved) setEditing(null);
          }}
          onMake={(slot) => void makeArticle(slot)}
          onOpen={(articleId) => router.push(`/articles/${articleId}`)}
        />
      )}
      {commenting && view && fanpageId !== null && (
        <CommentsModal
          fanpageId={fanpageId}
          view={view}
          selected={selected}
          onClose={() => setCommenting(false)}
          onQueued={(saved, queued) => {
            setView(saved);
            setQueuedTotal(queued);
            setCommenting(false);
            message.success(queued ? `Đã đưa ${queued} kịch bản vào hàng đợi` : "Không có kịch bản nào cần tạo");
          }}
        />
      )}
      {importing && view && fanpageId !== null && (
        <ImportModal
          fanpageId={fanpageId}
          onClose={() => setImporting(false)}
          onSaved={(saved, report) => {
            setView(saved);
            setImporting(false);
            message.success(
              `Đã lưu: ${report.placed} vào lịch, ${report.backlog} vào Backlog` +
                (report.moved_to_backlog ? `, ${report.moved_to_backlog} kịch bản cũ chuyển vào Backlog` : ""),
            );
          }}
        />
      )}
    </Flex>
  );
}

type SettingsBody = {
  start_date: string | null;
  per_day: number;
  post_times: string[];
  topic_group_ids: number[];
  kind_mix: Partial<Record<ArticleKind, number>>;
  tone: string;
  audience: string;
};

/** "Thiết lập": day 1, posts a day and their times (one chip each), and what "Tạo bằng AI" will write from. */
function PlanSettings({
  view,
  groups,
  onCancel,
  onSave,
}: {
  view: ArticlePlanView;
  groups: Knowledge["topics"];
  onCancel: () => void;
  onSave: (body: SettingsBody) => Promise<void>;
}) {
  const plan = view.plan;
  const [start, setStart] = useState(plan?.start_date ?? "");
  const [perDay, setPerDay] = useState(plan?.per_day ?? view.defaults.per_day);
  const [times, setTimes] = useState<string[]>(plan?.post_times ?? view.defaults.post_times);
  const [groupIds, setGroupIds] = useState<number[]>(plan?.topic_group_ids ?? []);
  const [mix, setMix] = useState<Partial<Record<ArticleKind, number>>>(plan?.kind_mix ?? {});
  const [tone, setTone] = useState(plan?.tone ?? "");
  const [audience, setAudience] = useState(plan?.audience ?? "");
  const [saving, setSaving] = useState(false);
  const mixTotal = Object.values(mix).reduce((sum, value) => sum + (value ?? 0), 0);
  const timesOk = times.length === perDay && times.every((time) => /^\d{2}:\d{2}$/.test(time));

  return (
    <Card size="small" data-testid="plan-settings">
      <Flex vertical gap={12}>
        <Flex gap={16} wrap align="end">
          <label>
            <Typography.Text type="secondary">Ngày bắt đầu</Typography.Text>
            <Input
              type="date"
              aria-label="Ngày bắt đầu"
              value={start}
              onChange={(event) => setStart(event.target.value)}
              style={{ display: "block" }}
            />
          </label>
          <label>
            <Typography.Text type="secondary">Số bài mỗi ngày</Typography.Text>
            <InputNumber
              aria-label="Số bài mỗi ngày"
              min={1}
              max={10}
              value={perDay}
              onChange={(value) => setPerDay(value ?? 1)}
              style={{ display: "block" }}
            />
          </label>
          <label style={{ flex: "1 1 260px" }}>
            <Typography.Text type="secondary">Giờ đăng</Typography.Text>
            <Select
              aria-label="Giờ đăng"
              mode="tags"
              style={{ width: "100%" }}
              value={times}
              open={false}
              tokenSeparators={[",", " "]}
              onChange={(value: string[]) => setTimes([...new Set(value)].sort())}
              status={timesOk ? undefined : "error"}
            />
          </label>
        </Flex>
        <Flex gap={16} wrap>
          <label style={{ flex: "1 1 240px" }}>
            <Typography.Text type="secondary">Nhóm chủ đề (cho Tạo bằng AI)</Typography.Text>
            <Select
              aria-label="Nhóm chủ đề"
              mode="multiple"
              style={{ width: "100%" }}
              value={groupIds}
              options={groups.map((group) => ({ value: group.id, label: group.name }))}
              onChange={setGroupIds}
            />
          </label>
          <div style={{ flex: "1 1 320px" }}>
            <Typography.Text type="secondary">
              Tỉ lệ dạng bài {mixTotal ? `(${mixTotal}%)` : "(để trống: AI tự chia)"}
            </Typography.Text>
            <Flex gap={6} wrap>
              {view.kinds.map((kind) => (
                <InputNumber
                  key={kind.value}
                  aria-label={`Tỉ lệ ${kind.label}`}
                  size="small"
                  min={0}
                  max={100}
                  addonBefore={kind.label}
                  addonAfter="%"
                  value={mix[kind.value] ?? null}
                  onChange={(value) => setMix({ ...mix, [kind.value]: value ?? 0 })}
                  style={{ width: 230 }}
                />
              ))}
            </Flex>
          </div>
        </Flex>
        <label>
          <Typography.Text type="secondary">Giọng văn</Typography.Text>
          <Input.TextArea
            aria-label="Giọng văn"
            value={tone}
            maxLength={500}
            autoSize={{ minRows: 1, maxRows: 3 }}
            placeholder="VD: Gần gũi, ngắn gọn, xưng “mình”, không dùng thuật ngữ y khoa khó"
            onChange={(event) => setTone(event.target.value)}
          />
        </label>
        <label>
          <Typography.Text type="secondary">Nhóm đối tượng (cho bình luận ghim)</Typography.Text>
          <Input
            aria-label="Nhóm đối tượng"
            value={audience}
            maxLength={200}
            placeholder="VD: 35–55 tuổi, quan tâm sức khỏe"
            onChange={(event) => setAudience(event.target.value)}
          />
        </label>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          Số giờ đăng phải bằng số bài mỗi ngày (gõ giờ dạng 07:00 rồi Enter). Giảm số bài: kịch bản ở khung bị bỏ
          chuyển vào Backlog. Nhóm chủ đề, tỉ lệ dạng bài và giọng văn chỉ dùng khi Tạo bằng AI.
        </Typography.Text>
        {mixTotal !== 0 && mixTotal !== 100 && (
          <Alert type="warning" showIcon title="Tỉ lệ các dạng bài phải cộng lại đúng 100%" />
        )}
        <Flex gap={8}>
          <Button
            type="primary"
            loading={saving}
            disabled={!start || !timesOk || (mixTotal !== 0 && mixTotal !== 100)}
            onClick={async () => {
              setSaving(true);
              await onSave({
                start_date: start || null,
                per_day: perDay,
                post_times: times,
                topic_group_ids: groupIds,
                kind_mix: mix,
                tone,
                audience,
              });
              setSaving(false);
            }}
          >
            Lưu
          </Button>
          {view.plan && <Button onClick={onCancel}>Huỷ</Button>}
        </Flex>
      </Flex>
    </Card>
  );
}

type SlotFields = {
  hook: string;
  body: string;
  cta: string;
  hashtags: string[];
  image_brief: string;
  image_urls: string[];
  kind: ArticleKind | null;
  knowledge_topic_id: number | null;
  skipped?: boolean;
  day?: number | null;
  slot?: number | null;
};

/** A script: read, edited by the Page's owner, skipped, sent to the Backlog, or made into an article. */
function SlotDrawer({
  editing,
  view,
  groups,
  busy,
  onClose,
  onSave,
  onMake,
  onOpen,
}: {
  editing: { slot: PlanSlot | null; day: number | null; number: number | null };
  view: ArticlePlanView;
  groups: Knowledge["topics"];
  busy: boolean;
  onClose: () => void;
  onSave: (body: Partial<SlotFields>) => Promise<void>;
  onMake: (slot: PlanSlot) => void;
  onOpen: (articleId: number) => void;
}) {
  const slot = editing.slot;
  const editable = view.can_edit;
  const [fields, setFields] = useState<SlotFields>({
    hook: slot?.hook ?? "",
    body: slot?.body ?? "",
    cta: slot?.cta ?? "",
    hashtags: slot?.hashtags ?? [],
    image_brief: slot?.image_brief ?? "",
    image_urls: slot?.image_urls ?? [],
    kind: slot?.kind ?? null,
    knowledge_topic_id: slot?.knowledge_topic_id ?? null,
  });
  const where =
    editing.day !== null
      ? `Ngày ${editing.day} · Khung ${editing.number} · ${view.plan?.post_times[(editing.number ?? 1) - 1] ?? ""}`
      : "Backlog";
  const set = (patch: Partial<SlotFields>) => setFields({ ...fields, ...patch });

  return (
    <FormDrawer
      title={slot ? where : `Thêm kịch bản · ${where}`}
      open
      width={560}
      onClose={onClose}
      footer={
        <Flex gap={8} wrap justify="end">
          {slot && editable && slot.article_id === null && (
            <Button loading={busy} onClick={() => onSave({ skipped: !slot.skipped })}>
              {slot.skipped ? "Dùng lại ô này" : "Bỏ qua ô này"}
            </Button>
          )}
          {slot && editable && slot.day !== null && (
            <Button loading={busy} onClick={() => onSave({ day: null, slot: null })}>
              Đưa vào Backlog
            </Button>
          )}
          {slot?.article_id ? (
            <Button onClick={() => onOpen(slot.article_id!)}>Mở bài viết</Button>
          ) : (
            slot &&
            editable &&
            !slot.skipped && (
              <Button type="primary" loading={busy} onClick={() => onMake(slot)}>
                Tạo bài từ ô này
              </Button>
            )
          )}
          {editable && (
            <Button
              type={slot ? "default" : "primary"}
              loading={busy}
              disabled={!fields.hook.trim()}
              onClick={() => onSave(fields)}
            >
              {slot ? "Lưu sửa" : "Thêm"}
            </Button>
          )}
        </Flex>
      }
    >
      <Flex vertical gap={12}>
        {slot && (
          <Flex gap={8} align="center" wrap>
            <Tag color={STATUS_COLORS[slot.status]}>{slot.status_label}</Tag>
            {slot.post_at && (
              <Typography.Text type="secondary">Đăng lúc {formatDateTime(slot.post_at)}</Typography.Text>
            )}
          </Flex>
        )}
        <label>
          <Typography.Text type="secondary">Câu mở (hook)</Typography.Text>
          <Input
            aria-label="Câu mở"
            value={fields.hook}
            maxLength={150}
            disabled={!editable}
            onChange={(e) => set({ hook: e.target.value })}
          />
        </label>
        <label>
          <Typography.Text type="secondary">Nội dung</Typography.Text>
          <Input.TextArea
            aria-label="Nội dung"
            value={fields.body}
            maxLength={2000}
            autoSize={{ minRows: 4, maxRows: 14 }}
            disabled={!editable}
            onChange={(e) => set({ body: e.target.value })}
          />
        </label>
        <label>
          <Typography.Text type="secondary">Câu kêu gọi bình luận</Typography.Text>
          <Input
            aria-label="Câu kêu gọi bình luận"
            value={fields.cta}
            maxLength={300}
            disabled={!editable}
            onChange={(e) => set({ cta: e.target.value })}
          />
        </label>
        <label>
          <Typography.Text type="secondary">Hashtag</Typography.Text>
          <Select
            aria-label="Hashtag"
            mode="tags"
            open={false}
            style={{ width: "100%" }}
            value={fields.hashtags}
            disabled={!editable}
            tokenSeparators={[" ", ","]}
            onChange={(value: string[]) => set({ hashtags: value })}
          />
        </label>
        <Flex gap={12} wrap>
          <label style={{ flex: "1 1 200px" }}>
            <Typography.Text type="secondary">Dạng bài</Typography.Text>
            <Select
              aria-label="Dạng bài"
              allowClear
              style={{ width: "100%" }}
              value={fields.kind ?? undefined}
              disabled={!editable}
              options={view.kinds}
              onChange={(value) => set({ kind: (value as ArticleKind | undefined) ?? null })}
            />
          </label>
          <label style={{ flex: "1 1 200px" }}>
            <Typography.Text type="secondary">Nhóm chủ đề</Typography.Text>
            <Select
              aria-label="Nhóm chủ đề"
              allowClear
              style={{ width: "100%" }}
              value={fields.knowledge_topic_id ?? undefined}
              disabled={!editable}
              options={groups.map((group) => ({ value: group.id, label: group.name }))}
              onChange={(value) => set({ knowledge_topic_id: (value as number | undefined) ?? null })}
            />
          </label>
        </Flex>
        <label>
          <Typography.Text type="secondary">Gợi ý ảnh (từ khoá tìm ảnh và prompt ảnh AI)</Typography.Text>
          <Input
            aria-label="Gợi ý ảnh"
            value={fields.image_brief}
            maxLength={500}
            disabled={!editable}
            onChange={(e) => set({ image_brief: e.target.value })}
          />
        </label>
        <label>
          <Typography.Text type="secondary">Link ảnh có sẵn (mỗi dòng một link, tự thêm vào bài)</Typography.Text>
          <Input.TextArea
            aria-label="Link ảnh có sẵn"
            value={fields.image_urls.join("\n")}
            autoSize={{ minRows: 1, maxRows: 6 }}
            disabled={!editable}
            onChange={(e) => set({ image_urls: e.target.value.split("\n") })}
          />
        </label>
      </Flex>
    </FormDrawer>
  );
}

type ImportReport = { placed: number; backlog: number; moved_to_backlog: number; replaced: number; skipped: number };

/** "Nhập file JSON/CSV": each row checked and placed in a preview; the plan changes only on "Lưu kế hoạch". */
function ImportModal({
  fanpageId,
  onClose,
  onSaved,
}: {
  fanpageId: number;
  onClose: () => void;
  onSaved: (view: ArticlePlanView, report: ImportReport) => void;
}) {
  const { message } = App.useApp();
  const [file, setFile] = useState<File | null>(null);
  const [placement, setPlacement] = useState<"by_day_slot" | "fill_empty">("by_day_slot");
  const [conflict, setConflict] = useState<"to_backlog" | "overwrite" | "skip">("to_backlog");
  const [preview, setPreview] = useState<PlanImportPreview | null>(null);
  const [only, setOnly] = useState<"all" | "error" | "warning">("all");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  // Only the latest reading fills the preview, whatever order the answers arrive in.
  const latest = useRef(0);

  /** The file read again with the chosen placement and conflict mode: nothing is written until "Lưu kế hoạch". */
  async function read(next: { file?: File; placement?: typeof placement; conflict?: typeof conflict }) {
    const using = {
      file: next.file ?? file,
      placement: next.placement ?? placement,
      conflict: next.conflict ?? conflict,
    };
    if (next.file) setFile(next.file);
    if (next.placement) setPlacement(next.placement);
    if (next.conflict) setConflict(next.conflict);
    if (!using.file) return;
    const request = ++latest.current;
    setLoading(true);
    try {
      const found = await upload<PlanImportPreview>(`/article-plans/${fanpageId}/import`, using.file, {
        placement: using.placement,
        conflict: using.conflict,
      });
      if (request === latest.current) setPreview(found);
    } catch (err) {
      if (request === latest.current) {
        setPreview(null);
        message.error(errorMessage(err));
      }
    } finally {
      if (request === latest.current) setLoading(false);
    }
  }

  const saveable = preview ? preview.rows.filter((row) => row.check !== "error" && row.action === "add").length : 0;
  const shown = (preview?.rows ?? []).filter((row) => only === "all" || row.check === only);

  async function save() {
    if (!preview) return;
    setSaving(true);
    try {
      const saved = await api<ArticlePlanView & { report: ImportReport }>(
        `/article-plans/${fanpageId}/import/apply`,
        "POST",
        { rows: preview.rows, placement, conflict },
      );
      onSaved(saved, saved.report);
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal
      open
      width={1080}
      title={
        <Flex vertical>
          <span>Nhập file JSON/CSV</span>
          {preview && (
            <Typography.Text type="secondary" style={{ fontSize: 12, fontWeight: 400 }}>
              {preview.file_name} · {preview.rows.length} dòng
            </Typography.Text>
          )}
        </Flex>
      }
      onCancel={onClose}
      footer={
        <Flex justify="space-between" wrap gap={8}>
          <Flex gap={8}>
            <Button href="/api/article-plans/import-template?format=csv">Tải file mẫu CSV</Button>
            <Button href="/api/article-plans/import-template?format=json">Mẫu JSON</Button>
            {preview && preview.counts.error > 0 && (
              <Button onClick={() => download("dong-loi.csv", errorsCsv(preview.rows), "text/csv;charset=utf-8")}>
                Tải {preview.counts.error} dòng lỗi
              </Button>
            )}
          </Flex>
          <Flex gap={8}>
            <Button onClick={onClose}>Huỷ</Button>
            <Button type="primary" disabled={!preview || saveable === 0 || loading} loading={saving} onClick={save}>
              Lưu kế hoạch ({saveable} dòng)
            </Button>
          </Flex>
        </Flex>
      }
    >
      <Flex vertical gap={12}>
        <Flex gap={12} wrap align="center">
          <input
            ref={input}
            type="file"
            accept=".csv,.json"
            hidden
            aria-label="Chọn file kế hoạch"
            onChange={(event) => {
              const chosen = event.target.files?.[0];
              event.target.value = "";
              if (chosen) void read({ file: chosen });
            }}
          />
          <Button icon={<UploadOutlined />} onClick={() => input.current?.click()}>
            {file ? `Đổi file (${file.name})` : "Chọn file .csv hoặc .json"}
          </Button>
          <Typography.Text type="secondary">Cách xếp</Typography.Text>
          <Segmented
            aria-label="Cách xếp"
            value={placement}
            onChange={(value) => void read({ placement: value as typeof placement })}
            options={[
              { value: "by_day_slot", label: "Theo ngày + khung trong file" },
              { value: "fill_empty", label: "Xếp lần lượt vào ô trống" },
            ]}
          />
          <Typography.Text type="secondary">Ô đã có kịch bản</Typography.Text>
          <Select
            aria-label="Ô đã có kịch bản"
            value={conflict}
            style={{ width: 240 }}
            onChange={(value) => void read({ conflict: value })}
            options={[
              { value: "to_backlog", label: "Đưa kịch bản cũ vào Backlog" },
              { value: "overwrite", label: "Ghi đè" },
              { value: "skip", label: "Bỏ qua dòng mới" },
            ]}
          />
        </Flex>
        {loading && <Spin />}
        {preview && (
          <>
            <Flex gap={8} align="center" wrap>
              <StatusText tone="success">{preview.counts.ok} hợp lệ</StatusText>
              <StatusText tone="warning">{preview.counts.warning} cảnh báo</StatusText>
              <StatusText tone="danger">{preview.counts.error} lỗi</StatusText>
              <StatusText tone="idle">{preview.counts.backlog} vào Backlog</StatusText>
              <Select
                aria-label="Hiện dòng"
                size="small"
                value={only}
                onChange={setOnly}
                style={{ marginInlineStart: "auto", width: 150 }}
                options={[
                  { value: "all", label: "Hiện: Tất cả" },
                  { value: "error", label: "Hiện: Lỗi" },
                  { value: "warning", label: "Hiện: Cảnh báo" },
                ]}
              />
            </Flex>
            <Table<PlanImportRow>
              rowKey="row"
              size="small"
              dataSource={shown}
              pagination={{ pageSize: 50, hideOnSinglePage: true }}
              scroll={{ y: 420 }}
              data-testid="plan-import-preview"
              columns={[
                { title: "#", dataIndex: "row", width: 50 },
                { title: "Ngày", dataIndex: "day", width: 60, render: (value) => value ?? "" },
                { title: "Khung", dataIndex: "slot", width: 60, render: (value) => value ?? "" },
                { title: "Câu mở (hook)", dataIndex: "hook", ellipsis: true },
                {
                  title: "Bình luận",
                  key: "comments",
                  width: 90,
                  render: (_, row) => (row.pinned_comments.length ? `${row.pinned_comments.length}/5` : "—"),
                },
                {
                  title: "Hành động",
                  key: "action",
                  width: 150,
                  render: (_, row) => ACTION_LABELS[row.action],
                },
                {
                  title: "Kiểm tra",
                  key: "check",
                  width: 100,
                  render: (_, row) => (
                    <StatusText tone={toneOf(CHECK_TAGS[row.check].color)}>{CHECK_TAGS[row.check].label}</StatusText>
                  ),
                },
                {
                  title: "Lý do",
                  key: "reason",
                  width: 300,
                  render: (_, row) => (
                    <>
                      {[...row.errors, ...row.warnings, row.note].filter(Boolean).join(" · ") ||
                        (row.target === "backlog" ? "→ Backlog" : "Hợp lệ")}
                      {row.disclaimer_removed && (
                        <Tag style={{ marginInlineStart: 6 }}>Đã bỏ câu lưu ý y khoa (tự đăng ở bình luận)</Tag>
                      )}
                    </>
                  ),
                },
              ]}
            />
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              Kế hoạch hiện tại chưa thay đổi. Dòng Lỗi sẽ không được lưu; sửa file rồi nhập lại, hoặc tải danh sách
              dòng lỗi.
            </Typography.Text>
          </>
        )}
      </Flex>
    </Modal>
  );
}

type CommentScope = "missing" | "selected" | "unposted";

/** "Tạo bình luận ghim": the scripts to write comments for, how many that is, and "Ghi đè" for those edited by hand.
 *  The jobs run in the worker; the plan tab shows their progress and reads the plan again until they are done. */
function CommentsModal({
  fanpageId,
  view,
  selected,
  onClose,
  onQueued,
}: {
  fanpageId: number;
  view: ArticlePlanView;
  selected: number[];
  onClose: () => void;
  onQueued: (view: ArticlePlanView, queued: number) => void;
}) {
  const { message } = App.useApp();
  const [scope, setScope] = useState<CommentScope>(selected.length ? "selected" : "missing");
  const [overwrite, setOverwrite] = useState(false);
  const [count, setCount] = useState<{ total: number; edited: number; will_run: number } | null>(null);
  const [saving, setSaving] = useState(false);
  const pending = view.plan?.comments_pending ?? 0;

  useEffect(() => {
    let current = true;
    const query = new URLSearchParams({ scope, ids: selected.join(","), overwrite: String(overwrite) });
    api<{ total: number; edited: number; will_run: number }>(`/article-plans/${fanpageId}/comments/count?${query}`)
      .then((found) => current && setCount(found))
      .catch((err) => current && message.error(errorMessage(err)));
    return () => {
      current = false;
    };
  }, [fanpageId, scope, selected, overwrite, message]);

  async function start() {
    setSaving(true);
    try {
      const saved = await api<ArticlePlanView & { queued: number }>(
        `/article-plans/${fanpageId}/comments/bulk`,
        "POST",
        {
          scope,
          ids: selected,
          overwrite,
        },
      );
      onQueued(saved, saved.queued);
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal
      open
      title="Tạo bình luận ghim"
      onCancel={onClose}
      okText={`Tạo cho ${count?.will_run ?? 0} kịch bản`}
      cancelText="Đóng"
      okButtonProps={{ disabled: !count || count.will_run === 0 || pending > 0, loading: saving }}
      onOk={start}
    >
      <Flex vertical gap={12} data-testid="comments-dialog">
        <Typography.Text type="secondary">
          AI viết 5 bình luận cho mỗi kịch bản, bình luận đầu được ghim. Chạy ngầm theo hàng đợi; bạn có thể đóng hộp
          thoại này.
        </Typography.Text>
        <Select
          aria-label="Phạm vi"
          value={scope}
          onChange={(value: CommentScope) => setScope(value)}
          options={[
            { value: "missing", label: "Ô “Chưa dùng” còn thiếu bình luận" },
            { value: "selected", label: `Ô đang chọn (${selected.length})`, disabled: selected.length === 0 },
            { value: "unposted", label: "Toàn bộ ô chưa đăng" },
          ]}
        />
        <Checkbox checked={overwrite} onChange={(event) => setOverwrite(event.target.checked)}>
          Ghi đè cả kịch bản đã được sửa tay
        </Checkbox>
        {count && (
          <Typography.Text data-testid="comments-count">
            Sẽ tạo cho {count.will_run} kịch bản
            {!overwrite && count.edited > 0 ? ` (bỏ qua ${count.edited} kịch bản đã sửa tay)` : ""}.
          </Typography.Text>
        )}
        {pending > 0 && <Hint>Đang tạo bình luận cho {pending} kịch bản…</Hint>}
      </Flex>
    </Modal>
  );
}
