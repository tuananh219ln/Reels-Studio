"use client";
import FormDrawer from "@/components/FormDrawer";
import { useMe } from "@/components/MeContext";
import ProductModal from "@/components/affiliate/ProductModal";
import QuickFill, { needsQuickFill } from "@/components/affiliate/QuickFill";
import { api, errorMessage, type AffiliateOptions, type AffiliateProduct } from "@/lib/api";
import { CheckOutlined, DeleteOutlined, EditOutlined, ReloadOutlined } from "@ant-design/icons";
import { App, Button, Flex, Popconfirm, Spin } from "antd";
import { useState } from "react";

type Props = {
  product?: AffiliateProduct;
  productId?: number;
  name?: string;
  editLabel?: string;
  onEdit?: (product: AffiliateProduct) => void;
  onChanged: () => void | Promise<void>;
};
export default function ProductActions({ product, productId, name, onChanged, editLabel, onEdit }: Props) {
  const { me } = useMe();
  const { message } = App.useApp();
  const [open, setOpen] = useState(false);
  const [loaded, setLoaded] = useState<AffiliateProduct | null>(null);
  const [options, setOptions] = useState<AffiliateOptions | null>(null);
  const [editing, setEditing] = useState<AffiliateProduct | null>(null);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const row = product ?? loaded;
  const id = product?.id ?? productId;
  async function read() {
    try {
      setFailed(false);
      setLoaded(await api<AffiliateProduct>(`/affiliate-products/${id}`));
    } catch (err) {
      setFailed(true);
      message.error(errorMessage(err));
    }
  }
  async function changed() {
    if (!product) await read();
    await onChanged();
  }
  async function edit() {
    if (!row) return;
    if (onEdit) {
      onEdit(row);
      return;
    }
    try {
      setOptions(await api<AffiliateOptions>("/affiliate-products/options"));
      setEditing(row);
    } catch (err) {
      message.error(errorMessage(err));
    }
  }
  async function act(action: string, method: "POST" | "DELETE" = "POST") {
    setBusy(true);
    try {
      await api(`/affiliate-products/${id}${action ? `/${action}` : ""}`, method);
      if (method === "DELETE") setOpen(false);
      await onChanged();
      if (!product && method !== "DELETE") await read();
      message.success(
        method === "DELETE"
          ? "Đã xoá sản phẩm"
          : action === "approve"
            ? "Đã duyệt"
            : action === "unapprove"
              ? "Đã bỏ duyệt"
              : "Đang lấy lại thông tin",
      );
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }
  const controls = row && (
    <Flex wrap gap={4}>
      <Button
        size="small"
        aria-label={editLabel ?? `Sửa ${row.name}`}
        icon={<EditOutlined />}
        disabled={busy}
        onClick={() => void edit()}
      >
        Sửa thông tin
      </Button>
      <Button
        size="small"
        icon={<CheckOutlined />}
        disabled={busy || row.lookup === "pending" || (row.status !== "approved" && row.problems.length > 0)}
        onClick={() => void act(row.status === "approved" ? "unapprove" : "approve")}
      >
        {row.status === "approved" ? "Bỏ duyệt" : "Duyệt"}
      </Button>
      {row.lookup === "failed" && (
        <Button
          size="small"
          aria-label={`Lấy lại thông tin ${row.name}`}
          icon={<ReloadOutlined />}
          disabled={busy}
          onClick={() => void act("lookup")}
        >
          Lấy lại thông tin
        </Button>
      )}
      {row.created_by_id === me.id && (
        <Popconfirm
          title="Xoá sản phẩm này?"
          description="Sản phẩm cũng được gỡ khỏi các video đang gắn."
          okText="Xoá"
          cancelText="Huỷ"
          onConfirm={() => act("", "DELETE")}
        >
          <Button size="small" danger disabled={busy} aria-label={`Xoá ${row.name}`} icon={<DeleteOutlined />} />
        </Popconfirm>
      )}
    </Flex>
  );
  return (
    <>
      {product ? (
        controls
      ) : (
        <Button
          size="small"
          onClick={() => {
            setOpen(true);
            setLoaded(null);
            void read();
          }}
        >
          Thao tác sản phẩm {name}
        </Button>
      )}
      {!product && (
        <FormDrawer title="Thao tác sản phẩm" open={open} onClose={() => setOpen(false)} footer={null}>
          {row ? (
            <Flex vertical gap={12}>
              <strong>{row.name}</strong>
              {row.problems.map((text) => (
                <span key={text}>{text}</span>
              ))}
              {controls}
              {options && needsQuickFill(row) && <QuickFill product={row} options={options} onSaved={changed} />}
            </Flex>
          ) : failed ? (
            <Button onClick={() => void read()}>Thử lại</Button>
          ) : (
            <Spin />
          )}
        </FormDrawer>
      )}
      {options && (
        <ProductModal
          target={editing}
          options={options}
          onClose={() => setEditing(null)}
          onDone={async () => {
            setEditing(null);
            await changed();
          }}
        />
      )}
    </>
  );
}
