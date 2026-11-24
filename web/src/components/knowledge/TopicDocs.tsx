"use client";

import EmptyState from "@/components/EmptyState";
import { api, errorMessage, formatDateTime, type TopicDoc } from "@/lib/api";
import {
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
  PushpinFilled,
  PushpinOutlined,
  SearchOutlined,
  UploadOutlined,
} from "@ant-design/icons";
import {
  App,
  Button,
  Flex,
  Form,
  Input,
  Modal,
  Popconfirm,
  Segmented,
  Select,
  Spin,
  Tag,
  Tooltip,
  Typography,
  theme,
} from "antd";
import { useCallback, useEffect, useRef, useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

type Listing = { sections: { key: string; label: string }[]; docs: TopicDoc[] };
type Draft = { id: number | null; section: string; name: string; body: string; pinned: boolean };
const NEW_DOC: Draft = { id: null, section: "template", name: "", body: "", pinned: false };

/** "Tài liệu" in Kho kiến thức: the Markdown documents of one topic group (job, templates, plans, prompts, reports),
 * with search, pins and who changed each last. The copy here is the master: assistants read it through MCP
 * (`list_docs`, `get_doc`). Reading is open to everyone; writing follows the group's "Cho cả đội sửa". */
export default function TopicDocs({
  topicId,
  canEdit,
  visible,
}: {
  topicId: number;
  canEdit: boolean;
  visible: boolean;
}) {
  const { message } = App.useApp();
  const { token } = theme.useToken();
  const [listing, setListing] = useState<Listing | null>(null);
  const [section, setSection] = useState("all");
  const [query, setQuery] = useState("");
  const [openId, setOpenId] = useState<number | null>(null);
  const [open, setOpen] = useState<TopicDoc | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [saving, setSaving] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    const params = new URLSearchParams({ topic_id: String(topicId) });
    if (query.trim()) params.set("q", query.trim());
    try {
      setListing(await api<Listing>(`/topic-docs?${params}`));
    } catch (err) {
      message.error(errorMessage(err));
    }
  }, [topicId, query, message]);

  useEffect(() => {
    if (!visible) return;
    const timer = window.setTimeout(load, query ? 250 : 0);
    return () => window.clearTimeout(timer);
  }, [visible, load, query]);

  useEffect(() => {
    if (openId === null) return;
    let live = true;
    api<TopicDoc>(`/topic-docs/${openId}`).then(
      (doc) => live && setOpen(doc),
      (err) => message.error(errorMessage(err)),
    );
    return () => {
      live = false;
    };
  }, [openId, message]);

  const docs = (listing?.docs ?? []).filter((doc) => section === "all" || doc.section === section);

  async function save() {
    if (!draft) return;
    setSaving(true);
    try {
      const body = { section: draft.section, name: draft.name, body: draft.body, pinned: draft.pinned };
      const saved =
        draft.id === null
          ? await api<TopicDoc>(`/topic-docs?topic_id=${topicId}`, "POST", body)
          : await api<TopicDoc>(`/topic-docs/${draft.id}`, "PATCH", body);
      setDraft(null);
      setOpenId(saved.id);
      setOpen(saved);
      await load();
      message.success("Đã lưu tài liệu");
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  async function togglePin(doc: TopicDoc) {
    try {
      await api(`/topic-docs/${doc.id}`, "PATCH", { pinned: !doc.pinned });
      await load();
    } catch (err) {
      message.error(errorMessage(err));
    }
  }

  async function remove(doc: TopicDoc) {
    try {
      await api(`/topic-docs/${doc.id}`, "DELETE");
      if (openId === doc.id) {
        setOpenId(null);
        setOpen(null);
      }
      await load();
      message.success("Đã xoá tài liệu");
    } catch (err) {
      message.error(errorMessage(err));
    }
  }

  async function readFile(file: File | undefined) {
    if (!file) return;
    setDraft({ ...NEW_DOC, name: file.name, body: await file.text() });
  }

  if (listing === null) {
    return (
      <Flex justify="center" style={{ padding: 32 }}>
        <Spin />
      </Flex>
    );
  }

  return (
    <Flex vertical gap={12} data-testid="topic-docs">
      <Typography.Text type="secondary">
        Bản chính của tài liệu vận hành nhóm nằm ở đây; file ở máy chỉ là bản nháp. Job dựng đọc luật qua MCP (“Liệt kê
        tài liệu của nhóm”, “Đọc tài liệu của nhóm”) thay vì chép vào thân job.
      </Typography.Text>
      <Flex wrap gap={8} justify="space-between">
        <Flex wrap gap={8}>
          <Input
            aria-label="Tìm tài liệu"
            placeholder="Tìm theo tên hoặc nội dung…"
            prefix={<SearchOutlined />}
            allowClear
            style={{ width: 260 }}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          <Segmented
            aria-label="Mục tài liệu"
            value={section}
            onChange={(value) => setSection(String(value))}
            options={[
              { value: "all", label: "Tất cả" },
              ...listing.sections.map((s) => ({ value: s.key, label: s.label })),
            ]}
          />
        </Flex>
        {canEdit && (
          <Flex gap={8}>
            <input
              ref={fileInput}
              type="file"
              accept=".md,text/markdown,text/plain"
              hidden
              data-testid="doc-file"
              onChange={(event) => {
                void readFile(event.target.files?.[0]);
                event.target.value = "";
              }}
            />
            <Button icon={<UploadOutlined />} onClick={() => fileInput.current?.click()}>
              Tải file .md
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setDraft(NEW_DOC)}>
              Thêm tài liệu
            </Button>
          </Flex>
        )}
      </Flex>
      <Flex gap={16} wrap align="flex-start">
        <Flex vertical gap={6} style={{ width: 340, maxWidth: "100%" }} data-testid="doc-list">
          {docs.length === 0 && (
            <EmptyState
              description={listing.docs.length ? "Không có tài liệu nào khớp" : "Nhóm này chưa có tài liệu nào"}
            />
          )}
          {docs.map((doc) => (
            <Flex
              key={doc.id}
              gap={8}
              align="flex-start"
              data-testid="doc-row"
              onClick={() => setOpenId(doc.id)}
              style={{
                cursor: "pointer",
                padding: "8px 10px",
                borderRadius: token.borderRadius,
                border: `1px solid ${openId === doc.id ? token.colorPrimary : token.colorBorderSecondary}`,
              }}
            >
              <Tooltip title={doc.pinned ? "Bỏ ghim" : "Ghim lên đầu"}>
                <Button
                  size="small"
                  type="text"
                  aria-label={doc.pinned ? "Bỏ ghim" : "Ghim"}
                  disabled={!canEdit}
                  icon={doc.pinned ? <PushpinFilled style={{ color: token.colorWarning }} /> : <PushpinOutlined />}
                  onClick={(event) => {
                    event.stopPropagation();
                    void togglePin(doc);
                  }}
                />
              </Tooltip>
              <Flex vertical style={{ minWidth: 0, flex: 1 }}>
                <Typography.Text strong ellipsis>
                  {doc.title}
                </Typography.Text>
                <Typography.Text type="secondary" ellipsis style={{ fontSize: 12 }}>
                  {doc.name}
                </Typography.Text>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  {doc.updated_by ?? "—"}, {formatDateTime(doc.updated_at)}
                </Typography.Text>
              </Flex>
              <Tag style={{ marginInlineEnd: 0 }}>{doc.section_label}</Tag>
            </Flex>
          ))}
        </Flex>
        <div style={{ flex: 1, minWidth: 280 }} data-testid="doc-reader">
          {open ? (
            <Flex vertical gap={8}>
              <Flex justify="space-between" align="center" gap={8} wrap>
                <Typography.Text type="secondary">
                  {open.section_label} · {open.name} · sửa lần cuối {open.updated_by ?? "—"},{" "}
                  {formatDateTime(open.updated_at)}
                </Typography.Text>
                {canEdit && (
                  <Flex gap={8}>
                    <Button
                      icon={<EditOutlined />}
                      onClick={() =>
                        setDraft({
                          id: open.id,
                          section: open.section,
                          name: open.name,
                          body: open.body ?? "",
                          pinned: open.pinned,
                        })
                      }
                    >
                      Sửa
                    </Button>
                    <Popconfirm
                      title="Xoá tài liệu này?"
                      okText="Xoá"
                      cancelText="Không"
                      onConfirm={() => remove(open)}
                    >
                      <Button danger icon={<DeleteOutlined />}>
                        Xoá
                      </Button>
                    </Popconfirm>
                  </Flex>
                )}
              </Flex>
              <div
                className="doc-markdown"
                style={{
                  padding: "4px 16px 12px",
                  border: `1px solid ${token.colorBorderSecondary}`,
                  borderRadius: token.borderRadiusLG,
                  overflowX: "auto",
                }}
              >
                <Markdown remarkPlugins={[remarkGfm]}>{open.body ?? ""}</Markdown>
              </div>
            </Flex>
          ) : (
            <EmptyState description="Chọn một tài liệu để xem" />
          )}
        </div>
      </Flex>
      <Modal
        title={draft?.id === null ? "Thêm tài liệu" : "Sửa tài liệu"}
        open={draft !== null}
        onCancel={() => setDraft(null)}
        onOk={save}
        okText="Lưu"
        cancelText="Huỷ"
        confirmLoading={saving}
        okButtonProps={{ disabled: !draft?.name.trim() }}
        width={760}
        destroyOnHidden
      >
        {draft && (
          <Form layout="vertical">
            <Flex gap={12}>
              <Form.Item label="Mục" style={{ width: 180 }}>
                <Select
                  aria-label="Mục"
                  value={draft.section}
                  onChange={(value) => setDraft({ ...draft, section: value })}
                  options={listing.sections.map((s) => ({ value: s.key, label: s.label }))}
                />
              </Form.Item>
              <Form.Item label="Tên file" style={{ flex: 1 }}>
                <Input
                  aria-label="Tên file"
                  value={draft.name}
                  placeholder="mau-chung.md"
                  maxLength={120}
                  onChange={(event) => setDraft({ ...draft, name: event.target.value })}
                />
              </Form.Item>
            </Flex>
            <Form.Item label="Nội dung (Markdown)">
              <Input.TextArea
                aria-label="Nội dung (Markdown)"
                value={draft.body}
                autoSize={{ minRows: 12, maxRows: 24 }}
                onChange={(event) => setDraft({ ...draft, body: event.target.value })}
              />
            </Form.Item>
          </Form>
        )}
      </Modal>
    </Flex>
  );
}
