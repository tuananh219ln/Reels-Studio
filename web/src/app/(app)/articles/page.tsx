"use client";
import ArticleActions from "@/components/actions/ArticleActions";

import ArticleThumb from "@/components/ArticleThumb";
import EmptyState from "@/components/EmptyState";
import FilterSelect from "@/components/FilterSelect";
import FormDrawer from "@/components/FormDrawer";
import { useMe } from "@/components/MeContext";
import PageHeader from "@/components/PageHeader";
import StatusText from "@/components/StatusText";
import WhoseFilter, { type Whose } from "@/components/WhoseFilter";
import { ARTICLE_STATUS_TONES, numbersLine } from "@/components/article/ArticlePosting";
import {
  api,
  errorMessage,
  formatDateTime,
  type Article,
  type ArticleKind,
  type ArticleList,
  type Knowledge,
  type PageComments,
} from "@/lib/api";
import { usePolling } from "@/lib/polling";
import { useUrlChoice } from "@/lib/urlState";
import { PlusOutlined } from "@ant-design/icons";
import { App, Button, Card, Flex, Form, Input, Select, Spin, Table, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";

/** Often while an article is being written or posted, else now and then for teammates' new ones. */
const REFRESH_MS = 10_000;
const IDLE_REFRESH_MS = 60_000;

type NewArticle = { knowledge_topic_id: number; kind: ArticleKind; topic: string; source_comment_id?: number };

function NewArticleDrawer({
  open,
  kinds,
  onClose,
}: {
  open: boolean;
  kinds: ArticleList["kinds"];
  onClose: () => void;
}) {
  const { message } = App.useApp();
  const router = useRouter();
  const [form] = Form.useForm<NewArticle>();
  const [groups, setGroups] = useState<Knowledge["topics"]>([]);
  const [comments, setComments] = useState<PageComments["comments"]>([]);
  const [busy, setBusy] = useState(false);
  const kind = Form.useWatch("kind", form);

  useEffect(() => {
    if (!open) return;
    api<Knowledge>("/knowledge")
      .then((data) => {
        setGroups(data.topics);
        if (data.topics.length && !form.getFieldValue("knowledge_topic_id")) {
          form.setFieldValue("knowledge_topic_id", data.topics[0].id);
        }
      })
      .catch((err) => message.error(errorMessage(err)));
  }, [open, form, message]);

  useEffect(() => {
    if (open && kind === "tra_loi_binh_luan") {
      api<PageComments>("/comments?state=all")
        .then((data) => setComments(data.comments))
        .catch((err) => message.error(errorMessage(err)));
    }
  }, [open, kind, message]);

  async function submit() {
    const values = await form.validateFields();
    setBusy(true);
    try {
      const article = await api<Article>("/articles", "POST", values);
      router.push(`/articles/${article.id}`);
    } catch (err) {
      message.error(errorMessage(err));
      setBusy(false);
    }
  }

  return (
    <FormDrawer
      title="Tạo bài viết"
      open={open}
      onClose={onClose}
      guard={form}
      onOk={submit}
      okText="Tạo bài"
      confirmLoading={busy}
      okButtonProps={{ disabled: groups.length === 0 }}
      destroyOnHidden
    >
      <Form form={form} layout="vertical" initialValues={{ kind: "kien_thuc", topic: "" }} requiredMark={false}>
        <Form.Item name="knowledge_topic_id" label="Nhóm chủ đề" rules={[{ required: true, message: "Chọn nhóm" }]}>
          <Select options={groups.map((group) => ({ value: group.id, label: group.name }))} />
        </Form.Item>
        <Form.Item name="kind" label="Dạng bài">
          <Select options={kinds} />
        </Form.Item>
        <Form.Item
          name="topic"
          label="Chủ đề của bài"
          extra="AI viết caption theo chủ đề này; có thể để trống nếu bạn tự viết."
        >
          <Input.TextArea
            autoSize={{ minRows: 2, maxRows: 4 }}
            maxLength={300}
            placeholder="Ví dụ: Uống nước ấm buổi sáng…"
          />
        </Form.Item>
        {kind === "tra_loi_binh_luan" && (
          <Form.Item name="source_comment_id" label="Bình luận được trả lời">
            <Select
              showSearch
              allowClear
              optionFilterProp="label"
              placeholder={comments.length ? "Chọn bình luận" : "Chưa có bình luận nào"}
              options={comments.map((comment) => ({
                value: comment.id,
                label: `${comment.author || "Người xem"}: ${comment.message}`,
              }))}
            />
          </Form.Item>
        )}
      </Form>
    </FormDrawer>
  );
}

export default function ArticlesPage() {
  // The list's search and filters are in the address, which a static page only knows in the browser.
  return (
    <Suspense fallback={null}>
      <Articles />
    </Suspense>
  );
}

function Articles() {
  const { message } = App.useApp();
  const [data, setData] = useState<ArticleList | null>(null);
  const [group, setGroup] = useUrlChoice<string | null>("group", null);
  const [kind, setKind] = useUrlChoice<ArticleKind | null>("kind", null);
  const [creating, setCreating] = useState(false);
  const { me } = useMe();
  // "Của tôi" or "Cả đội"; null until chosen (the default follows whether the member has made an article).
  const [whosePick, setWhose] = useUrlChoice<Whose | null>("whose", null, ["mine", "all"]);

  // `quiet` for the refreshes: an api that is down is said once, on opening, not on every refresh.
  const load = useCallback(
    async (quiet = false) => {
      try {
        setData(await api<ArticleList>("/articles"));
      } catch (err) {
        if (!quiet) message.error(errorMessage(err));
      }
    },
    [message],
  );

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- the first load; state is set only after the request answers
    void load();
  }, [load]);
  const working = (data?.articles ?? []).some(
    (row) => row.suggest.state === "pending" || ["publishing", "pending", "unpublishing"].includes(row.status),
  );
  usePolling(() => load(true), working ? REFRESH_MS : IDLE_REFRESH_MS);

  const all = data?.articles ?? [];
  const mineCount = all.filter((row) => row.created_by_id === me.id).length;
  const whose = whosePick ?? (mineCount > 0 ? "mine" : "all");
  const rows = all.filter(
    (row) =>
      (whose === "all" || row.created_by_id === me.id) &&
      (!group || row.group_name === group) &&
      (!kind || row.kind === kind),
  );
  const groups = [...new Set((data?.articles ?? []).map((row) => row.group_name).filter(Boolean))] as string[];

  const columns: ColumnsType<Article> = [
    {
      title: "Bài viết",
      key: "article",
      width: 320,
      minWidth: 260,
      render: (_, row) => (
        <Flex gap={12} align="center">
          <ArticleThumb article={row} />
          <Flex vertical style={{ minWidth: 0 }}>
            <Link prefetch={false} href={`/articles/${row.id}`}>
              <Typography.Text strong ellipsis style={{ maxWidth: 320 }}>
                {row.hook || row.topic || "(chưa có caption)"}
              </Typography.Text>
            </Link>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {row.topic && row.hook ? row.topic : (row.image_kind_label ?? "Chỉ chữ")}
            </Typography.Text>
          </Flex>
        </Flex>
      ),
    },
    {
      title: "Trạng thái",
      key: "status",
      width: 120,
      render: (_, row) =>
        row.job?.status === "queued" || row.job?.status === "running" ? (
          <StatusText tone="active">AI đang viết…</StatusText>
        ) : (
          <StatusText tone={ARTICLE_STATUS_TONES[row.status]}>{row.status_label}</StatusText>
        ),
    },
    {
      title: "Page",
      key: "pages",
      width: 150,
      render: (_, row) => {
        const pages = [
          ...new Set(
            row.posts
              .filter((post) => post.status === "published" || post.status === "scheduled")
              .map((post) => post.fanpage),
          ),
        ];
        return pages.length ? pages.join(", ") : "—";
      },
    },
    {
      title: "Số 48h",
      key: "numbers",
      width: 230,
      render: (_, row) => {
        const post = row.posts.find((item) => item.numbers.at_48h);
        if (!post) {
          return row.posts.some((item) => item.status === "published") ? (
            <Typography.Text type="secondary">chưa đo 48h</Typography.Text>
          ) : (
            "—"
          );
        }
        const { at_48h: mark, analysis } = post.numbers;
        return (
          <Typography.Text strong={analysis.standout} style={{ fontSize: 13 }}>
            {numbersLine(mark!, analysis.share_rate)}
          </Typography.Text>
        );
      },
    },
    { title: "Dạng bài", dataIndex: "kind_label", width: 130 },
    { title: "Nhóm chủ đề", dataIndex: "group_name", width: 130, render: (value) => value ?? "—" },
    {
      title: "Tạo",
      key: "created",
      width: 140,
      render: (_, row) => (
        <Flex vertical>
          <span>{formatDateTime(row.created_at)}</span>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {row.created_by}
          </Typography.Text>
        </Flex>
      ),
    },
    {
      key: "actions",
      title: "Thao tác",
      width: 280,
      fixed: "right",
      render: (_, row) => <ArticleActions article={row} onChanged={() => load(true)} />,
    },
  ];

  return (
    <>
      <PageHeader
        title="Bài viết"
        description="Bài ảnh hoặc bài chữ cho Page: thử chủ đề rẻ trước khi làm reel, giữ Page đăng đều và gom bình luận."
        actions={
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreating(true)}>
            Tạo bài viết
          </Button>
        }
      >
        <WhoseFilter value={whose} onChange={setWhose} mine={mineCount} all={all.length} />
        <FilterSelect<string>
          value={group}
          placeholder="Mọi nhóm chủ đề"
          onChange={(value) => setGroup(value ?? null)}
          options={groups.map((name) => ({ value: name, label: name }))}
        />
        <FilterSelect<ArticleKind>
          value={kind}
          placeholder="Mọi dạng bài"
          onChange={(value) => setKind(value ?? null)}
          options={data?.kinds ?? []}
        />
      </PageHeader>
      <Card styles={{ body: { padding: 0 } }}>
        {data === null ? (
          <Flex justify="center" style={{ padding: 48 }}>
            <Spin />
          </Flex>
        ) : (
          <Table<Article>
            rowKey="id"
            columns={columns}
            dataSource={rows}
            pagination={false}
            scroll={{ x: "max-content" }}
            locale={{
              emptyText: (
                <EmptyState
                  description={whose === "mine" ? "Không có bài viết nào của bạn khớp bộ lọc" : "Chưa có bài viết nào"}
                  action={
                    whose !== "mine" && (
                      <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreating(true)}>
                        Viết bài đầu tiên
                      </Button>
                    )
                  }
                />
              ),
            }}
          />
        )}
      </Card>
      <NewArticleDrawer open={creating} kinds={data?.kinds ?? []} onClose={() => setCreating(false)} />
    </>
  );
}
