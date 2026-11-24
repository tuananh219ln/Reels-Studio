"use client";

import StatusText, { toneOf } from "@/components/StatusText";
import EmptyState from "@/components/EmptyState";
import { useMe } from "@/components/MeContext";
import {
  CheckCircleFilled,
  CheckOutlined,
  CopyOutlined,
  DeleteOutlined,
  EditOutlined,
  ExclamationCircleOutlined,
  LinkOutlined,
  HistoryOutlined,
  LeftOutlined,
  MoreOutlined,
  PlusOutlined,
  RightOutlined,
  TeamOutlined,
} from "@ant-design/icons";
import {
  App,
  Button,
  Card,
  Col,
  ConfigProvider,
  Dropdown,
  Flex,
  Segmented,
  Input,
  Row,
  Select,
  Spin,
  Switch,
  Tabs,
  theme,
  Tooltip,
  Typography,
} from "antd";
import type { MenuProps } from "antd";
import Link from "next/link";
import { Suspense, useCallback, useEffect, useState } from "react";
import {
  api,
  errorMessage,
  type AffiliateRevenue,
  type EditTemplates,
  type Knowledge,
  type KnowledgeTopic,
} from "@/lib/api";
import { useStoredChoice } from "@/lib/storedChoice";
import { useLeaveGuard } from "@/lib/unsaved";
import { keepOnlyInAddress, useUrlChoiceIf, useUrlId } from "@/lib/urlState";
import EditHistory, { lastEditText } from "@/components/EditHistory";
import GuideButton from "@/components/GuideButton";
import PageHeader from "@/components/PageHeader";
import TopicVideos from "@/components/knowledge/TopicVideos";
import TopicMedia from "@/components/knowledge/TopicMedia";
import TopicSchedule from "@/components/knowledge/TopicSchedule";
import TopicDocs from "@/components/knowledge/TopicDocs";
import StockOrderCard from "@/components/knowledge/StockOrderCard";
import GroupVideoModeCard from "@/components/knowledge/GroupVideoModeCard";
import GroupNoPeopleCard from "@/components/knowledge/GroupNoPeopleCard";
import GroupOutroCard from "@/components/knowledge/GroupOutroCard";
import GroupTextLookCard from "@/components/knowledge/GroupTextLookCard";
import { usePlanTabs } from "@/components/plan/PlanTab";
import { VoicePicker } from "@/components/video/VideoSettings";

export default function KnowledgePage() {
  // The group shown, its tab and its lists' filters are in the address, which a static page only knows in the browser.
  return (
    <Suspense fallback={null}>
      <Knowledge />
    </Suspense>
  );
}

function Knowledge() {
  const { message } = App.useApp();
  const { token } = theme.useToken();
  const { me } = useMe();
  const [data, setData] = useState<Knowledge | null>(null);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  // The group shown is in the address, with its tab and its lists' filters.
  const [chosen] = useUrlId("group");
  // Topics opened so far stay mounted (hidden when another is chosen): each box keeps its own unsaved text.
  const [opened, setOpened] = useState<number[]>([]);
  // The group list stays in view beside the group only when they sit side by side; stacked on a phone it scrolls away.
  // "Của tôi" (the groups of the member's Pages and the ones the member made) until "Cả đội" is chosen; it stays on this browser.
  const [scope, changeScope] = useStoredChoice<"mine" | "all">("knowledge-scope", "mine");
  // The group column folds to a narrow strip (a dot and two letters per group); kept on this browser.
  const [rail, setRail] = useStoredChoice<"open" | "folded">("knowledge-rail", "open");
  const folded = rail === "folded";

  useEffect(() => {
    api<Knowledge>("/knowledge")
      .then(setData)
      .catch((err) => message.error(errorMessage(err)));
  }, [message]);

  if (!data) {
    return (
      <Flex justify="center" style={{ padding: 48 }}>
        <Spin />
      </Flex>
    );
  }

  // The chosen topic, or the first one while none is chosen or the chosen one was deleted.
  const current = data.topics.find((topic) => topic.id === chosen) ?? data.topics[0] ?? null;
  // The group shown stays among the chips whatever the filter.
  // "Của tôi": the groups of the member's Pages and the groups the member made.
  const isMine = (topic: KnowledgeTopic) => topic.mine || topic.created_by_id === me.id;
  const listed = data.topics.filter((topic) => scope === "all" || isMine(topic) || topic.id === current?.id);
  const mounted = data.topics.filter((topic) => topic.id === current?.id || opened.includes(topic.id));

  function choose(id: number) {
    // Another group opens on its Video tab, as before, with none of the last group's filters.
    keepOnlyInAddress({ group: String(id) });
    setOpened((ids) => (ids.includes(id) ? ids : [...ids, id]));
  }

  async function add() {
    setBusy(true);
    try {
      const before = new Set(data?.topics.map((topic) => topic.id));
      const saved = await api<Knowledge>("/knowledge/topics", "POST", { name });
      setData(saved);
      setName("");
      const added = saved.topics.find((topic) => !before.has(topic.id));
      if (added) {
        choose(added.id);
      }
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  // "Cả đội" lists the groups under the member who made each, the member's own first.
  const makerName = (topic: KnowledgeTopic) =>
    topic.created_by_id === me.id ? `${topic.owner ?? "Bạn"} (bạn)` : (topic.owner ?? "Chưa có người tạo");
  const sections: { key: string; title: string; items: KnowledgeTopic[] }[] =
    scope === "all"
      ? [...new Set(listed.map(makerName))]
          .sort((x, y) => Number(y.endsWith("(bạn)")) - Number(x.endsWith("(bạn)")) || x.localeCompare(y, "vi"))
          .map((maker) => {
            const items = listed.filter((topic) => makerName(topic) === maker);
            return { key: maker, title: `${maker} · ${items.length}`, items };
          })
      : [{ key: "mine", title: "", items: listed }];
  const renderTopic = (topic: KnowledgeTopic) => {
    const active = topic.id === current?.id;
    const missing = missingRequired(topic);
    const tile = <GroupTile topic={topic} active={active} missing={missing.length > 0} />;
    if (folded) {
      return (
        <Tooltip
          key={topic.id}
          placement="right"
          title={`${topic.name} · ${topic.video_count} video${missing.length ? ` · còn thiếu: ${missing.join(", ")}` : ""}`}
        >
          <button
            type="button"
            aria-label={topic.name}
            aria-current={active ? "true" : undefined}
            onClick={() => choose(topic.id)}
            style={{ border: 0, background: "transparent", padding: 0, margin: "0 auto", cursor: "pointer" }}
          >
            {tile}
          </button>
        </Tooltip>
      );
    }
    const pages = topic.page_list.length;
    return (
      <button
        key={topic.id}
        type="button"
        aria-current={active ? "true" : undefined}
        onClick={() => choose(topic.id)}
        title={missing.length === 0 ? "Sẵn sàng tạo video" : `Còn thiếu: ${missing.join(", ")}`}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          width: "100%",
          border: 0,
          borderRadius: token.borderRadius,
          font: "inherit",
          textAlign: "left",
          cursor: "pointer",
          padding: "8px 10px",
          background: active ? token.colorPrimaryBg : "transparent",
          color: token.colorText,
        }}
      >
        {tile}
        <span style={{ flex: 1, minWidth: 0 }}>
          <span
            style={{
              display: "-webkit-box",
              WebkitLineClamp: 2,
              WebkitBoxOrient: "vertical",
              overflow: "hidden",
              fontWeight: active ? 600 : 500,
              color: active ? token.colorPrimaryText : undefined,
              lineHeight: 1.3,
            }}
          >
            {topic.name}
          </span>
          <span
            style={{
              display: "block",
              fontSize: 12,
              color: missing.length === 0 ? token.colorTextTertiary : token.colorWarningText,
            }}
          >
            {missing.length === 0
              ? `${topic.video_count} video · ${pages} Page`
              : `${topic.video_count} video · thiếu ${missing[0]}`}
          </span>
        </span>
      </button>
    );
  };

  return (
    <>
      <PageHeader
        title="Kho kiến thức"
        actions={<GuideButton screen="knowledge" />}
        description="Mỗi nhóm chủ đề có video, prompt, từ cấm và kế hoạch 30 ngày riêng. Nhóm được chọn khi tạo video; bản nhân bản dùng nhóm của video gốc."
      />
      {/* A group is a workspace: the groups in a column on the left (above the group on a phone), each with a dot that
          says whether it still lacks something, and the group itself, with its checklist, on the right. */}
      {/* One card: the group column is its left edge, the group the rest. */}
      <Flex
        align="stretch"
        wrap
        style={{
          background: token.colorBgContainer,
          border: `1px solid ${token.colorBorderSecondary}`,
          borderRadius: token.borderRadiusLG,
          overflow: "hidden",
        }}
      >
        <Flex
          vertical
          gap={folded ? 6 : 12}
          component="aside"
          aria-label="Nhóm chủ đề"
          style={{
            flex: folded ? "0 0 60px" : "0 0 256px",
            width: folded ? 60 : 256,
            maxWidth: "100%",
            background: token.colorFillQuaternary,
            borderInlineEnd: `1px solid ${token.colorBorderSecondary}`,
            padding: folded ? "10px 0" : 12,
          }}
        >
          <Flex justify={folded ? "center" : "space-between"} align="center" gap={4}>
            {!folded && (
              <Typography.Text strong style={{ flex: 1, paddingInlineStart: 4 }}>
                Nhóm
              </Typography.Text>
            )}
            {!folded && (
              <EditHistory
                entityType="knowledge_topic"
                field="name"
                title="Nhóm chủ đề"
                kind="value"
                trigger={(open) => (
                  <Tooltip title="Nhóm đã tạo, đổi tên, xoá">
                    <Button
                      size="small"
                      type="text"
                      aria-label="Lịch sử nhóm chủ đề"
                      icon={<HistoryOutlined />}
                      onClick={open}
                    />
                  </Tooltip>
                )}
              />
            )}
            <Tooltip title={folded ? "Mở rộng danh sách nhóm" : "Thu gọn danh sách nhóm"}>
              <Button
                size="small"
                type="text"
                aria-label={folded ? "Mở rộng danh sách nhóm" : "Thu gọn danh sách nhóm"}
                icon={folded ? <RightOutlined /> : <LeftOutlined />}
                onClick={() => setRail(folded ? "open" : "folded")}
              />
            </Tooltip>
          </Flex>
          {!folded && (
            // The same underlined tabs as the group's own, not a second kind of switch.
            <div aria-label="Lọc nhóm" role="group">
              <Tabs
                size="small"
                activeKey={scope}
                onChange={(key) => changeScope(key as "mine" | "all")}
                tabBarStyle={{ margin: 0 }}
                items={[
                  {
                    key: "mine",
                    label: (
                      <span>
                        Của tôi <ScopeCount n={data.topics.filter(isMine).length} />
                      </span>
                    ),
                  },
                  {
                    key: "all",
                    label: (
                      <span>
                        Cả đội <ScopeCount n={data.topics.length} />
                      </span>
                    ),
                  },
                ]}
              />
            </div>
          )}
          <Flex vertical gap={folded ? 8 : 4} data-testid="topic-list">
            {listed.length === 0 && (
              <Typography.Text type="secondary">
                Bạn chưa có nhóm nào. Chọn “Cả đội” để xem các nhóm của mọi người, hoặc thêm một nhóm mới.
              </Typography.Text>
            )}
            {sections.map(({ key, title, items }) => (
              <Flex vertical gap={folded ? 8 : 4} key={key}>
                {title && !folded && (
                  <Typography.Text type="secondary" style={{ fontSize: 12, padding: "8px 10px 0" }}>
                    {title}
                  </Typography.Text>
                )}
                {items.map(renderTopic)}
              </Flex>
            ))}
          </Flex>
          {!folded && (
            <Input
              // A quiet dashed field at the foot of the list; the tick shows once there is a name.
              style={{ borderStyle: "dashed", background: "transparent" }}
              aria-label="Tên nhóm chủ đề mới"
              placeholder="Thêm nhóm mới…"
              prefix={<PlusOutlined style={{ color: token.colorTextTertiary }} />}
              suffix={
                name.trim() ? (
                  <Tooltip title="Thêm nhóm">
                    <Button
                      size="small"
                      type="primary"
                      shape="circle"
                      aria-label="Thêm nhóm"
                      icon={<CheckOutlined />}
                      loading={busy}
                      onClick={add}
                    />
                  </Tooltip>
                ) : (
                  <span />
                )
              }
              maxLength={100}
              value={name}
              onChange={(event) => setName(event.target.value)}
              onPressEnter={() => name.trim() && add()}
            />
          )}
        </Flex>
        <div style={{ flex: "1 1 560px", minWidth: 0 }}>
          {current === null ? (
            <Card>
              <EmptyState description="Chưa có nhóm chủ đề nào. Thêm một nhóm ở bên trái." />
            </Card>
          ) : (
            mounted.map((topic) => (
              <div key={topic.id} hidden={topic.id !== current.id}>
                <TopicBody
                  topic={topic}
                  defaults={data}
                  onSaved={setData}
                  onOpenTopic={choose}
                  visible={topic.id === current.id}
                />
              </div>
            ))
          )}
        </div>
      </Flex>
    </>
  );
}

/** A group's tile: its two initials and a dot that is green when it can make videos and amber while it cannot. The same
 * tile is the folded column and the start of each row of the open one. */
function GroupTile({ topic, active, missing }: { topic: KnowledgeTopic; active: boolean; missing: boolean }) {
  const { token } = theme.useToken();
  return (
    <span
      style={{
        position: "relative",
        flex: "none",
        width: 36,
        height: 36,
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        borderRadius: token.borderRadius,
        border: `1px solid ${active ? token.colorPrimaryBorder : "transparent"}`,
        background: active ? token.colorBgContainer : token.colorFillSecondary,
        color: active ? token.colorPrimaryText : token.colorTextSecondary,
        fontSize: 13,
        fontWeight: 600,
      }}
    >
      {initials(topic.name)}
      <span
        aria-hidden
        style={{
          position: "absolute",
          top: -3,
          right: -3,
          width: 10,
          height: 10,
          borderRadius: "50%",
          border: `2px solid ${token.colorBgContainer}`,
          background: missing ? token.colorWarning : token.colorSuccess,
        }}
      />
    </span>
  );
}

/** Two letters for a group in the folded column: the first of its first two words ("Già Mà Khỏe" → "GM"). */
function initials(name: string): string {
  const words = name
    .trim()
    .split(/\s+/)
    .filter((word) => /[\p{L}\p{N}]/u.test(word));
  return (words.length > 1 ? words[0][0] + words[1][0] : (words[0] ?? "?").slice(0, 2)).toUpperCase();
}

/** What a group must have to make and post videos: a Page that posts it and a script prompt (the owner's rule,
 * 2026-11-25). A document, a 30-day plan and an approved product are only worth having. */
function missingRequired(topic: KnowledgeTopic): string[] {
  return [
    ...(topic.readiness.pages > 0 ? [] : ["Page đăng nhóm"]),
    ...(topic.script_prompt ? [] : ["prompt viết kịch bản"]),
  ];
}

/** A group several Pages post: "Page" picks one to read the group for (its videos, its calendar, its orders, its
 * comment sets); "Tất cả Page" is the whole group. One Page's orders are those whose links carry its code. */
function PageScope({
  topic,
  chosen,
  onChoose,
}: {
  topic: KnowledgeTopic;
  chosen: number | null;
  onChoose: (id: number | null) => void;
}) {
  const { token } = theme.useToken();
  const [revenue, setRevenue] = useState<AffiliateRevenue | null>(null);
  useEffect(() => {
    if (chosen === null) return;
    let live = true;
    api<AffiliateRevenue>(`/affiliate-accounts/revenue?days=30&fanpage_id=${chosen}`).then(
      (found) => live && setRevenue(found),
      () => live && setRevenue(null),
    );
    return () => {
      live = false;
    };
  }, [chosen]);
  const page = topic.page_list.find((one) => one.id === chosen);
  return (
    <Flex vertical gap={8} data-testid="page-scope">
      <Flex gap={12} align="center" wrap>
        <Typography.Text type="secondary">Page</Typography.Text>
        <Segmented<number>
          aria-label="Xem nhóm theo Page"
          value={chosen ?? 0}
          onChange={(value) => onChoose(value === 0 ? null : value)}
          options={[
            { value: 0, label: "Tất cả Page" },
            ...topic.page_list.map((one) => ({ value: one.id, label: one.name })),
          ]}
        />
      </Flex>
      {page && (
        <Flex
          gap={16}
          align="center"
          wrap
          style={{
            border: `1px solid ${token.colorBorderSecondary}`,
            borderRadius: token.borderRadiusLG,
            padding: "8px 14px",
          }}
        >
          <Typography.Text strong>{page.name}</Typography.Text>
          <Typography.Text type="secondary">
            {revenue === null
              ? "Đơn 30 ngày: —"
              : `Đơn 30 ngày: ${revenue.orders} đơn, ${revenue.commission.toLocaleString("vi-VN")}đ hoa hồng`}
          </Typography.Text>
          <Tooltip title="Đơn chỉ gắn về Page khi link mang mã của Page. Link lưu sẵn của sản phẩm mang mã của một Page, nên đơn của Page kia có thể không hiện ở đây.">
            <Typography.Text type="secondary">ⓘ</Typography.Text>
          </Tooltip>
          <Flex gap={8} style={{ marginInlineStart: "auto" }}>
            <Button size="small" href={`/affiliate?tab=sets&page=${page.id}`}>
              Bộ bình luận của Page
            </Button>
            <Button size="small" href={`/fanpages/${page.id}?tab=schedule`}>
              Lịch đăng của Page
            </Button>
          </Flex>
        </Flex>
      )}
    </Flex>
  );
}

/** A tab that starts a group (the work, the knowledge, the settings): a thin line before it, its name unchanged. */
function GroupStart({ children }: { children: React.ReactNode }) {
  const { token } = theme.useToken();
  return (
    <span
      style={{ borderInlineStart: `1px solid ${token.colorBorder}`, paddingInlineStart: 14, marginInlineStart: -4 }}
    >
      {children}
    </span>
  );
}

/** "Sẵn sàng tạo video": what the group still lacks, each with the button that does it. It folds to one line once the
 * group has everything. */
function Readiness({ topic, open }: { topic: KnowledgeTopic; open: (tab: string) => void }) {
  const { token } = theme.useToken();
  const { readiness } = topic;
  const steps: { key: string; required: boolean; done: boolean; text: string; action: React.ReactNode }[] = [
    {
      key: "pages",
      required: true,
      done: readiness.pages > 0,
      text: readiness.pages > 0 ? `Có ${readiness.pages} Page đăng nhóm này` : "Chưa có Page nào đăng nhóm này",
      action: (
        <Button size="small" href="/fanpages">
          Quản lý kênh
        </Button>
      ),
    },
    {
      key: "prompt",
      required: true,
      done: Boolean(topic.script_prompt),
      text: topic.script_prompt
        ? "Đã có prompt viết kịch bản"
        : "Nhóm chưa có prompt viết kịch bản nên chưa tạo được video bằng AI trên web (vẫn tạo được qua MCP hoặc tự viết kịch bản)",
      action: (
        <Button size="small" onClick={() => open("prompts")}>
          Thêm prompt
        </Button>
      ),
    },
    {
      key: "docs",
      required: false,
      done: readiness.docs > 0,
      text: readiness.docs > 0 ? `Có ${readiness.docs} tài liệu vận hành` : "Chưa có tài liệu vận hành",
      action: (
        <Button size="small" onClick={() => open("docs")}>
          Thêm tài liệu
        </Button>
      ),
    },
    {
      key: "plan",
      required: false,
      done: readiness.plan_started,
      text: readiness.plan_started ? "Đã lập kế hoạch 30 ngày" : "Chưa lập kế hoạch 30 ngày",
      action: (
        <Button size="small" onClick={() => open("plan")}>
          Lập kế hoạch
        </Button>
      ),
    },
    {
      key: "products",
      required: false,
      done: readiness.products > 0,
      text:
        readiness.products > 0
          ? `Có ${readiness.products} sản phẩm affiliate đã duyệt`
          : "Chưa có sản phẩm affiliate đã duyệt",
      action: (
        <Button size="small" href={`/affiliate?tab=products&group=${topic.id}`}>
          Mở Affiliate
        </Button>
      ),
    },
  ];
  const required = steps.filter((step) => step.required);
  const optional = steps.filter((step) => !step.required);
  const requiredMissing = required.filter((step) => !step.done).length;
  const optionalMissing = optional.filter((step) => !step.done);
  // Open while a required step is missing; else one line the member may unfold. A pick of the member's stays.
  const [pick, setPick] = useState<boolean | null>(null);
  const expanded = pick ?? requiredMissing > 0;
  const allDone = requiredMissing === 0 && optionalMissing.length === 0;
  const row = (step: (typeof steps)[number]) => (
    <Flex key={step.key} gap={8} align="center">
      {step.done ? (
        <CheckCircleFilled style={{ color: token.colorSuccess }} />
      ) : (
        <ExclamationCircleOutlined style={{ color: step.required ? token.colorWarning : token.colorTextTertiary }} />
      )}
      <Typography.Text type={step.done ? "secondary" : undefined} style={{ flex: 1 }}>
        {step.text}
      </Typography.Text>
      {!step.done && step.action}
    </Flex>
  );
  return (
    <Flex
      vertical
      gap={6}
      data-testid="group-ready"
      style={{
        border: `1px solid ${token.colorBorderSecondary}`,
        borderRadius: token.borderRadiusLG,
        background: token.colorFillQuaternary,
        padding: "8px 14px",
      }}
    >
      <Flex
        component="button"
        justify="space-between"
        align="center"
        gap={8}
        aria-expanded={expanded}
        onClick={() => setPick(!expanded)}
        style={{
          border: 0,
          background: "transparent",
          padding: 0,
          font: "inherit",
          cursor: "pointer",
          textAlign: "left",
        }}
      >
        <Typography.Text strong type={requiredMissing > 0 ? undefined : "success"}>
          {requiredMissing === 0 ? (
            <CheckCircleFilled />
          ) : (
            <ExclamationCircleOutlined style={{ color: token.colorWarning }} />
          )}{" "}
          {requiredMissing === 0
            ? "Sẵn sàng tạo video"
            : `Chưa sẵn sàng: thiếu ${required.filter((step) => !step.done).length}/${required.length} mục bắt buộc`}
        </Typography.Text>
        <Typography.Text type="secondary">
          {allDone
            ? "đủ cả"
            : optionalMissing.length > 0
              ? `nên có thêm: ${optionalMissing.map((step) => OPTIONAL_NAMES[step.key]).join(", ")}`
              : ""}{" "}
          {expanded ? "▴" : "▾"}
        </Typography.Text>
      </Flex>
      {expanded && (
        <>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            Bắt buộc
          </Typography.Text>
          {required.map(row)}
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            Nên có
          </Typography.Text>
          {optional.map(row)}
        </>
      )}
    </Flex>
  );
}

const OPTIONAL_NAMES: Record<string, string> = {
  docs: "tài liệu",
  plan: "kế hoạch 30 ngày",
  products: "sản phẩm affiliate",
};

/** The number beside "Của tôi" and "Cả đội": a small grey count, not part of the label's words. */
function ScopeCount({ n }: { n: number }) {
  return <span style={{ opacity: 0.55, fontWeight: 500 }}>{n}</span>;
}

type PromptField =
  "script_prompt" | "clone_prompt" | "learn_prompt" | "analyze_prompt" | "revise_prompt" | "article_prompt";

/** The prompts a group holds, in the order of the menu; `defaultKey` names the app's own text on `Knowledge`. An
 * empty script or clone prompt is empty (the group cannot make videos without a script prompt); the other prompts
 * are empty in the database when they use the default. */
const PROMPTS: {
  field: PromptField;
  label: string;
  title: string;
  defaultKey: keyof Knowledge;
  emptyIsDefault: boolean;
}[] = [
  {
    field: "script_prompt",
    label: "Viết kịch bản",
    title: "Prompt viết kịch bản",
    defaultKey: "default_script_prompt",
    emptyIsDefault: false,
  },
  {
    field: "clone_prompt",
    label: "Nhân bản",
    title: "Prompt nhân bản",
    defaultKey: "default_clone_prompt",
    emptyIsDefault: false,
  },
  {
    field: "learn_prompt",
    label: "Học từ video mẫu",
    title: "Prompt học từ video mẫu",
    defaultKey: "default_learn_prompt",
    emptyIsDefault: true,
  },
  {
    field: "analyze_prompt",
    label: "Phân tích video mẫu",
    title: "Prompt phân tích video mẫu",
    defaultKey: "default_analyze_prompt",
    emptyIsDefault: true,
  },
  {
    field: "revise_prompt",
    label: "Sửa theo góp ý",
    title: "Prompt sửa theo góp ý",
    defaultKey: "default_revise_prompt",
    emptyIsDefault: true,
  },
  {
    field: "article_prompt",
    label: "Viết bài",
    title: "Prompt viết bài",
    defaultKey: "default_article_prompt",
    emptyIsDefault: true,
  },
];

/** The parts of a group, as its history names them. */
const TOPIC_FIELDS: Record<string, string> = {
  name: "Tên nhóm",
  script_prompt: "Prompt viết kịch bản",
  clone_prompt: "Prompt nhân bản",
  learn_prompt: "Prompt học từ video mẫu",
  analyze_prompt: "Prompt phân tích video mẫu",
  revise_prompt: "Prompt sửa theo góp ý",
  article_prompt: "Prompt viết bài",
  plan_prompt: "Prompt kế hoạch",
  banned_words: "Từ cấm",
  photo_hint: "Gợi ý tìm ảnh",
  voice_id: "Giọng mặc định",
  voice_backup_id: "Giọng phụ",
  video_mode: "Kiểu video",
  text_look: "Chữ & phụ đề",
  text_ai: "AI chọn kiểu chữ cho từng video",
  outro_cta: "Cảnh kết Theo dõi & Chia sẻ",
  stock_order: "Thứ tự nguồn ảnh",
  media_folder: "Thư mục tư liệu",
  templates: "Mẫu dựng của nhóm",
  edit_template_default: "Mẫu cho video mới",
  plan_start_date: "Ngày bắt đầu kế hoạch",
  plan_per_day: "Số ý tưởng mỗi ngày",
  plan_post_times: "Giờ đăng gợi ý",
  video_target: "Số video mục tiêu",
};

type PromptState = "edited" | "default" | "empty";

function promptState(topic: KnowledgeTopic, defaults: Knowledge, prompt: (typeof PROMPTS)[number]): PromptState {
  const saved = topic[prompt.field];
  if (!saved.trim()) {
    return prompt.emptyIsDefault ? "default" : "empty";
  }
  return saved.trim() === String(defaults[prompt.defaultKey]).trim() ? "default" : "edited";
}

const STATE_TAGS: Record<PromptState, { label: string; color?: string }> = {
  edited: { label: "Đã sửa", color: "orange" },
  default: { label: "Mặc định" },
  empty: { label: "Trống", color: "gold" },
};

const PROMPT_HELP: Record<PromptField, React.ReactNode> = {
  script_prompt: (
    <>
      Chỗ điền <Typography.Text code>[Chủ đề]</Typography.Text> được thay bằng chủ đề của video; nếu xóa chỗ điền này,
      chủ đề được nối vào cuối prompt. Video tạo từ kế hoạch 30 ngày còn điền{" "}
      <Typography.Text code>[Nhóm nỗi đau]</Typography.Text>, <Typography.Text code>[Nỗi đau]</Typography.Text> và{" "}
      <Typography.Text code>[Góc hook]</Typography.Text> của ý tưởng (thiếu chỗ điền thì nối vào cuối).
    </>
  ),
  clone_prompt: (
    <>
      Dùng khi bấm “Nhân bản”. Các chỗ điền <Typography.Text code>[tiêu đề]</Typography.Text>,{" "}
      <Typography.Text code>[chủ đề]</Typography.Text>,{" "}
      <Typography.Text code>[kịch bản đã sửa của video gốc]</Typography.Text> và{" "}
      <Typography.Text code>[yêu cầu đổi]</Typography.Text> được thay bằng dữ liệu của video gốc; chỗ điền nào bị xóa
      thì thông tin đó được nối vào cuối prompt.
    </>
  ),
  learn_prompt: (
    <>
      Dùng khi tạo video “Từ video mẫu”: AI xem khung hình và lời thoại của video mẫu rồi viết kịch bản mới. Các chỗ
      điền <Typography.Text code>[chủ đề]</Typography.Text>,{" "}
      <Typography.Text code>[lời thoại video mẫu]</Typography.Text>,{" "}
      <Typography.Text code>[phân tích video mẫu]</Typography.Text> và{" "}
      <Typography.Text code>[khung hình video mẫu]</Typography.Text> được thay bằng dữ liệu của video mẫu; chỗ điền nào
      bị xóa thì thông tin đó được nối vào cuối prompt. Đoạn clip cho từng cảnh do app tự yêu cầu.
    </>
  ),
  analyze_prompt: (
    <>
      Dùng ở các cách “Hai bước tự động”, “Duyệt phân tích trước” và “Dùng mẫu đã học”, khi AI phân tích video mẫu trước
      khi viết. Chỗ điền <Typography.Text code>[lời thoại video mẫu]</Typography.Text> và{" "}
      <Typography.Text code>[khung hình video mẫu]</Typography.Text> được thay bằng dữ liệu của video mẫu.
    </>
  ),
  revise_prompt: (
    <>
      Dùng khi bấm “Nhờ AI sửa” trong xem trước video. Chỗ điền{" "}
      <Typography.Text code>[kịch bản hiện tại]</Typography.Text> được thay bằng các cảnh của video (chữ, lời đọc, lớp
      chữ và giây của từng cảnh), còn <Typography.Text code>[góp ý]</Typography.Text> bằng các góp ý đang chờ, kèm giây
      và cảnh của từng góp ý.
    </>
  ),
  article_prompt: (
    <>
      Dùng khi bấm “AI viết” ở mục Bài viết. Chỗ điền <Typography.Text code>[Chủ đề]</Typography.Text>,{" "}
      <Typography.Text code>[Dạng bài]</Typography.Text>, <Typography.Text code>[Nhóm chủ đề]</Typography.Text> và{" "}
      <Typography.Text code>[Bình luận gốc]</Typography.Text> được thay bằng thông tin của bài; chỗ nào bị xóa thì thông
      tin đó được nối vào cuối prompt. Câu “Tham khảo, không thay thế tư vấn bác sĩ” do app tự thêm.
    </>
  ),
};

function TopicBody({
  topic,
  defaults,
  onSaved,
  onOpenTopic,
  visible,
}: {
  topic: KnowledgeTopic;
  defaults: Knowledge;
  onSaved: (data: Knowledge) => void;
  /** Opens another group (the copy "Nhân bản nhóm" makes). */
  onOpenTopic: (id: number) => void;
  /** The group shown: its tab is the address's; a group opened earlier and hidden keeps its own. */
  visible: boolean;
}) {
  const [chosenTab, setTab] = useUrlChoiceIf<string>(visible, "tab", "videos");
  // A group several Pages post can be read for one of them; the choice is in the address and kept across its tabs.
  const [pageParam, setPageParam] = useUrlChoiceIf<string | null>(visible, "page", null);
  const chosenPage = topic.page_list.find((one) => String(one.id) === pageParam) ?? null;
  const keepGroup = () =>
    keepOnlyInAddress({ group: String(topic.id), ...(chosenPage ? { page: String(chosenPage.id) } : {}) });
  // "Mẫu dựng" moved into "Cài đặt nhóm" (2026-11-10): an old link to it opens that tab.
  const tab = chosenTab === "templates" ? "words" : chosenTab;
  const { me } = useMe();
  const path = `/knowledge/topics/${topic.id}`;
  // "Cho cả đội sửa" off and the group not mine: its prompts, words and templates are only read here.
  const locked = !topic.team_edit && topic.created_by_id !== me.id;
  const readOnly = (children: React.ReactNode) => (
    <ConfigProvider componentDisabled={locked}>{children}</ConfigProvider>
  );
  const { tabs: planTabs, dialogs: planDialogs } = usePlanTabs(topic.id, visible);
  const update = async (body: Partial<KnowledgeTopic>) => {
    const saved = await api<Knowledge>(path, "PATCH", body);
    onSaved(saved);
    return saved.topics.find((item) => item.id === topic.id) ?? topic;
  };
  // After a version is put back from "Lịch sử": the cards follow the group's new values.
  const reload = async () => onSaved(await api<Knowledge>("/knowledge"));
  const edited = PROMPTS.filter((prompt) => promptState(topic, defaults, prompt) === "edited").length;

  // Not a Card itself: the cards inside are found by their own title.
  return (
    <Flex vertical gap={4} data-topic={topic.name} style={{ padding: "16px 20px 20px" }}>
      <TopicHeader
        topic={topic}
        path={path}
        update={update}
        onSaved={onSaved}
        onOpenTopic={onOpenTopic}
        summary={
          <>
            {topic.video_count} video, {edited} prompt đã sửa
            {locked && (
              <Typography.Text data-testid="group-locked">
                , chỉ {topic.owner ?? "người tạo nhóm"} sửa được nhóm này
              </Typography.Text>
            )}
            {topic.last_edit && (
              <>
                {", "}
                <EditHistory
                  entityType="knowledge_topic"
                  entityId={topic.id}
                  title={topic.name}
                  kind="fields"
                  fieldLabels={TOPIC_FIELDS}
                  trigger={(open) => (
                    <Typography.Link
                      id={`topic-history-${topic.id}`}
                      onClick={open}
                      style={{ fontSize: "inherit", color: "inherit", textDecoration: "underline dotted" }}
                    >
                      <HistoryOutlined /> {lastEditText(topic.last_edit!, TOPIC_FIELDS)}
                    </Typography.Link>
                  )}
                />
              </>
            )}
          </>
        }
      />
      <Readiness
        topic={topic}
        open={(key) => {
          if (visible) keepGroup();
          setTab(key);
        }}
      />
      {topic.page_list.length >= 2 && (
        <PageScope
          topic={topic}
          chosen={chosenPage?.id ?? null}
          onChoose={(id) => {
            if (visible) keepGroup();
            setPageParam(id === null ? null : String(id));
          }}
        />
      )}
      <Tabs
        activeKey={tab}
        onChange={(next) => {
          // A tab's list starts without the last tab's filters.
          if (visible) keepGroup();
          setTab(next);
        }}
        items={[
          {
            key: "videos",
            label: `Video (${topic.video_count})`,
            children: (
              <TopicVideos
                topicId={topic.id}
                fanpageId={chosenPage?.id}
                canCreate={Boolean(topic.script_prompt)}
                visible={visible}
              />
            ),
          },
          ...planTabs,
          {
            key: "schedule",
            label: "Lịch đăng",
            children: (
              <TopicSchedule topicId={topic.id} fanpageId={chosenPage?.id} visible={visible && tab === "schedule"} />
            ),
          },
          {
            key: "media",
            label: <GroupStart>Tư liệu</GroupStart>,
            children: <TopicMedia topic={topic} update={update} locked={locked} />,
          },
          {
            key: "docs",
            label: "Tài liệu",
            children: <TopicDocs topicId={topic.id} canEdit={!locked} visible={visible && tab === "docs"} />,
          },
          {
            key: "prompts",
            label: "Prompt",
            children: readOnly(<PromptsPanel topic={topic} defaults={defaults} update={update} reload={reload} />),
          },
          {
            key: "words",
            label: <GroupStart>Cài đặt nhóm</GroupStart>,
            children: readOnly(
              <Flex vertical gap={24}>
                <section aria-labelledby={`script-${topic.id}`}>
                  <SectionHead
                    id={`script-${topic.id}`}
                    title="Viết kịch bản & tìm ảnh"
                    hint="AI đọc phần này mỗi lần viết kịch bản cho nhóm và tìm ảnh cho từng cảnh."
                  />
                  <Row gutter={[16, 16]}>
                    <Col xs={24} xl={12}>
                      <BannedWordsCard
                        topicId={topic.id}
                        initial={topic.banned_words}
                        update={update}
                        reload={reload}
                      />
                    </Col>
                    <Col xs={24} xl={12}>
                      <Flex vertical gap={16}>
                        <PhotoHintCard topicId={topic.id} initial={topic.photo_hint} update={update} reload={reload} />
                        <StockOrderCard
                          key={topic.stock_order.join()}
                          initial={topic.stock_order}
                          custom={topic.stock_order_custom}
                          update={update}
                        />
                      </Flex>
                    </Col>
                  </Row>
                </section>
                <section aria-labelledby={`new-${topic.id}`}>
                  <SectionHead
                    id={`new-${topic.id}`}
                    title="Video mới của nhóm"
                    hint={
                      "Mọi video tạo mới trong nhóm (trên web, trợ lý qua MCP) bắt đầu theo phần này, " +
                      "thay cho Thiết lập mặc định của người tạo. Chỉnh riêng trên từng video vẫn được; video đã có không đổi."
                    }
                  />
                  <Row gutter={[16, 16]}>
                    <Col xs={24} xl={12}>
                      <Flex vertical gap={16}>
                        <GroupVideoModeCard topic={topic} update={update} />
                        <GroupNoPeopleCard topic={topic} update={update} />
                        <GroupOutroCard topic={topic} update={update} />
                        <GroupVoiceCard
                          topicId={topic.id}
                          initial={topic.voice_id}
                          initialBackup={topic.voice_backup_id}
                          update={update}
                          reload={reload}
                        />
                        <GroupTemplatesCard topic={topic} update={update} />
                      </Flex>
                    </Col>
                    <Col xs={24} xl={12}>
                      <GroupTextLookCard
                        topic={topic}
                        start={defaults.default_text_look}
                        update={update}
                        reload={async (data) => onSaved(data ?? (await api<Knowledge>("/knowledge")))}
                      />
                    </Col>
                  </Row>
                </section>
              </Flex>,
            ),
          },
        ]}
      />
      {planDialogs}
    </Flex>
  );
}

/** A part of "Cài đặt nhóm": a heading and one line on what it is for. */
function SectionHead({ id, title, hint }: { id: string; title: string; hint: string }) {
  return (
    <div style={{ marginBottom: 12 }}>
      <Typography.Title level={5} id={id} style={{ margin: 0 }}>
        {title}
      </Typography.Title>
      <Typography.Text type="secondary">{hint}</Typography.Text>
    </div>
  );
}

/** The group's name as the heading, renamed in place ("Đổi tên"), and "Xoá nhóm" under "⋯" (only while it has no
 * videos, as a video keeps its group). */
function TopicHeader({
  topic,
  path,
  update,
  onSaved,
  onOpenTopic,
  summary,
}: {
  topic: KnowledgeTopic;
  path: string;
  update: Update;
  onSaved: (data: Knowledge) => void;
  onOpenTopic: (id: number) => void;
  summary: React.ReactNode;
}) {
  const { message, modal } = App.useApp();
  const { me } = useMe();
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(topic.name);
  const locked = !topic.team_edit && topic.created_by_id !== me.id;
  const [busy, setBusy] = useState(false);
  const isMaker = topic.created_by_id === me.id;

  async function rename() {
    setBusy(true);
    try {
      setValue((await update({ name: value })).name);
      setEditing(false);
      message.success("Đã lưu tên nhóm chủ đề");
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  function remove() {
    modal.confirm({
      title: `Xoá nhóm “${topic.name}”?`,
      content: "Prompt, từ cấm và kế hoạch 30 ngày của nhóm sẽ bị xoá.",
      okText: "Xoá",
      cancelText: "Huỷ",
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          onSaved(await api<Knowledge>(path, "DELETE"));
        } catch (err) {
          message.error(errorMessage(err));
        }
      },
    });
  }

  async function duplicate() {
    try {
      const saved = await api<Knowledge>(`/knowledge/topics/${topic.id}/duplicate`, "POST");
      onSaved(saved);
      // The newest of the copies of this group is the one just made.
      const made = saved.topics
        .filter((other) => other.id !== topic.id && other.name.startsWith(`${topic.name} (bản sao`))
        .sort((x, y) => y.id - x.id)[0];
      if (made) onOpenTopic(made.id);
      message.success(`Đã nhân bản thành “${made?.name ?? "nhóm mới"}”`);
    } catch (err) {
      message.error(errorMessage(err));
    }
  }

  async function run(call: () => Promise<unknown>, done: string) {
    try {
      await call();
      message.success(done);
    } catch (err) {
      message.error(errorMessage(err));
    }
  }

  // "Quản lý nhóm": everything done to the group itself, in one menu.
  const items: MenuProps["items"] = [
    {
      key: "rename",
      icon: <EditOutlined />,
      disabled: locked,
      label: "Đổi tên nhóm",
      onClick: () => setEditing(true),
    },
    { key: "duplicate", icon: <CopyOutlined />, label: "Nhân bản nhóm", onClick: duplicate },
    {
      key: "history",
      icon: <HistoryOutlined />,
      disabled: !topic.last_edit,
      label: "Lịch sử thay đổi",
      onClick: () => document.getElementById(`topic-history-${topic.id}`)?.click(),
    },
    ...(topic.created_by_id === null
      ? [
          {
            key: "claim",
            icon: <TeamOutlined />,
            label: "Nhận nhóm",
            onClick: () =>
              run(
                async () => onSaved(await api<Knowledge>(`/knowledge/topics/${topic.id}/owner`, "POST")),
                "Đã nhận nhóm",
              ),
          },
        ]
      : isMaker
        ? [
            {
              key: "team",
              icon: <TeamOutlined />,
              // The menu stays open while the switch is turned, as a switch in a menu should.
              label: (
                <Tooltip
                  placement="left"
                  title="Tắt: chỉ bạn sửa được prompt, từ cấm, mẫu dựng và kế hoạch của nhóm; cả đội vẫn tạo video từ nhóm."
                >
                  <Flex justify="space-between" align="center" gap={16}>
                    Cho cả đội sửa
                    <Switch
                      size="small"
                      aria-label="Cho cả đội sửa"
                      checked={topic.team_edit}
                      onClick={(_, event) => event.stopPropagation()}
                      onChange={(on) =>
                        run(
                          () => update({ team_edit: on }),
                          on ? "Cả đội sửa được nhóm này" : "Chỉ bạn sửa được nhóm này",
                        )
                      }
                    />
                  </Flex>
                </Tooltip>
              ),
            },
          ]
        : []),
    { type: "divider" },
    { key: "pages", icon: <LinkOutlined />, label: <Link href="/fanpages">Mở Quản lý kênh</Link> },
    {
      key: "products",
      icon: <LinkOutlined />,
      label: <Link href={`/affiliate?tab=products&group=${topic.id}`}>Sản phẩm của nhóm trong Affiliate</Link>,
    },
    { type: "divider" },
    {
      key: "delete",
      danger: true,
      icon: <DeleteOutlined />,
      // Only the group's maker deletes it, and never while it holds videos.
      disabled: topic.video_count > 0 || !isMaker,
      label: !isMaker
        ? "Xoá nhóm (chỉ người tạo nhóm)"
        : topic.video_count > 0
          ? "Xoá nhóm (nhóm còn video)"
          : "Xoá nhóm",
      onClick: remove,
    },
  ];

  return (
    <Flex wrap gap={12} justify="space-between" align="flex-start">
      <Flex vertical gap={2} style={{ minWidth: 0, flex: 1 }}>
        {editing ? (
          <Flex gap={8} wrap>
            <Input
              aria-label="Tên nhóm chủ đề"
              autoFocus
              style={{ maxWidth: 420 }}
              maxLength={100}
              value={value}
              onChange={(event) => setValue(event.target.value)}
              onPressEnter={() => value.trim() && value !== topic.name && rename()}
              onKeyDown={(event) => {
                if (event.key === "Escape") {
                  setValue(topic.name);
                  setEditing(false);
                }
              }}
            />
            <Button
              type="primary"
              icon={<CheckOutlined />}
              loading={busy}
              disabled={!value.trim() || value === topic.name}
              onClick={rename}
            >
              Lưu tên
            </Button>
            <Button
              onClick={() => {
                setValue(topic.name);
                setEditing(false);
              }}
            >
              Huỷ
            </Button>
          </Flex>
        ) : (
          <Typography.Title
            level={4}
            ellipsis
            style={{ margin: 0 }}
            // A double click renames, as the pencil used to.
            onDoubleClick={() => !locked && setEditing(true)}
          >
            {topic.name}
          </Typography.Title>
        )}
        <Typography.Text type="secondary">{summary}</Typography.Text>
      </Flex>
      <Dropdown trigger={["click"]} menu={{ items }}>
        <Button aria-label="Thao tác khác với nhóm" icon={<MoreOutlined />}>
          Quản lý nhóm
        </Button>
      </Dropdown>
    </Flex>
  );
}

/** "Prompt": the group's prompts listed on the left, the chosen one edited on the right. Every editor stays
 * mounted, so text typed in one and not saved survives choosing another. */
function PromptsPanel({
  topic,
  defaults,
  update,
  reload,
}: {
  topic: KnowledgeTopic;
  defaults: Knowledge;
  update: Update;
  reload: Reload;
}) {
  const { token } = theme.useToken();
  const [chosen, setChosen] = useState<PromptField>("script_prompt");
  return (
    <Flex wrap gap={16} align="flex-start">
      {/* About 240 px for the list, the rest for the editor; on a phone the editor goes under the list. */}
      <div style={{ flex: "1 1 220px", maxWidth: 260 }}>
        <Flex vertical gap={2} role="tablist" aria-label="Các prompt của nhóm" aria-orientation="vertical">
          {PROMPTS.map((prompt) => {
            const active = prompt.field === chosen;
            const state = STATE_TAGS[promptState(topic, defaults, prompt)];
            return (
              <button
                key={prompt.field}
                type="button"
                role="tab"
                aria-selected={active}
                onClick={() => setChosen(prompt.field)}
                style={{
                  width: "100%",
                  border: "none",
                  borderLeft: `3px solid ${active ? token.colorPrimary : "transparent"}`,
                  textAlign: "left",
                  font: "inherit",
                  cursor: "pointer",
                  padding: "8px 10px",
                  borderRadius: token.borderRadius,
                  background: active ? token.colorPrimaryBg : "transparent",
                }}
              >
                <Flex justify="space-between" align="center" gap={8}>
                  <Typography.Text strong={active} style={{ color: active ? token.colorPrimaryText : undefined }}>
                    {prompt.label}
                  </Typography.Text>
                  <StatusText tone={toneOf(state.color)}>{state.label}</StatusText>
                </Flex>
              </button>
            );
          })}
        </Flex>
      </div>
      <div style={{ flex: "999 1 420px", minWidth: 0 }}>
        {PROMPTS.map((prompt) => (
          <div key={prompt.field} hidden={prompt.field !== chosen}>
            <PromptCard
              topicId={topic.id}
              title={prompt.title}
              field={prompt.field}
              emptyIsDefault={prompt.emptyIsDefault}
              // Empty in the database means the default is used, so the default is what is shown.
              initial={
                prompt.emptyIsDefault ? topic[prompt.field] || String(defaults[prompt.defaultKey]) : topic[prompt.field]
              }
              fallback={String(defaults[prompt.defaultKey])}
              update={update}
              reload={reload}
              help={PROMPT_HELP[prompt.field]}
            />
          </div>
        ))}
      </div>
    </Flex>
  );
}

type Update = (body: Partial<KnowledgeTopic>) => Promise<KnowledgeTopic>;
type Reload = () => Promise<void>;

/** A card's text as last saved: a new saved value (put back from "Lịch sử") replaces what the box shows. Also says
 * whether the box holds typing not saved yet, and takes what a save returned (`setSaved`). */
function useSaved<T>(saved: T, key: (value: T) => string = String) {
  const [value, setValue] = useState(saved);
  const [base, setBase] = useState(saved);
  const [seen, setSeen] = useState(key(saved));
  if (seen !== key(saved)) {
    setSeen(key(saved));
    setValue(saved);
    setBase(saved);
  }
  const setSaved = useCallback((next: T) => {
    setValue(next);
    setBase(next);
  }, []);
  return [value, setValue, key(value) !== key(base), setSaved] as const;
}

function PromptCard({
  topicId,
  title,
  field,
  emptyIsDefault,
  initial,
  fallback,
  update,
  reload,
  help,
}: {
  topicId: number;
  title: string;
  field: PromptField;
  emptyIsDefault: boolean;
  initial: string;
  fallback: string;
  update: Update;
  reload: Reload;
  help: React.ReactNode;
}) {
  const { message } = App.useApp();
  const [value, setValue, dirty, setSaved] = useSaved(initial);
  useLeaveGuard(() => dirty);
  const [busy, setBusy] = useState(false);

  async function save(text: string) {
    setBusy(true);
    try {
      setSaved((await update({ [field]: text }))[field]);
      message.success(`Đã lưu ${title.toLowerCase()}`);
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card
      title={title}
      size="small"
      extra={
        <EditHistory
          entityType="knowledge_topic"
          entityId={topicId}
          field={field}
          title={title}
          kind="text"
          // Empty in the database means the default is used (for the prompts that have one).
          show={(saved) => (emptyIsDefault && !saved ? fallback : String(saved))}
          current={initial}
          defaultText={fallback}
          restorable
          onRestored={reload}
        />
      }
    >
      <Typography.Paragraph type="secondary">
        {help} Phần định dạng JSON đầu ra cố định trong app và không cần viết ở đây.
      </Typography.Paragraph>
      <Input.TextArea
        aria-label={title}
        value={value}
        autoSize={{ minRows: 8, maxRows: 30 }}
        onChange={(event) => setValue(event.target.value)}
      />
      <Flex wrap gap={8} style={{ marginTop: 12 }}>
        <Button type="primary" loading={busy} disabled={!value.trim()} onClick={() => save(value)}>
          Lưu
        </Button>
      </Flex>
    </Card>
  );
}

/** "Gợi ý tìm ảnh": what this group's photos show, read by the AI when it writes the scenes' search keywords. */
function PhotoHintCard({
  topicId,
  initial,
  update,
  reload,
}: {
  topicId: number;
  initial: string;
  update: Update;
  reload: Reload;
}) {
  const { message } = App.useApp();
  const [text, setText, dirty, setSaved] = useSaved(initial);
  useLeaveGuard(() => dirty);
  const [busy, setBusy] = useState(false);

  async function save() {
    setBusy(true);
    try {
      setSaved((await update({ photo_hint: text })).photo_hint);
      message.success("Đã lưu gợi ý tìm ảnh");
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card
      title="Gợi ý tìm ảnh"
      size="small"
      extra={
        <EditHistory
          entityType="knowledge_topic"
          entityId={topicId}
          field="photo_hint"
          title="Gợi ý tìm ảnh"
          kind="text"
          current={initial}
          restorable
          onRestored={reload}
        />
      }
    >
      <Typography.Paragraph type="secondary">
        Ảnh của nhóm này nên cho thấy gì. AI đọc gợi ý này khi viết từ khóa tìm ảnh và prompt ảnh AI cho từng cảnh, áp
        dụng cho kịch bản viết sau khi lưu. Để trống nếu không cần.
      </Typography.Paragraph>
      <Input.TextArea
        aria-label="Gợi ý tìm ảnh"
        value={text}
        placeholder="VD: cây rau đang mọc trong chậu, luống đất hoặc tay người đang chăm cây; không phải món rau đã nấu…"
        autoSize={{ minRows: 3, maxRows: 8 }}
        maxLength={1000}
        onChange={(event) => setText(event.target.value)}
      />
      <Button type="primary" loading={busy} style={{ marginTop: 12 }} onClick={save}>
        Lưu gợi ý
      </Button>
    </Card>
  );
}

/** "Giọng mặc định của nhóm": the voice new videos of this group start with, over their maker's defaults. */
function GroupVoiceCard({
  topicId,
  initial,
  initialBackup,
  update,
  reload,
}: {
  topicId: number;
  initial: string;
  initialBackup: string;
  update: Update;
  reload: Reload;
}) {
  const { message } = App.useApp();
  const [voice, setVoice] = useSaved(initial);
  const [backup, setBackup] = useSaved(initialBackup);
  const [busy, setBusy] = useState(false);

  async function save() {
    setBusy(true);
    try {
      const saved = await update({ voice_id: voice, voice_backup_id: backup });
      setVoice(saved.voice_id);
      setBackup(saved.voice_backup_id);
      message.success("Đã lưu giọng của nhóm");
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card
      title="Giọng mặc định của nhóm"
      size="small"
      extra={
        <EditHistory
          entityType="knowledge_topic"
          entityId={topicId}
          field="voice_id"
          title="Giọng mặc định của nhóm"
          kind="value"
          show={(saved) => String(saved) || "Theo Thiết lập mặc định của người tạo"}
          current={initial || "Theo Thiết lập mặc định của người tạo"}
          restorable
          onRestored={reload}
        />
      }
    >
      <Typography.Paragraph type="secondary">
        Video tạo mới trong nhóm này đọc bằng giọng này, thay cho giọng trong Thiết lập mặc định của người tạo. Video đã
        có không đổi; đổi giọng riêng trên từng video vẫn được. Để trống thì theo Thiết lập mặc định như cũ.
      </Typography.Paragraph>
      <VoicePicker
        values={{ voice_id: voice }}
        unset="Theo Thiết lập mặc định của người tạo"
        onChange={(changes) => setVoice(changes.voice_id ?? "")}
      />
      <Typography.Paragraph type="secondary" style={{ marginTop: 16 }}>
        Giọng phụ: khi giọng chính không đọc được (mọi key của dịch vụ đó sai hoặc hết hạn mức), cảnh được đọc bằng
        giọng này, có thể của dịch vụ khác. Để trống thì video báo lỗi như cũ.
      </Typography.Paragraph>
      <VoicePicker
        values={{ voice_id: backup }}
        unset="Không dùng giọng phụ"
        onChange={(changes) => setBackup(changes.voice_id ?? "")}
      />
      <Button
        type="primary"
        loading={busy}
        disabled={voice === initial && backup === initialBackup}
        style={{ marginTop: 12 }}
        onClick={save}
      >
        Lưu giọng
      </Button>
    </Card>
  );
}

/** "Mẫu dựng của nhóm": the saved templates the group holds, and the one its new videos take over their maker's. */
function GroupTemplatesCard({ topic, update }: { topic: KnowledgeTopic; update: Update }) {
  const { message } = App.useApp();
  const [library, setLibrary] = useState<EditTemplates | null>(null);
  const [held, setHeld] = useState<number[]>(topic.templates);
  const [chosen, setChosen] = useState<"app" | number | null>(topic.edit_template_default);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api<EditTemplates>("/edit-templates").then(setLibrary, (err) => message.error(errorMessage(err)));
  }, [message]);

  const saved = topic.templates.join(",") === held.join(",") && topic.edit_template_default === chosen;
  const names = new Map((library?.templates ?? []).map((item) => [item.id, item.name]));

  async function save() {
    setBusy(true);
    try {
      const after = await update({ templates: held, edit_template_default: chosen });
      setHeld(after.templates);
      setChosen(after.edit_template_default);
      message.success("Đã lưu mẫu dựng của nhóm");
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title="Mẫu dựng của nhóm" size="small" style={{ maxWidth: 640 }}>
      <Typography.Paragraph type="secondary">
        Gắn các mẫu dựng (lưu từ video trong “Tự dựng”) cho nhóm và chọn một mẫu cho video mới của nhóm. Thứ tự ưu tiên
        khi video mới được viết xong cảnh: mẫu chọn riêng trên video › mẫu của nhóm › mẫu của người tạo (Cài đặt › Mẫu
        dựng) › không áp. Video đã có giữ nguyên.
      </Typography.Paragraph>
      {library === null ? (
        <Spin />
      ) : (
        <Flex vertical gap={12}>
          <Select
            mode="multiple"
            aria-label="Mẫu của nhóm"
            placeholder="Chưa gắn mẫu nào"
            value={held}
            options={library.templates
              .filter((item) => !item.builtin)
              .map((item) => ({ value: item.id as number, label: item.name }))}
            onChange={(ids: number[]) => {
              setHeld(ids);
              if (typeof chosen === "number" && !ids.includes(chosen)) setChosen(null);
            }}
          />
          <Select
            aria-label="Mẫu cho video mới của nhóm"
            value={chosen === null ? "none" : String(chosen)}
            options={[
              { value: "none", label: "Không áp mẫu của nhóm" },
              { value: "app", label: String(names.get("app") ?? "Gợi ý của app") },
              ...held.map((id) => ({ value: String(id), label: names.get(id) ?? `Mẫu ${id}` })),
            ]}
            onChange={(value: string) => setChosen(value === "none" ? null : value === "app" ? "app" : Number(value))}
          />
          <div>
            <Button type="primary" loading={busy} disabled={saved} onClick={save}>
              Lưu mẫu dựng
            </Button>
          </div>
        </Flex>
      )}
    </Card>
  );
}

function BannedWordsCard({
  topicId,
  initial,
  update,
  reload,
}: {
  topicId: number;
  initial: string[];
  update: Update;
  reload: Reload;
}) {
  const { message } = App.useApp();
  const [text, setText, dirty, setSaved] = useSaved(initial.join("\n"));
  useLeaveGuard(() => dirty);
  const [busy, setBusy] = useState(false);

  async function save() {
    setBusy(true);
    try {
      const banned_words = text
        .split("\n")
        .map((word) => word.trim())
        .filter(Boolean);
      setSaved((await update({ banned_words })).banned_words.join("\n"));
      message.success("Đã lưu danh sách từ cấm");
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card
      title="Từ cấm"
      size="small"
      extra={
        <EditHistory
          entityType="knowledge_topic"
          entityId={topicId}
          field="banned_words"
          title="Từ cấm"
          kind="words"
          show={(saved) => ((saved as string[] | null) ?? []).join("\n")}
          current={initial.join("\n")}
          restorable
          onRestored={reload}
        />
      }
    >
      <Typography.Paragraph type="secondary">
        Mỗi dòng một từ. Tiêu đề, chữ cảnh, caption và bình luận ghim có từ cấm sẽ hiện cảnh báo vàng (không chặn
        render). AI viết kịch bản cũng được dặn tránh các từ này.
      </Typography.Paragraph>
      <Input.TextArea
        aria-label="Từ cấm"
        value={text}
        autoSize={{ minRows: 5, maxRows: 20 }}
        onChange={(event) => setText(event.target.value)}
      />
      <Button type="primary" loading={busy} style={{ marginTop: 12 }} onClick={save}>
        Lưu từ cấm
      </Button>
    </Card>
  );
}
