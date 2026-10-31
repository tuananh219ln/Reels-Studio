"use client";

import { PlusOutlined } from "@ant-design/icons";
import { App, Button, Checkbox, Flex, Input, Modal, Popconfirm, Space, Table, Tag, Typography } from "antd";
import { useCallback, useEffect, useState } from "react";
import { api, errorMessage, type Fanpage, type FanpageChoice } from "@/lib/api";

const time = (value: string) => new Date(value).toLocaleString("vi-VN", { dateStyle: "short", timeStyle: "short" });

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

  async function setActive(row: Fanpage, active: boolean) {
    try {
      setRows(await api<Fanpage[]>(`/fanpages/${row.id}`, "PATCH", { active }));
    } catch (err) {
      message.error(errorMessage(err));
    }
  }

  return (
    <>
      <Flex wrap gap={12} justify="space-between" align="center">
        <Typography.Title level={2} style={{ margin: 0, fontWeight: 600 }}>
          Kết nối Fanpage
        </Typography.Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setAdding(true)}>
          Thêm Fanpage
        </Button>
      </Flex>
      <Typography.Paragraph type="secondary" style={{ margin: "8px 0 16px" }}>
        Dán token của một System User trong Business Manager, có quyền <code>pages_show_list</code>,{" "}
        <code>pages_read_engagement</code> và <code>pages_manage_posts</code>, đã được gán Page. Khi lưu, tool kiểm tra
        token với Meta rồi lưu mã hoá; token không bao giờ hiện lại.
      </Typography.Paragraph>
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
          {
            title: "Cập nhật",
            render: (_, row) => `${time(row.updated_at)}${row.updated_by ? ` · ${row.updated_by}` : ""}`,
          },
          {
            title: "",
            render: (_, row) => (
              <Space>
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
      <AddModal open={adding} onClose={() => setAdding(false)} onSaved={setRows} />
      <TokenModal row={replacing} onClose={() => setReplacing(null)} onSaved={setRows} />
    </>
  );
}
