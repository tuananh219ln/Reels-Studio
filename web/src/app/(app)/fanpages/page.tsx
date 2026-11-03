"use client";

import { PlusOutlined } from "@ant-design/icons";
import {
  App,
  Button,
  Card,
  Checkbox,
  Flex,
  Input,
  Modal,
  Popconfirm,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import { useCallback, useEffect, useState } from "react";
import { api, errorMessage, formatDateTime, type Fanpage, type FanpageChoice } from "@/lib/api";
import PageHeader from "@/components/PageHeader";

const number = (value: number) => value.toLocaleString("vi-VN");

/** The worker's last check of the Page's token: works, broken (with what to do), or waiting for the worker. */
function CheckStatus({ row }: { row: Fanpage }) {
  const { check } = row;
  if (!row.active) return <Typography.Text type="secondary">—</Typography.Text>;
  const tag = check.error ? (
    <Tooltip title={check.error}>
      <Tag color="error">Lỗi kết nối</Tag>
    </Tooltip>
  ) : check.checked_at ? (
    <Tag color="success">Hoạt động</Tag>
  ) : (
    <Tag>Chưa kiểm tra</Tag>
  );
  return (
    <Flex vertical gap={2}>
      <span>
        {tag}
        {check.pending && <Typography.Text type="secondary">Đang kiểm tra…</Typography.Text>}
      </span>
      {check.error && (
        <Typography.Text type="danger" style={{ fontSize: 12, maxWidth: 320 }}>
          {check.error}
          {row.scheduled_posts > 0 && ` · ${row.scheduled_posts} bài đang hẹn giờ sẽ không kiểm tra hay hủy được`}
        </Typography.Text>
      )}
      {check.checked_at && (
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          Kiểm tra lúc {formatDateTime(check.checked_at)}
        </Typography.Text>
      )}
    </Flex>
  );
}

function Followers({ row }: { row: Fanpage }) {
  const { followers, followers_this_week: gain } = row.check;
  if (followers === null) return <Typography.Text type="secondary">—</Typography.Text>;
  return (
    <Flex vertical gap={2}>
      <span>{number(followers)}</span>
      {gain !== null && (
        <Typography.Text type={gain > 0 ? "success" : "secondary"} style={{ fontSize: 12 }}>
          {gain > 0 ? "+" : ""}
          {number(gain)} tuần này
        </Typography.Text>
      )}
    </Flex>
  );
}

function TokenInput({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  return (
    <Input.Password
      aria-label="Token"
      value={value}
      autoComplete="new-password"
      placeholder="Dán token vào đây"
      onChange={(event) => onChange(event.target.value)}
    />
  );
}

/** Paste a token, see the Pages it manages, choose which to connect. */
function AddModal({
  open,
  onClose,
  onSaved,
}: {
  open: boolean;
  onClose: () => void;
  onSaved: (rows: Fanpage[]) => void;
}) {
  const { message } = App.useApp();
  const [token, setToken] = useState("");
  const [pages, setPages] = useState<FanpageChoice[] | null>(null);
  const [chosen, setChosen] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  async function lookup() {
    setBusy(true);
    try {
      const found = (await api<{ pages: FanpageChoice[] }>("/fanpages/lookup", "POST", { token })).pages;
      setPages(found);
      const usable = found.filter((page) => page.can_post);
      setChosen(usable.length === 1 ? [usable[0].page_id] : []);
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function save() {
    setBusy(true);
    try {
      onSaved(await api<Fanpage[]>("/fanpages", "POST", { token, page_ids: chosen }));
      onClose();
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      title="Thêm Fanpage"
      open={open}
      onCancel={onClose}
      destroyOnHidden
      afterClose={() => {
        setToken("");
        setPages(null);
        setChosen([]);
      }}
      okText={pages ? "Lưu" : "Kiểm tra token"}
      cancelText="Huỷ"
      confirmLoading={busy}
      okButtonProps={{ disabled: pages ? chosen.length === 0 : !token.trim() }}
      onOk={pages ? save : lookup}
    >
      <Flex vertical gap={12}>
        <TokenInput
          value={token}
          onChange={(value) => {
            setToken(value);
            setPages(null);
          }}
        />
        {pages && (
          <Checkbox.Group
            value={chosen}
            onChange={(values) => setChosen(values as string[])}
            style={{ display: "flex", flexDirection: "column", gap: 6 }}
            options={pages.map((page) => ({
              value: page.page_id,
              disabled: !page.can_post,
              label: page.can_post ? `${page.name} (${page.page_id})` : `${page.name} (token không có quyền đăng)`,
            }))}
          />
        )}
      </Flex>
    </Modal>
  );
}

function TokenModal({
  row,
  onClose,
  onSaved,
}: {
  row: Fanpage | null;
  onClose: () => void;
  onSaved: (rows: Fanpage[]) => void;
}) {
  const { message } = App.useApp();
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);

  async function save() {
    setBusy(true);
    try {
      onSaved(await api<Fanpage[]>(`/fanpages/${row?.id}/token`, "PUT", { token }));
      onClose();
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      title={`Dán token mới cho ${row?.name ?? ""}`}
      open={row !== null}
      onCancel={onClose}
      destroyOnHidden
      afterClose={() => setToken("")}
      okText="Lưu"
      cancelText="Huỷ"
      confirmLoading={busy}
      okButtonProps={{ disabled: !token.trim() }}
      onOk={save}
    >
      <TokenInput value={token} onChange={setToken} />
    </Modal>
  );
}

export default function FanpagesPage() {
  const { message } = App.useApp();
  const [rows, setRows] = useState<Fanpage[] | null>(null);
  const [adding, setAdding] = useState(false);
  const [replacing, setReplacing] = useState<Fanpage | null>(null);

  const load = useCallback(async () => {
    try {
      setRows(await api<Fanpage[]>("/fanpages"));
    } catch (err) {
      message.error(errorMessage(err));
    }
  }, [message]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- loads on mount; state is set only after the request answers
    void load();
  }, [load]);

  async function checkNow(row: Fanpage) {
    try {
      setRows(await api<Fanpage[]>(`/fanpages/${row.id}/check`, "POST"));
    } catch (err) {
      message.error(errorMessage(err));
    }
  }

  // While a check waits for the worker, ask again every few seconds until it has answered.
  const pending = rows?.some((row) => row.check.pending) ?? false;
  useEffect(() => {
    if (!pending) return;
    const timer = setTimeout(() => void load(), 4000);
    return () => clearTimeout(timer);
  }, [pending, rows, load]);

  async function setActive(row: Fanpage, active: boolean) {
    try {
      setRows(await api<Fanpage[]>(`/fanpages/${row.id}`, "PATCH", { active }));
    } catch (err) {
      message.error(errorMessage(err));
    }
  }

  return (
    <>
      <PageHeader
        title="Kết nối Fanpage"
        actions={
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setAdding(true)}>
            Thêm Fanpage
          </Button>
        }
        description={
          <>
            Dán token của một System User trong Business Manager, có quyền <code>pages_show_list</code>,{" "}
            <code>pages_read_engagement</code> và <code>pages_manage_posts</code>, đã được gán Page. Khi lưu, tool kiểm
            tra token với Meta rồi lưu mã hoá; token không bao giờ hiện lại. Sau đó tool tự kiểm tra lại mỗi 12 giờ, để
            biết sớm Page nào hỏng token.
          </>
        }
      />
      <Card styles={{ body: { padding: 0 } }}>
        <Table<Fanpage>
          rowKey="id"
          loading={rows === null}
          dataSource={rows ?? []}
          pagination={false}
          scroll={{ x: "max-content" }}
          locale={{ emptyText: "Chưa kết nối Fanpage nào" }}
          columns={[
            { title: "Page", render: (_, row) => `${row.name} (${row.page_id})` },
            { title: "Token", render: (_, row) => `…${row.token_tail}` },
            {
              title: "Trạng thái",
              render: (_, row) => (
                <Tag color={row.active ? "success" : "default"}>{row.active ? "Đang dùng" : "Ngừng dùng"}</Tag>
              ),
            },
            { title: "Kết nối", render: (_, row) => <CheckStatus row={row} /> },
            { title: "Người theo dõi", render: (_, row) => <Followers row={row} /> },
            {
              title: "Cập nhật",
              render: (_, row) => `${formatDateTime(row.updated_at)}${row.updated_by ? ` · ${row.updated_by}` : ""}`,
            },
            {
              title: "",
              render: (_, row) => (
                <Space>
                  {row.active && (
                    <Button size="small" disabled={row.check.pending} onClick={() => checkNow(row)}>
                      Kiểm tra ngay
                    </Button>
                  )}
                  <Button size="small" onClick={() => setReplacing(row)}>
                    Dán token mới
                  </Button>
                  {row.active ? (
                    <Popconfirm
                      title="Ngừng dùng Fanpage này?"
                      okText="Ngừng dùng"
                      cancelText="Huỷ"
                      onConfirm={() => setActive(row, false)}
                    >
                      <Button size="small" danger>
                        Ngừng dùng
                      </Button>
                    </Popconfirm>
                  ) : (
                    <Button size="small" onClick={() => setActive(row, true)}>
                      Dùng lại
                    </Button>
                  )}
                </Space>
              ),
            },
          ]}
        />
      </Card>
      <AddModal open={adding} onClose={() => setAdding(false)} onSaved={setRows} />
      <TokenModal row={replacing} onClose={() => setReplacing(null)} onSaved={setRows} />
    </>
  );
}
