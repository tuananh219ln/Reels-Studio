"use client";

import { useMe } from "@/components/MeContext";
import {
  CheckOutlined,
  DeleteOutlined,
  EditOutlined,
  HistoryOutlined,
  MoreOutlined,
  PlusOutlined,
} from "@ant-design/icons";
import {
  App,
  Button,
  Card,
  Col,
  Dropdown,
  Empty,
  Flex,
  Input,
  Row,
  Select,
  Spin,
  Tabs,
  Tag,
  theme,
  Tooltip,
  Typography,
} from "antd";
import { useEffect, useState } from "react";
import { api, errorMessage, type EditTemplates, type Knowledge, type KnowledgeTopic } from "@/lib/api";
import EditHistory, { lastEditText } from "@/components/EditHistory";
import PageHeader from "@/components/PageHeader";
import TopicVideos from "@/components/knowledge/TopicVideos";
import StockOrderCard from "@/components/knowledge/StockOrderCard";
import { usePlanTabs } from "@/components/plan/PlanTab";
import { VoicePicker } from "@/components/video/VideoSettings";

export default function KnowledgePage() {
  const { message } = App.useApp();
  const { token } = theme.useToken();
  const [data, setData] = useState<Knowledge | null>(null);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [chosen, setChosen] = useState<number | null>(null);
  // Topics opened so far stay mounted (hidden when another is chosen): each box keeps its own unsaved text.
  const [opened, setOpened] = useState<number[]>([]);

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
  const mounted = data.topics.filter((topic) => topic.id === current?.id || opened.includes(topic.id));

  function choose(id: number) {
    setChosen(id);
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

  return (
    <>
      <PageHeader
        title="Kho kiến thức"
        description="Mỗi nhóm chủ đề có video, prompt, từ cấm và kế hoạch 30 ngày riêng. Nhóm được chọn khi tạo video; bản nhân bản dùng nhóm của video gốc."
      />
      <Row gutter={[16, 16]} align="top">
        <Col xs={24} lg={6} xxl={5} style={{ position: "sticky", top: 16, zIndex: 1 }}>
          <Card
            size="small"
            title="Nhóm chủ đề"
            extra={
              <Flex gap={8} align="center">
                <Typography.Text type="secondary">{data.topics.length}</Typography.Text>
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
              </Flex>
            }
            styles={{ body: { padding: 8 } }}
          >
            <Flex vertical gap={2} data-testid="topic-list">
              {data.topics.map((topic) => {
                const active = topic.id === current?.id;
                return (
                  <button
                    key={topic.id}
                    type="button"
                    aria-current={active ? "true" : undefined}
                    onClick={() => choose(topic.id)}
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
                    <Flex vertical style={{ minWidth: 0 }}>
                      <Typography.Text strong ellipsis style={{ color: active ? token.colorPrimaryText : undefined }}>
                        {topic.name}
                      </Typography.Text>
                      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                        {topic.mine && (
                          <Typography.Text style={{ fontSize: 12, color: token.colorPrimaryText }}>
                            Của tôi ·{" "}
                          </Typography.Text>
                        )}
                        {topic.video_count} video
                        {!topic.script_prompt && (
                          <Typography.Text type="warning" style={{ fontSize: 12 }}>
                            {" "}
                            · Chưa có prompt
                          </Typography.Text>
                        )}
                      </Typography.Text>
                    </Flex>
                  </button>
                );
              })}
            </Flex>
            <Flex
              gap={6}
              style={{ padding: "8px 4px 4px", borderTop: `1px solid ${token.colorBorderSecondary}`, marginTop: 6 }}
            >
              <Input
                size="small"
                aria-label="Tên nhóm chủ đề mới"
                placeholder="Tên nhóm mới"
                maxLength={100}
                value={name}
                onChange={(event) => setName(event.target.value)}
                onPressEnter={() => name.trim() && add()}
              />
              <Tooltip title="Thêm nhóm">
                <Button
                  size="small"
                  aria-label="Thêm nhóm"
                  icon={<PlusOutlined />}
                  loading={busy}
                  disabled={!name.trim()}
                  onClick={add}
                />
              </Tooltip>
            </Flex>
          </Card>
        </Col>
        <Col xs={24} lg={18} xxl={19}>
          {current === null ? (
            <Card>
              <Empty description="Chưa có nhóm chủ đề nào. Thêm một nhóm ở bên trái." />
            </Card>
          ) : (
            mounted.map((topic) => (
              <div key={topic.id} hidden={topic.id !== current.id}>
                <TopicBody topic={topic} defaults={data} onSaved={setData} />
              </div>
            ))
          )}
        </Col>
      </Row>
    </>
  );
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
  stock_order: "Thứ tự nguồn ảnh",
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
}: {
  topic: KnowledgeTopic;
  defaults: Knowledge;
  onSaved: (data: Knowledge) => void;
}) {
  const { token } = theme.useToken();
  const path = `/knowledge/topics/${topic.id}`;
  const { tabs: planTabs, dialogs: planDialogs } = usePlanTabs(topic.id);
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
    <Flex
      vertical
      gap={4}
      data-topic={topic.name}
      style={{
        background: token.colorBgContainer,
        border: `1px solid ${token.colorBorderSecondary}`,
        borderRadius: token.borderRadiusLG,
        padding: "16px 20px 20px",
      }}
    >
      <TopicHeader
        topic={topic}
        path={path}
        update={update}
        onSaved={onSaved}
        summary={
          <>
            {topic.video_count} video · {edited} prompt đã sửa
            {!topic.script_prompt && (
              <Typography.Text type="warning"> · Chưa có prompt viết kịch bản nên chưa tạo video được</Typography.Text>
            )}
            {topic.last_edit && (
              <>
                {" · "}
                <EditHistory
                  entityType="knowledge_topic"
                  entityId={topic.id}
                  title={topic.name}
                  kind="fields"
                  fieldLabels={TOPIC_FIELDS}
                  trigger={(open) => (
                    <Typography.Link onClick={open} style={{ fontSize: "inherit" }}>
                      <HistoryOutlined /> {lastEditText(topic.last_edit!, TOPIC_FIELDS)}
                    </Typography.Link>
                  )}
                />
              </>
            )}
          </>
        }
      />
      <Tabs
        defaultActiveKey="videos"
        items={[
          {
            key: "videos",
            label: `Video (${topic.video_count})`,
            children: <TopicVideos topicId={topic.id} canCreate={Boolean(topic.script_prompt)} />,
          },
          {
            key: "prompts",
            label: "Prompt",
            children: <PromptsPanel topic={topic} defaults={defaults} update={update} reload={reload} />,
          },
          {
            key: "words",
            label: "Từ cấm, ảnh & giọng",
            children: (
              <Row gutter={[16, 16]}>
                <Col xs={24} xl={12}>
                  <BannedWordsCard topicId={topic.id} initial={topic.banned_words} update={update} reload={reload} />
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
                    <GroupVoiceCard topicId={topic.id} initial={topic.voice_id} update={update} reload={reload} />
                  </Flex>
                </Col>
              </Row>
            ),
          },
          {
            key: "templates",
            label: "Mẫu dựng",
            children: <GroupTemplatesCard topic={topic} update={update} />,
          },
          ...planTabs,
        ]}
      />
      {planDialogs}
    </Flex>
  );
}

/** The group's name as the heading, renamed in place ("Đổi tên"), and "Xoá nhóm" under "⋯" (only while it has no
 * videos, as a video keeps its group). */
function TopicHeader({
  topic,
  path,
  update,
  onSaved,
  summary,
}: {
  topic: KnowledgeTopic;
  path: string;
  update: Update;
  onSaved: (data: Knowledge) => void;
  summary: React.ReactNode;
}) {
  const { message, modal } = App.useApp();
  const { me } = useMe();
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(topic.name);
  const [busy, setBusy] = useState(false);

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
          <Flex gap={4} align="center" style={{ minWidth: 0 }}>
            <Typography.Title level={4} ellipsis style={{ margin: 0 }}>
              {topic.name}
            </Typography.Title>
            <Tooltip title="Đổi tên">
              <Button
                type="text"
                size="small"
                aria-label="Đổi tên"
                icon={<EditOutlined />}
                onClick={() => setEditing(true)}
              />
            </Tooltip>
          </Flex>
        )}
        <Typography.Text type="secondary">{summary}</Typography.Text>
      </Flex>
      <Dropdown
        trigger={["click"]}
        menu={{
          items: [
            {
              key: "delete",
              danger: true,
              icon: <DeleteOutlined />,
              // Only the group's maker deletes it, and never while it holds videos.
              disabled: topic.video_count > 0 || topic.created_by_id !== me.id,
              label:
                topic.created_by_id !== me.id
                  ? "Xoá nhóm (chỉ người tạo nhóm)"
                  : topic.video_count > 0
                    ? "Xoá nhóm (nhóm còn video)"
                    : "Xoá nhóm",
              onClick: remove,
            },
          ],
        }}
      >
        <Button aria-label="Thao tác khác với nhóm" icon={<MoreOutlined />} />
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
                  <Tag color={state.color} style={{ marginInlineEnd: 0 }}>
                    {state.label}
                  </Tag>
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

/** A card's text as last saved: a new saved value (put back from "Lịch sử") replaces what the box shows. */
function useSaved<T>(saved: T, key: (value: T) => string = String) {
  const [value, setValue] = useState(saved);
  const [seen, setSeen] = useState(key(saved));
  if (seen !== key(saved)) {
    setSeen(key(saved));
    setValue(saved);
  }
  return [value, setValue] as const;
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
  const [value, setValue] = useSaved(initial);
  const [busy, setBusy] = useState(false);

  async function save(text: string) {
    setBusy(true);
    try {
      setValue((await update({ [field]: text }))[field]);
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
  const [text, setText] = useSaved(initial);
  const [busy, setBusy] = useState(false);

  async function save() {
    setBusy(true);
    try {
      setText((await update({ photo_hint: text })).photo_hint);
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
        placeholder="VD: cây rau đang mọc trong chậu, luống đất hoặc tay người đang chăm cây; không phải món rau đã nấu"
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
  update,
  reload,
}: {
  topicId: number;
  initial: string;
  update: Update;
  reload: Reload;
}) {
  const { message } = App.useApp();
  const [voice, setVoice] = useSaved(initial);
  const [busy, setBusy] = useState(false);

  async function save() {
    setBusy(true);
    try {
      setVoice((await update({ voice_id: voice })).voice_id);
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
      <Button type="primary" loading={busy} disabled={voice === initial} style={{ marginTop: 12 }} onClick={save}>
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
        khi video mới được viết xong cảnh: mẫu chọn riêng trên video › mẫu của nhóm › mẫu của người tạo (Cấu hình › Mẫu
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
  const [text, setText] = useSaved(initial.join("\n"));
  const [busy, setBusy] = useState(false);

  async function save() {
    setBusy(true);
    try {
      const banned_words = text
        .split("\n")
        .map((word) => word.trim())
        .filter(Boolean);
      setText((await update({ banned_words })).banned_words.join("\n"));
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
