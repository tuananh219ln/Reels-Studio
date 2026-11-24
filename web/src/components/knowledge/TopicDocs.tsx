"use client";

import EmptyState from "@/components/EmptyState";
import { api, errorMessage, formatDateTime, type TopicDoc } from "@/lib/api";
import {
  CopyOutlined,
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

type Heading = { id: string; level: number; text: string };

/** An anchor for a heading: its words without accents, joined by dashes (the same for the outline and the heading). */
function anchorOf(text: string): string {
  const plain = text
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/đ/g, "d")
    .replace(/Đ/g, "D")
    .toLowerCase();
  return `doc-${plain.replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "")}`;
}

/** The "#", "##" and "###" headings of a Markdown text, outside code fences, for "Trên trang này". */
function outlineOf(body: string): Heading[] {
  const found: Heading[] = [];
  let fenced = false;
  for (const line of body.split("\n")) {
    if (line.trimStart().startsWith("```")) {
      fenced = !fenced;
      continue;
    }
    const match = !fenced && /^(#{1,3})\s+(.+?)\s*#*\s*$/.exec(line);
    if (match) {
      const text = match[2].replace(/[*_`]/g, "");
      found.push({ id: anchorOf(text), level: match[1].length, text });
    }
  }
  return found;
}

function textOf(node: React.ReactNode): string {
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(textOf).join("");
  if (node && typeof node === "object" && "props" in node)
    return textOf((node as { props: { children?: React.ReactNode } }).props.children);
  return "";
}

/** Headings that carry the anchor "Trên trang này" jumps to. */
const headingAnchors = {
  h1: ({ children }: { children?: React.ReactNode }) => <h1 id={anchorOf(textOf(children))}>{children}</h1>,
  h2: ({ children }: { children?: React.ReactNode }) => <h2 id={anchorOf(textOf(children))}>{children}</h2>,
  h3: ({ children }: { children?: React.ReactNode }) => <h3 id={anchorOf(textOf(children))}>{children}</h3>,
};

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
  const pinnedCount = docs.filter((doc) => doc.pinned).length;
  const outline = open ? outlineOf(open.body ?? "") : [];

  async function copy(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      message.success("Đã sao chép nội dung tài liệu");
    } catch {
      message.error("Trình duyệt không cho sao chép, hãy bôi đen và sao chép tay");
    }
  }

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
        Bản chính của tài liệu vận hành nhóm; job dựng đọc qua MCP (“Liệt kê tài liệu của nhóm”, “Đọc tài liệu của
        nhóm”), không chép vào thân job.
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
        <Flex vertical gap={4} style={{ width: 300, maxWidth: "100%" }} data-testid="doc-list">
          {docs.length === 0 && (
            <EmptyState
              description={listing.docs.length ? "Không có tài liệu nào khớp" : "Nhóm này chưa có tài liệu nào"}
            />
          )}
          {[
            { title: "Ghim", rows: docs.filter((doc) => doc.pinned) },
            { title: pinnedCount > 0 ? "Khác" : "", rows: docs.filter((doc) => !doc.pinned) },
          ].map(
            ({ title, rows }) =>
              rows.length > 0 && (
                <Flex vertical gap={4} key={title || "all"}>
                  {title && (
                    <Typography.Text type="secondary" style={{ fontSize: 12, padding: "4px 4px 0" }}>
                      {title === "Ghim" ? "📌 Ghim" : title}
                    </Typography.Text>
                  )}
                  {rows.map((doc) => (
                    <Flex
                      key={doc.id}
                      gap={6}
                      align="flex-start"
                      data-testid="doc-row"
                      onClick={() => setOpenId(doc.id)}
                      style={{
                        cursor: "pointer",
                        padding: "7px 8px",
                        borderRadius: token.borderRadius,
                        background: openId === doc.id ? token.colorPrimaryBg : "transparent",
                      }}
                    >
                      <Tooltip title={doc.pinned ? "Bỏ ghim" : "Ghim lên đầu"}>
                        <Button
                          size="small"
                          type="text"
                          aria-label={doc.pinned ? "Bỏ ghim" : "Ghim"}
                          disabled={!canEdit}
                          icon={
                            doc.pinned ? <PushpinFilled style={{ color: token.colorWarning }} /> : <PushpinOutlined />
                          }
                          onClick={(event) => {
                            event.stopPropagation();
                            void togglePin(doc);
                          }}
                        />
                      </Tooltip>
                      <Flex vertical style={{ minWidth: 0, flex: 1 }}>
                        <Typography.Text strong ellipsis={{ tooltip: doc.title }}>
                          {doc.title}
                        </Typography.Text>
                        <Typography.Text type="secondary" ellipsis style={{ fontSize: 12 }}>
                          {doc.section_label} · {doc.updated_by ?? "—"}, {formatDateTime(doc.updated_at)}
                        </Typography.Text>
                      </Flex>
                    </Flex>
                  ))}
                </Flex>
              ),
          )}
        </Flex>
        <div style={{ flex: 1, minWidth: 280 }} data-testid="doc-reader">
          {open ? (
            <Flex gap={16} align="flex-start" wrap>
              <Flex vertical gap={8} style={{ flex: "1 1 420px", minWidth: 0, maxWidth: 760 }}>
                <Flex justify="space-between" align="center" gap={8} wrap>
                  <Typography.Text type="secondary">
                    {open.section_label} · {open.name} · sửa lần cuối {open.updated_by ?? "—"},{" "}
                    {formatDateTime(open.updated_at)}
                  </Typography.Text>
                  <Flex gap={8}>
                    <Button icon={<CopyOutlined />} onClick={() => void copy(open.body ?? "")}>
                      Sao chép
                    </Button>
                    {canEdit && (
                      <>
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
                      </>
                    )}
                  </Flex>
                </Flex>
                <div
                  className="doc-markdown"
                  style={{
                    padding: "4px 20px 16px",
                    border: `1px solid ${token.colorBorderSecondary}`,
                    borderRadius: token.borderRadiusLG,
                    overflowX: "auto",
                    lineHeight: 1.7,
                  }}
                >
                  <Markdown remarkPlugins={[remarkGfm]} components={headingAnchors}>
                    {open.body ?? ""}
                  </Markdown>
                </div>
              </Flex>
              {outline.length >= 3 && (
                <nav
                  aria-label="Trên trang này"
                  style={{ flex: "0 0 180px", position: "sticky", top: 16, maxHeight: "70vh", overflowY: "auto" }}
                >
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    Trên trang này
                  </Typography.Text>
                  <Flex vertical gap={2} style={{ marginTop: 4 }}>
                    {outline.map((heading) => (
                      <a
                        key={heading.id}
                        href={`#${heading.id}`}
                        onClick={(event) => {
                          event.preventDefault();
                          document.getElementById(heading.id)?.scrollIntoView({ behavior: "smooth", block: "start" });
                        }}
                        style={{ fontSize: 12, paddingInlineStart: (heading.level - 1) * 10, color: "inherit" }}
                      >
                        {heading.text}
                      </a>
                    ))}
                  </Flex>
                </nav>
              )}
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
