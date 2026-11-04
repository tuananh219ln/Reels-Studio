"use client";

import { DeleteOutlined, PlusOutlined } from "@ant-design/icons";
import {
  App,
  Button,
  Card,
  Col,
  Empty,
  Flex,
  Input,
  Popconfirm,
  Row,
  Spin,
  Tabs,
  Tag,
  theme,
  Tooltip,
  Typography,
} from "antd";
import { useEffect, useState } from "react";
import { api, errorMessage, type Knowledge, type KnowledgeTopic } from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import PlanTab from "@/components/plan/PlanTab";

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
        description="Mỗi nhóm chủ đề có prompt viết kịch bản, prompt nhân bản, từ cấm và kế hoạch 30 ngày riêng. Video dùng nhóm được chọn khi tạo video; bản nhân bản dùng nhóm của video gốc."
      />
      <Row gutter={[16, 16]} align="top">
        <Col xs={24} lg={7} xxl={6}>
          <Card size="small" title="Nhóm chủ đề" styles={{ body: { padding: 8 } }}>
            <Flex gap={8} style={{ padding: 4, marginBottom: 8 }}>
              <Input
                aria-label="Tên nhóm chủ đề mới"
                placeholder="Tên nhóm chủ đề mới"
                maxLength={100}
                value={name}
                onChange={(event) => setName(event.target.value)}
                onPressEnter={() => name.trim() && add()}
              />
              <Button icon={<PlusOutlined />} loading={busy} disabled={!name.trim()} onClick={add}>
                Thêm nhóm
              </Button>
            </Flex>
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
                      textAlign: "left",
                      font: "inherit",
                      cursor: "pointer",
                      padding: "10px 12px",
                      borderRadius: token.borderRadius,
                      background: active ? token.colorPrimaryBg : "transparent",
                    }}
                  >
                    <Flex justify="space-between" align="center" gap={8}>
                      <Flex vertical style={{ minWidth: 0 }}>
                        <Typography.Text strong ellipsis style={{ color: active ? token.colorPrimaryText : undefined }}>
                          {topic.name}
                        </Typography.Text>
                        <Typography.Text type="secondary" style={{ fontSize: 13 }}>
                          {topic.video_count} video
                        </Typography.Text>
                      </Flex>
                      {!topic.script_prompt && <Tag color="gold">Chưa có prompt</Tag>}
                    </Flex>
                  </button>
                );
              })}
            </Flex>
          </Card>
        </Col>
        <Col xs={24} lg={17} xxl={18}>
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

function TopicBody({
  topic,
  defaults,
  onSaved,
}: {
  topic: KnowledgeTopic;
  defaults: Knowledge;
  onSaved: (data: Knowledge) => void;
}) {
  const { message } = App.useApp();
  const { token } = theme.useToken();
  const path = `/knowledge/topics/${topic.id}`;
  const update = async (body: Partial<KnowledgeTopic>) => {
    const saved = await api<Knowledge>(path, "PATCH", body);
    onSaved(saved);
    return saved.topics.find((item) => item.id === topic.id) ?? topic;
  };

  async function remove() {
    try {
      onSaved(await api<Knowledge>(path, "DELETE"));
    } catch (err) {
      message.error(errorMessage(err));
    }
  }

  // Not a Card itself: the prompt cards inside are found by their own title.
  return (
    <Flex
      vertical
      gap={8}
      data-topic={topic.name}
      style={{
        background: token.colorBgContainer,
        border: `1px solid ${token.colorBorderSecondary}`,
        borderRadius: token.borderRadiusLG,
        padding: "16px 20px 20px",
      }}
    >
      <Flex wrap gap={12} justify="space-between" align="center">
        <Flex vertical gap={2}>
          <Typography.Title level={4} style={{ margin: 0 }}>
            {topic.name}
          </Typography.Title>
          <Typography.Text type="secondary">
            {topic.video_count} video dùng nhóm này
            {!topic.script_prompt && ", chưa có prompt viết kịch bản nên chưa tạo video được"}
          </Typography.Text>
        </Flex>
        <Flex wrap gap={8} align="center">
          <NameCard name={topic.name} update={update} />
          <Tooltip title={topic.video_count > 0 ? "Nhóm còn video nên chưa xoá được" : undefined}>
            <span>
              <Popconfirm
                title="Xoá nhóm chủ đề này?"
                okText="Xoá"
                cancelText="Huỷ"
                okButtonProps={{ danger: true }}
                disabled={topic.video_count > 0}
                onConfirm={remove}
              >
                <Button danger icon={<DeleteOutlined />} disabled={topic.video_count > 0}>
                  Xoá nhóm
                </Button>
              </Popconfirm>
            </span>
          </Tooltip>
        </Flex>
      </Flex>
      <Tabs
        items={[
          {
            key: "prompts",
            label: "Prompt và từ cấm",
            children: (
              <Row gutter={[16, 16]}>
                <Col xs={24} xl={16}>
                  <Flex vertical gap={16}>
                    <PromptCard
                      title="Prompt viết kịch bản"
                      field="script_prompt"
                      initial={topic.script_prompt}
                      fallback={defaults.default_script_prompt}
                      update={update}
                      help={
                        <>
                          Chỗ điền <Typography.Text code>[Chủ đề]</Typography.Text> được thay bằng chủ đề của video; nếu
                          xóa chỗ điền này, chủ đề được nối vào cuối prompt. Video tạo từ kế hoạch 30 ngày còn điền{" "}
                          <Typography.Text code>[Nhóm nỗi đau]</Typography.Text>,{" "}
                          <Typography.Text code>[Nỗi đau]</Typography.Text> và{" "}
                          <Typography.Text code>[Góc hook]</Typography.Text> của ý tưởng (thiếu chỗ điền thì nối vào
                          cuối).
                        </>
                      }
                    />
                    <PromptCard
                      title="Prompt nhân bản"
                      field="clone_prompt"
                      initial={topic.clone_prompt}
                      fallback={defaults.default_clone_prompt}
                      update={update}
                      help={
                        <>
                          Dùng khi bấm “Nhân bản”. Các chỗ điền <Typography.Text code>[tiêu đề]</Typography.Text>,{" "}
                          <Typography.Text code>[chủ đề]</Typography.Text>,{" "}
                          <Typography.Text code>[kịch bản đã sửa của video gốc]</Typography.Text> và{" "}
                          <Typography.Text code>[yêu cầu đổi]</Typography.Text> được thay bằng dữ liệu của video gốc;
                          chỗ điền nào bị xóa thì thông tin đó được nối vào cuối prompt.
                        </>
                      }
                    />
                  </Flex>
                </Col>
                <Col xs={24} xl={8}>
                  <BannedWordsCard initial={topic.banned_words} update={update} />
                </Col>
              </Row>
            ),
          },
          { key: "plan", label: "Kế hoạch 30 ngày", children: <PlanTab topicId={topic.id} /> },
        ]}
      />
    </Flex>
  );
}

type Update = (body: Partial<KnowledgeTopic>) => Promise<KnowledgeTopic>;

function NameCard({ name, update }: { name: string; update: Update }) {
  const { message } = App.useApp();
  const [value, setValue] = useState(name);
  const [busy, setBusy] = useState(false);

  async function save() {
    setBusy(true);
    try {
      setValue((await update({ name: value })).name);
      message.success("Đã lưu tên nhóm chủ đề");
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Flex gap={8}>
      <Input
        aria-label="Tên nhóm chủ đề"
        style={{ width: 220 }}
        maxLength={100}
        value={value}
        onChange={(event) => setValue(event.target.value)}
      />
      <Button loading={busy} disabled={!value.trim() || value === name} onClick={save}>
        Đổi tên
      </Button>
    </Flex>
  );
}

function PromptCard({
  title,
  field,
  initial,
  fallback,
  update,
  help,
}: {
  title: string;
  field: "script_prompt" | "clone_prompt";
  initial: string;
  fallback: string;
  update: Update;
  help: React.ReactNode;
}) {
  const { message, modal } = App.useApp();
  const [value, setValue] = useState(initial);
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
    <Card title={title} size="small">
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
        <Button
          disabled={busy}
          onClick={() =>
            modal.confirm({
              title: `Khôi phục ${title.toLowerCase()} mặc định?`,
              content: "Prompt đang dùng sẽ được thay bằng bản mặc định.",
              okText: "Khôi phục",
              cancelText: "Huỷ",
              onOk: () => save(fallback),
            })
          }
        >
          Khôi phục mặc định
        </Button>
      </Flex>
    </Card>
  );
}

function BannedWordsCard({ initial, update }: { initial: string[]; update: Update }) {
  const { message } = App.useApp();
  const [text, setText] = useState(initial.join("\n"));
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
    <Card title="Từ cấm" size="small">
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
